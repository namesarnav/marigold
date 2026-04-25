terraform {
  required_version = ">= 1.6.0"

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
  # prior setup. Uncomment to move state into the artifacts bucket once it
  # exists — note the chicken-and-egg: the bucket is created by this config, so
  # apply once with local state, then migrate.
  #
  # backend "s3" {
  #   bucket       = "marigold-artifacts-<suffix>"
  #   key          = "infra/terraform.tfstate"
  #   region       = "us-east-1"
  #   encrypt      = true
  #   use_lockfile = true
  # }
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
