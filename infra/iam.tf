# The node's identity. An instance profile is used rather than long-lived access
# keys so nothing has to store credentials on the box or in GitHub for the
# node's own AWS calls.

data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "node" {
  name               = "${var.project}-node"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

# ECR: pull only. The node runs images; CI is what pushes them.
data "aws_iam_policy_document" "ecr_pull" {
  statement {
    sid = "GetAuthToken"
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    # This call is not resource-scoped in the ECR API.
    resources = ["*"]
  }

  statement {
    sid = "PullImages"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [for r in aws_ecr_repository.services : r.arn]
  }
}

resource "aws_iam_role_policy" "ecr_pull" {
  name   = "${var.project}-ecr-pull"
  role   = aws_iam_role.node.id
  policy = data.aws_iam_policy_document.ecr_pull.json
}

# S3: read and write only inside the project's own bucket. Uploaded PDFs and
# model artifacts both live there, so the node needs both directions.
data "aws_iam_policy_document" "s3_artifacts" {
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.artifacts.arn]
  }

  statement {
    sid = "ReadWriteObjects"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${aws_s3_bucket.artifacts.arn}/*"]
  }
}

resource "aws_iam_role_policy" "s3_artifacts" {
  name   = "${var.project}-s3-artifacts"
  role   = aws_iam_role.node.id
  policy = data.aws_iam_policy_document.s3_artifacts.json
}

resource "aws_iam_instance_profile" "node" {
  name = "${var.project}-node"
  role = aws_iam_role.node.name
}

# --- Application secrets ------------------------------------------------------
#
# Secrets live in SSM Parameter Store as SecureString and are read by the node
# at deploy time, which is what keeps them out of three places they must never
# be: this repository, the container image, and the SSM command history that
# `ssm:SendCommand` parameters are recorded in (those are readable by anyone
# with ssm:ListCommands, so passing a database password as a command argument
# would defeat the point).
#
# The deploy pipeline therefore never handles a secret at all — it only tells
# the node to refresh the Kubernetes secret from here.
data "aws_iam_policy_document" "ssm_parameters" {
  statement {
    sid = "ReadAppSecrets"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
    ]
    resources = [
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${var.project}/*",
    ]
  }

  statement {
    sid     = "DecryptSecureStrings"
    actions = ["kms:Decrypt"]
    # The AWS-managed key SSM uses for SecureString by default.
    resources = ["arn:aws:kms:${var.aws_region}:${data.aws_caller_identity.current.account_id}:alias/aws/ssm"]
  }
}

resource "aws_iam_role_policy" "ssm_parameters" {
  name   = "${var.project}-ssm-parameters"
  role   = aws_iam_role.node.id
  policy = data.aws_iam_policy_document.ssm_parameters.json
}

# --- SSM: how CI reaches the node ---------------------------------------------
#
# Session Manager is what lets the deploy pipeline run kubectl on the box
# without opening a single inbound port. The alternative would be allowing the
# Kubernetes API (6443) from GitHub's runner IP ranges, which are large,
# change without notice, and are shared with every other GitHub customer —
# effectively handing cluster admin to a very wide net. security.tf keeps 6443
# restricted to var.ssh_allowed_cidr precisely because of this.
resource "aws_iam_role_policy_attachment" "node_ssm" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# --- GitHub Actions OIDC ------------------------------------------------------
#
# CI assumes a role by presenting a short-lived token GitHub signs for the
# workflow run. No long-lived AWS access key is created, stored in GitHub, or
# able to leak from it.
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # GitHub rotates its signing certificate. Modern AWS validates the OIDC
  # provider against the host's live certificate chain rather than this
  # thumbprint, but the field is still required by the API.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]

  tags = {
    Name = "${var.project}-github-oidc"
  }
}

data "aws_iam_policy_document" "github_assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Scoped to this repository's main branch. Without a `sub` condition any
    # GitHub repository in the world could assume this role — this is the
    # single most important line in the file.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "${var.project}-github-actions"
  description        = "Assumed by GitHub Actions to build, push and deploy ${var.project}"
  assume_role_policy = data.aws_iam_policy_document.github_assume_role.json
}

# Push images, and tell the node to pull and roll them out. Deliberately narrow:
# no ec2:*, no iam:*, and no ability to read the artifacts bucket.
data "aws_iam_policy_document" "github_deploy" {
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # Not resource-scopable in the ECR API.
  }

  statement {
    sid = "EcrPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [for r in aws_ecr_repository.services : r.arn]
  }

  statement {
    sid     = "RunDeployOnTheNode"
    actions = ["ssm:SendCommand"]
    # Restricted to this one instance plus the AWS-owned shell document, so the
    # role cannot run commands on anything else in the account.
    resources = [
      aws_instance.node.arn,
      "arn:aws:ssm:${var.aws_region}::document/AWS-RunShellScript",
    ]
  }

  statement {
    sid = "ReadDeployResult"
    actions = [
      "ssm:GetCommandInvocation",
      "ssm:ListCommandInvocations",
      "ssm:ListCommands",
    ]
    resources = ["*"] # These are not resource-scopable either.
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "${var.project}-github-deploy"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_deploy.json
}
