resource "aws_security_group" "node" {
  name        = "${var.project}-node"
  description = "Single k3s node: public HTTP/HTTPS, admin-only SSH and Kubernetes API"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${var.project}-node"
  }
}

# --- Public ingress -----------------------------------------------------------
# Only the web listeners are open to the world. Traefik ships with k3s and
# terminates ingress on these two ports.

resource "aws_vpc_security_group_ingress_rule" "http" {
  security_group_id = aws_security_group.node.id
  description       = "HTTP (redirects to HTTPS, and serves ACME http-01 challenges)"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  security_group_id = aws_security_group.node.id
  description       = "HTTPS"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

# --- Admin ingress ------------------------------------------------------------
# Restricted to var.ssh_allowed_cidr. The Kubernetes API in particular is
# effectively root on the cluster, so it is never opened broadly.

resource "aws_vpc_security_group_ingress_rule" "ssh" {
  security_group_id = aws_security_group.node.id
  description       = "SSH, admin only"
  cidr_ipv4         = var.ssh_allowed_cidr
  from_port         = 22
  to_port           = 22
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "kube_api" {
  security_group_id = aws_security_group.node.id
  description       = "k3s / Kubernetes API for kubectl and CI deploys, admin only"
  cidr_ipv4         = var.ssh_allowed_cidr
  from_port         = 6443
  to_port           = 6443
  ip_protocol       = "tcp"
}

# Postgres (5432) and Redis (6379) are intentionally absent: both run as
# in-cluster services reached over the pod network, never from outside the node.

resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.node.id
  description       = "Outbound: ECR pulls, Gemini API, OS packages"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_key_pair" "admin" {
  key_name   = "${var.project}-admin"
  public_key = var.ssh_public_key
}
