# infra/ — Terraform for the k3s target

Everything AWS is expressed here; there are no manual console steps beyond two
that AWS gives no API for: delegating nameservers at your registrar, and
requesting SES production access. Both are called out in the runbook below.

The repo's root `.gitignore` has a `*md` rule, so this file was force-added.
The reasoning that must survive also lives in comments in the `.tf` files.

> **`deployments.md` in the repo root is stale.** It describes a Railway
> deployment with a managed Postgres plugin and `railway up` in CI, which
> contradicts this project's architecture spec (self-managed k3s on EC2,
> Terraform, ECR). This directory implements that target.

## What it creates

| Resource | Notes |
| --- | --- |
| VPC + one public subnet + IGW | No private subnets: they would need a NAT gateway at ~$32/mo, more than the whole budget. |
| S3 gateway endpoint | Free, and keeps PDF/model traffic off the metered IGW path. |
| Security group | 80/443 public; 22 and 6443 restricted to `ssh_allowed_cidr`. |
| EC2 instance (t4g, ARM) | Single k3s node, Ubuntu 24.04 arm64, IMDSv2 required. |
| Elastic IP | Stable address so DNS and kubeconfig survive a stop/start. |
| S3 bucket | `uploads/` for PDFs, `models/` for artifacts, with lifecycle pruning. |
| ECR repositories | `app` and `ml`, with lifecycle rules so old images stop accruing storage cost. |
| IAM role + instance profile | ECR pull, S3 read/write on the one bucket, SSM Session Manager, and read access to its own secrets in Parameter Store. No static keys anywhere. |
| Route53 hosted zone + records | Apex A record to the EIP, `www` CNAME, and the SES verification/DKIM/SPF/DMARC records. |
| SES domain identity + DKIM | Sending identity for verification and password-reset email. Starts in **sandbox mode** — see the runbook. |
| GitHub OIDC provider + deploy role | CI assumes a short-lived role scoped to one repo on `refs/heads/main`. No AWS access key is stored in GitHub. |

Kubernetes manifests live in [`k8s/`](k8s/) and are applied by the deploy
pipeline: Postgres (StatefulSet on a `local-path` PVC), Redis, the app
Deployment with an Alembic init container, a Traefik ingress with cert-manager
TLS, and the nightly backup CronJob.

## Cost

Against the $20/month ceiling, us-east-1 on demand:

| Item | Monthly |
| --- | --- |
| t4g.small (default) | $12.26 |
| 30 GB gp3 root | $2.40 |
| Public IPv4 | $3.65 |
| ECR + S3 | ~$1.50 |
| Route53 hosted zone | $0.50 |
| SES | $0 (free from EC2 under 62k messages/mo) |
| **Total** | **~$20.30** |

**This is ~$0.30 over the $20 ceiling**, and the overage is the Route53 hosted
zone. Stated rather than rounded away, because the ceiling is a real constraint.
Three ways to close it if that matters: keep DNS at the registrar and point an A
record at the Elastic IP by hand (saves $0.50, loses Terraform-managed DNS);
drop the root volume from 30 GB to 20 GB (saves $0.80, but 30 GB is the
free-tier allowance so this may be $0 anyway); or accept it. The single largest
line remains the public IPv4 address at $3.65, which is unavoidable for a
publicly reachable single node.

`t4g.medium` — the originally specced size — is $24.53/mo for the instance
alone, putting the total near **$32/mo**. It stays available as a variable
override, but it does not fit the stated budget without a 1-year Compute
Savings Plan. `terraform output estimated_monthly_cost_usd` recomputes this for
whatever size is selected.

Postgres and Redis run **in-cluster** rather than as RDS/ElastiCache for the
same reason; see the comment block at the top of `variables.tf` for the full
list of managed services deliberately avoided and what each would have cost.

## Usage

