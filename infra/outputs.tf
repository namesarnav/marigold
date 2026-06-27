output "node_public_ip" {
  description = "Elastic IP of the k3s node. Point the app's DNS record here."
  value       = aws_eip.node.public_ip
}

output "node_instance_id" {
  description = "EC2 instance id, for `aws ssm`/console access."
  value       = aws_instance.node.id
}

output "ssh_command" {
  description = "Ready-to-run SSH command for the node."
  value       = "ssh ubuntu@${aws_eip.node.public_ip}"
}

output "kubeconfig_command" {
  description = <<-EOT
    Copies the cluster's kubeconfig locally and rewrites its server address from
    127.0.0.1 to the node's public IP, which is what makes remote kubectl work.
  EOT
  value = join(" ", [
    "ssh ubuntu@${aws_eip.node.public_ip} 'sudo cat /etc/rancher/k3s/k3s.yaml'",
    "| sed 's|127.0.0.1|${aws_eip.node.public_ip}|'",
    "> ~/.kube/marigold.yaml",
  ])
}

output "artifacts_bucket" {
  description = "S3 bucket holding uploaded PDFs (uploads/) and model artifacts (models/)."
  value       = aws_s3_bucket.artifacts.bucket
}

output "ecr_registry" {
  description = "Registry host to docker login against and tag images with."
  value       = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"
}

output "ecr_repository_urls" {
  description = "Push targets, keyed by service."
  value       = { for k, r in aws_ecr_repository.services : k => r.repository_url }
}

output "estimated_monthly_cost_usd" {
  description = <<-EOT
    Rough monthly spend for the selected instance size, against the project's
    $20 ceiling. Hardcoded us-east-1 on-demand rates — a planning aid, not a
    billing source. Check Cost Explorer for actual spend.
  EOT
  value = format(
    "~$%.2f/mo (%s instance $%.2f + 30GB gp3 $2.40 + IPv4 $3.65 + ECR/S3 ~$1.50)",
    lookup(local.instance_monthly_cost, var.instance_type, 0) + 2.40 + 3.65 + 1.50,
    var.instance_type,
    lookup(local.instance_monthly_cost, var.instance_type, 0),
  )
}

locals {
  # us-east-1 on-demand, 730 hours.
  instance_monthly_cost = {
    "t4g.nano"   = 3.07
    "t4g.micro"  = 6.13
    "t4g.small"  = 12.26
    "t4g.medium" = 24.53
    "t4g.large"  = 49.06
  }
}

output "route53_nameservers" {
  description = <<-EOT
    Point your registrar at these four nameservers.

    Nothing resolves until you do — not the site, and not the Let's Encrypt
    HTTP-01 challenge, so the certificate cannot be issued either. Delegation
    typically propagates within an hour but the TTL at the registrar governs.
  EOT
  value       = aws_route53_zone.main.name_servers
}

output "app_url" {
  description = "Where the app will be served once DNS is delegated and the deploy has run."
  value       = "https://${var.domain_name}"
}

output "github_actions_role_arn" {
  description = <<-EOT
    Set this as the AWS_DEPLOY_ROLE_ARN secret (or variable) in the GitHub
    repository. The deploy workflow assumes it via OIDC; no AWS access key is
    ever stored in GitHub.
  EOT
  value       = aws_iam_role.github_actions.arn
}

output "ses_sandbox_reminder" {
  description = "Deliberately an output, not a comment: it is the step most likely to be forgotten."
  value = join(" ", [
    "SES is in SANDBOX mode until you request production access.",
    "Until granted, it will only deliver to individually verified addresses and",
    "will silently drop signup verification emails to real users.",
    "Request it in the SES console for region ${var.aws_region}; approval is usually <24h.",
  ])
}
