variable "aws_region" {
  description = "Region to deploy into. Kept in one place because instance pricing below is region-specific."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "marigold"
}

# --- Cost ceiling -------------------------------------------------------------
#
# The project budget is $20/month of total AWS spend. That ceiling is what
# drives most of the shape of this config, so the reasoning lives here rather
# than in a doc that drifts:
#
#   t4g.small   730h x $0.0168  = $12.26/mo   <- default, fits
#   t4g.medium  730h x $0.0336  = $24.53/mo   <- over budget on its own
#   30 GB gp3 root volume                     = $2.40/mo
#   1 public IPv4 address (charged since Feb 2024) = $3.65/mo
#   ECR storage + S3 (small)                  = $1-2/mo
#
# So t4g.small lands around $18/mo all-in and t4g.medium around $32/mo. The
# t4g.medium target therefore needs either a 1-year Compute Savings Plan
# (~$15/mo for the instance) or an accepted budget overrun.
#
# Deliberately NOT used, all of which would break the ceiling:
#   - EKS            ($72/mo control plane) -> self-managed k3s instead
#   - RDS            (~$15/mo smallest)     -> Postgres runs in-cluster
#   - ElastiCache    (~$12/mo smallest)     -> Redis runs in-cluster
#   - NAT Gateway    (~$32/mo + data)       -> single public subnet, no private subnets
#   - ALB            (~$16/mo)              -> k3s Traefik ingress on the instance
#   - Always-on GPU  ($380+/mo for g5.xlarge) -> training runs on torn-down spot
#
variable "instance_type" {
  description = <<-EOT
    EC2 instance type. Must be ARM/Graviton (t4g.*) to match the ECR images.

    Defaults to t4g.small to stay under the $20/month ceiling. t4g.medium is
    the originally specced size and gives the PyTorch ML service real headroom,
    but pushes total spend to roughly $32/month on demand — override this only
    with that tradeoff in mind.
  EOT
  type        = string
  default     = "t4g.small"

  validation {
    condition     = startswith(var.instance_type, "t4g.")
    error_message = "Instance type must be a t4g.* (Graviton/ARM) size to match the ARM container images."
  }
}

variable "root_volume_size_gb" {
  description = <<-EOT
    Root EBS volume size. Holds the OS, container images, and the in-cluster
    Postgres and Redis data via k3s local-path storage.

    30 GB is the AWS free-tier allowance and the smallest size that comfortably
    fits the image set; the ML service's model artifacts live in S3 rather than
    on disk to keep this small.
  EOT
  type        = number
  default     = 30
}

variable "ssh_allowed_cidr" {
  description = <<-EOT
    CIDR permitted to reach SSH (22) and the k3s API (6443).

    There is no default on purpose: this must be your own address, e.g.
    "203.0.113.4/32". Exposing the Kubernetes API to 0.0.0.0/0 hands cluster
    admin to anyone who obtains the node token.
  EOT
  type        = string

  validation {
    condition     = var.ssh_allowed_cidr != "0.0.0.0/0"
    error_message = "Refusing 0.0.0.0/0: the k3s API and SSH must be restricted to a known address."
  }
}

variable "ssh_public_key" {
  description = "OpenSSH public key installed on the instance for admin access."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR for the VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR for the single public subnet. No private subnets exist: they would need a NAT gateway."
  type        = string
  default     = "10.20.1.0/24"
}

variable "ecr_repositories" {
  description = <<-EOT
    Container repositories, one per deployable image.

    Matches what the repo actually builds today: the root Dockerfile produces a
    single "app" image (FastAPI serving the built Vite bundle as static files),
    and "ml" is the separate PyTorch inference service. Splitting app into
    separate backend and frontend images is a later step and would mean adding
    an nginx image plus per-service Dockerfiles.
  EOT
  type        = list(string)
  default     = ["app", "ml"]
}

variable "ecr_untagged_expiry_days" {
  description = "Days before untagged images are deleted. CI pushes on every merge, so untagged layers accumulate and are billed."
  type        = number
  default     = 7
}

variable "ecr_max_tagged_images" {
  description = "Tagged images kept per repository, newest first. Enough to roll back a few deploys without paying to store every build."
  type        = number
  default     = 10
}

# --- Domain and email ---------------------------------------------------------

variable "domain_name" {
  description = <<-EOT
    The apex domain the app is served from, e.g. "marigold.app". No scheme, no
    trailing dot, no "www." prefix — the www record is derived from this.

    No default: this is deployment-specific, and a wrong value here produces a
    hosted zone and a certificate for someone else's name.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", var.domain_name))
    error_message = "domain_name must be a bare domain like example.com — no scheme, no path, no trailing dot."
  }

  validation {
    condition     = !startswith(var.domain_name, "www.")
    error_message = "Use the apex domain; the www CNAME is created from it automatically."
  }
}

variable "acme_email" {
  description = <<-EOT
    Contact address registered with Let's Encrypt. They email it when a
    certificate is close to expiring without having renewed, which is the only
    warning you get before the site starts serving an invalid certificate.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", var.acme_email))
    error_message = "acme_email must be a valid email address."
  }
}

variable "dmarc_report_email" {
  description = <<-EOT
    Where aggregate DMARC reports are sent. Can be the same as acme_email.
    Receiving mail providers send a daily XML summary of what passed and failed
    authentication, which is how you find out DKIM broke before users do.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", var.dmarc_report_email))
    error_message = "dmarc_report_email must be a valid email address."
  }
}

variable "github_repository" {
  description = <<-EOT
    The GitHub repo allowed to assume the CI deploy role, as "owner/name".

    This is a security boundary, not a label: the OIDC trust policy scopes role
    assumption to this exact repository. A wildcard here would let any repo on
    GitHub push images to your registry and deploy to your cluster.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$", var.github_repository))
    error_message = "github_repository must be in owner/name form, e.g. arnavverma/marigold."
  }
}

variable "backup_retention_days" {
  description = <<-EOT
    How long nightly database dumps are kept in S3.

    This is the recovery window, not a tidiness setting: the database lives on
    the node's root volume with no replica, so these dumps are the only thing
    standing between an instance failure and total data loss.
  EOT
  type        = number
  default     = 30

  validation {
    condition     = var.backup_retention_days >= 7
    error_message = "Keep at least 7 days of backups; a shorter window cannot survive a problem discovered over a weekend."
  }
}