For a first deployment follow the **[Deployment runbook](#deployment-runbook)**
below — the order matters, and two steps (nameserver delegation, SES production
access) have to happen before things that depend on them.

To just stand up the infrastructure:

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Fill in ssh_allowed_cidr (curl -s https://checkip.amazonaws.com), ssh_public_key,
# domain_name, acme_email, dmarc_report_email and github_repository.

terraform init
terraform plan
terraform apply
```

Then pull the kubeconfig:

```bash
terraform output -raw kubeconfig_command   # prints the command to run
```

## Things to know before applying

- **`ssh_allowed_cidr` has no default and rejects `0.0.0.0/0`.** Port 6443 is
  cluster admin; it is never opened broadly.
- **The node's root volume holds the Postgres data directory.** Replacing the
  instance destroys the database. `aws_instance.node` therefore has
  `ignore_changes = [ami, user_data]`, so a new Canonical AMI release or an
  edit to the bootstrap script does not silently schedule a replace. Rotating
  either is a deliberate, manual operation that needs a database dump first.
- **State is local by default.** The S3 backend block in `versions.tf` is
  commented out because the bucket it would use is created by this config —
  apply once with local state, then migrate.
- **Bootstrap is thin on purpose.** `user_data/k3s-bootstrap.sh.tftpl` installs
  k3s, the AWS CLI, and a systemd timer that refreshes the ECR image-pull
  secret every 6 hours (ECR tokens expire after 12). Application manifests are
  applied by CI, not baked into the image.

## Deployment runbook

Order matters. Each step gates the next.

### 1. Seed secrets (before anything else)

```bash
cd infra/scripts
AWS_REGION=us-east-1 ./put-secrets.sh
```

Writes SecureStrings to SSM Parameter Store under `/marigold/`. It generates the
Postgres password and `SECRET_KEY` for you and prompts for `GEMINI_API_KEY`.
OAuth client credentials are optional — omitted means password login only,
because `backend/oauth.py` only registers a provider when both of its values are
present.

**The deploy pipeline never sees these.** SSM `SendCommand` parameters are kept
in command history readable by anyone with `ssm:ListCommands`, so a password
passed as a command argument would leak. The node reads them itself.

### 2. Request SES production access — do this first, it has a queue

New SES accounts are in **sandbox mode**: mail is accepted by the API and
delivered only to separately verified addresses. Signup verification emails to
real users are silently dropped. Open the request in the SES console for your
region; approval is usually under 24h. Until then run with
`EMAIL_BACKEND=console` and verify accounts by hand.

This is the only step in the whole deployment with someone else's queue in front
of it, which is why it comes before the infrastructure that depends on it.

### 3. Apply the infrastructure

```bash
cp terraform.tfvars.example terraform.tfvars   # fill it in
terraform init && terraform plan               # read the plan
terraform apply
```

Check `estimated_monthly_cost_usd` in the output against the ceiling.

### 4. Delegate DNS at your registrar

```bash
terraform output route53_nameservers
```

Point the domain's nameservers at those four values. **Nothing works until this
propagates** — not the site, and not the Let's Encrypt HTTP-01 challenge, so no
certificate can be issued either. Confirm with `dig +short NS <domain>`.

### 5. Confirm the node bootstrapped

```bash
ssh ubuntu@$(terraform output -raw node_public_ip) \
  'sudo tail -30 /var/log/marigold-bootstrap.log'
```

Must end with `bootstrap complete`. That log covers k3s, the 2 GB swapfile,
cert-manager, and the ECR credential refresh timer.

### 6. Configure GitHub and deploy

Set these as repository **variables**: `DOMAIN`, `ACME_EMAIL`, `AWS_REGION`,
`ARTIFACTS_BUCKET`, `SES_FROM_EMAIL`, `INSTANCE_ID` (all from `terraform
output`), and one **secret**: `AWS_DEPLOY_ROLE_ARN` from
`terraform output github_actions_role_arn`.

Push to `main`. The deploy workflow builds an **arm64** image, pushes it to ECR,
and rolls it out over SSM.

### 7. Verify

```bash
curl https://<domain>/healthz          # no -k; the certificate must be real
```

Then register, verify the email, upload a PDF, study a card and take a quiz. The
check that matters most:

```sql
SELECT source, count(*) FROM interactions GROUP BY source;
```

Both `quiz` and `study` rows must be present. That is the knowledge-tracing
training data actually accumulating, which is the entire premise of wiring
`ml/` in later.

### 8. Prove the backup restores

An untested backup is not a backup.

```bash
kubectl -n marigold create job --from=cronjob/postgres-backup backup-check
kubectl -n marigold logs job/backup-check
aws s3 ls s3://$(terraform output -raw artifacts_bucket)/backups/ --recursive
```

Then restore one into a scratch database and count the tables. This was verified
locally against Postgres 16 (dump → restore → 12 tables + row content intact);
the S3 leg needs the node's instance profile and can only be checked there.

## Operations

**Rollback:** `kubectl -n marigold rollout undo deployment/app`. ECR keeps the
last 10 tagged images, each tagged with its commit SHA.

**Run something on the node without opening a port:**
`aws ssm start-session --target $(terraform output -raw node_instance_id)`.

**Rotate a secret:** re-run `put-secrets.sh`, then redeploy. Note that changing
`POSTGRES_PASSWORD` there does *not* change it in an existing database —
Postgres only reads that variable when initialising an empty data directory. Use
`ALTER ROLE` in the cluster as well.

**Memory.** The node is 2 GB and the steady state is ~1.5 GB. Check with
`free -m` over SSM. metrics-server is disabled deliberately (it costs ~100 MB),
so `kubectl top` is unavailable by design.

## Not done yet

- **No spot-instance training config.** GPU training is specified as
  provision-use-destroy and has no Terraform yet.
- **`ml/` is not wired into the product.** Nothing imports it; there is no
  `/api/review/next` endpoint. The deployment is shaped so it can be added
  in-process (the prior-only path is pure NumPy), but torch's resident set must
  be re-measured against the 2 GB budget before the SAKT path is enabled.
- **Backups depend on the Alpine package repo.** The CronJob installs `aws-cli`
  at runtime; a sustained outage there means missed backups. The fix is a
  dedicated backup image in ECR, traded off against a second image to build and
  store.
- **Terraform state is local** until the S3 backend in `versions.tf` is
  uncommented and migrated, which can only happen after the first apply creates
  the bucket.
