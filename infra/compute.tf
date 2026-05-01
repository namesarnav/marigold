# Ubuntu 24.04 LTS on arm64. Resolved by data source rather than a hardcoded
# AMI id so the config is region-portable, with the id ignored on subsequent
# applies (see lifecycle below) so a new Canonical release does not silently
# schedule the node for replacement.
data "aws_ami" "ubuntu_arm64" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd*/ubuntu-noble-24.04-arm64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_instance" "node" {
  ami                    = data.aws_ami.ubuntu_arm64.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.node.id]
  key_name               = aws_key_pair.admin.key_name
  iam_instance_profile   = aws_iam_instance_profile.node.name

  user_data                   = local.k3s_bootstrap
  user_data_replace_on_change = false # Editing the script must not destroy a running cluster.

  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_size_gb
    encrypted   = true
    # gp3 includes 3000 IOPS and 125 MB/s at no extra charge; going above
    # either is billed, and a single-user workload does not need it.
    iops       = 3000
    throughput = 125

    tags = {
      Name = "${var.project}-root"
    }
  }

  metadata_options {
    # IMDSv2 only: a server-side request forgery in the app should not be able
    # to read the instance role's credentials.
    http_tokens                 = "required"
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 2 # Containers need one extra hop.
  }

  lifecycle {
    # This node holds the Postgres data directory on its root volume, so
    # replacing it destroys the database. Both of these are the usual causes of
    # an unintended replace.
    ignore_changes = [ami, user_data]
  }

  tags = {
    Name = "${var.project}-node"
  }
}

# A stable address, so DNS and the kubeconfig survive a stop/start. An EIP
# attached to a running instance carries no charge beyond the public-IPv4 fee
# that any public address now incurs.
resource "aws_eip" "node" {
  domain = "vpc"

  tags = {
    Name = "${var.project}-eip"
  }
}

resource "aws_eip_association" "node" {
  instance_id   = aws_instance.node.id
  allocation_id = aws_eip.node.id
}

locals {
  k3s_bootstrap = templatefile("${path.module}/user_data/k3s-bootstrap.sh.tftpl", {
    aws_region   = var.aws_region
    artifacts_s3 = aws_s3_bucket.artifacts.bucket
    ecr_registry = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"
    project      = var.project
  })
}

data "aws_caller_identity" "current" {}
