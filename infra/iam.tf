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
