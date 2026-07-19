terraform {
  # 1.10+ specifically: the S3 backend below uses `use_lockfile`, which replaces
  # the old DynamoDB lock table and does not exist in earlier versions.
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # State is local by default so a fresh clone can `terraform plan` with no
  # prior setup.
  #
  # To move it to S3 — recommended once this is real, because local state means
  # one laptop is the only record of what exists — copy backend.tf.example to
  # backend.tf and backend.hcl.example to backend.hcl, then:
  #
  #   terraform init -backend-config=backend.hcl -migrate-state
  #
  # The backend deliberately uses a *separate*, hand-created bucket rather than
  # the artifacts bucket this config manages. State that lives in a bucket
  # described by that same state is a bootstrap knot: you cannot create it on
  # the first apply, and you cannot cleanly destroy it on the last.
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "marigold"
      ManagedBy = "terraform"
    }
  }
}
