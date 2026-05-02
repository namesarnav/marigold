# infra/ — Terraform for the k3s target

Everything AWS is expressed here; there are no manual console steps. Note that
the repo's root `.gitignore` has a `*md` rule, so this file is untracked — the
reasoning that must survive lives in comments in the `.tf` files themselves.

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
| IAM role + instance profile | ECR pull, S3 read/write on the one bucket. No static keys anywhere. |

## Cost

Against the $20/month ceiling, us-east-1 on demand:

| Item | Monthly |
| --- | --- |
| t4g.small (default) | $12.26 |
| 30 GB gp3 root | $2.40 |
| Public IPv4 | $3.65 |
| ECR + S3 | ~$1.50 |
| **Total** | **~$19.80** |

`t4g.medium` — the originally specced size — is $24.53/mo for the instance
alone, putting the total near **$32/mo**. It stays available as a variable
override, but it does not fit the stated budget without a 1-year Compute
Savings Plan. `terraform output estimated_monthly_cost_usd` recomputes this for
whatever size is selected.

Postgres and Redis run **in-cluster** rather than as RDS/ElastiCache for the
same reason; see the comment block at the top of `variables.tf` for the full
list of managed services deliberately avoided and what each would have cost.

## Usage

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Fill in ssh_allowed_cidr (curl -s https://checkip.amazonaws.com) and ssh_public_key

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

## Not done yet

- **No Kubernetes manifests.** Nothing deploys the app to the cluster; there is
  no `k8s/` directory yet. The node comes up empty apart from k3s itself.
- **No CI wiring.** The spec describes build → ECR → `kubectl apply`; the
  only workflow present is `datadog-synthetics.yml`.
- **No TLS/DNS.** Traefik serves plain HTTP; cert-manager and a DNS record are
  not configured.
- **No spot-instance training config.** GPU training is specified as
  provision-use-destroy and has no Terraform yet.
