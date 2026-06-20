# DNS and email identity.
#
# The domain is registered with an external registrar, so this config creates
# the hosted zone and Terraform manages the records inside it. Nothing resolves
# until the registrar's nameservers are pointed at the four values in the
# `route53_nameservers` output — that delegation is a manual step at the
# registrar and is the gate on everything downstream, including Let's Encrypt
# issuance (the HTTP-01 challenge needs the name to resolve to this node).

resource "aws_route53_zone" "main" {
  name    = var.domain_name
  comment = "Managed by Terraform for ${var.project}"

  tags = {
    Name = "${var.project}-zone"
  }
}

# Apex -> the node's Elastic IP. A plain A record rather than an alias, because
# an alias target must be an AWS-managed resource and this points at an EC2
# instance's address.
resource "aws_route53_record" "apex" {
  zone_id = aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "A"
  ttl     = 300
  records = [aws_eip.node.public_ip]
}

resource "aws_route53_record" "www" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "www.${var.domain_name}"
  type    = "CNAME"
  ttl     = 300
  records = [var.domain_name]
}

# --- SES: sending identity for verification and password-reset email ----------
#
# IMPORTANT: none of this lifts the SES sandbox. A brand-new SES account can
# only deliver to addresses it has separately verified, so signup verification
# emails to real users are accepted by the API and silently dropped. Production
# access is a support request in the SES console and is the single step in this
# whole deployment with a queue in front of it (typically under 24h) — file it
# early. Until it is granted, run with EMAIL_BACKEND=console.

resource "aws_ses_domain_identity" "main" {
  domain = var.domain_name
}

resource "aws_ses_domain_dkim" "main" {
  domain = aws_ses_domain_identity.main.domain
}

# Proves ownership of the domain to SES.
resource "aws_route53_record" "ses_verification" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "_amazonses.${var.domain_name}"
  type    = "TXT"
  ttl     = 600
  records = [aws_ses_domain_identity.main.verification_token]
}

# DKIM signing. SES always issues exactly three CNAMEs; without all three,
# messages go unsigned and land in spam.
resource "aws_route53_record" "ses_dkim" {
  count = 3

  zone_id = aws_route53_zone.main.zone_id
  name    = "${aws_ses_domain_dkim.main.dkim_tokens[count.index]}._domainkey.${var.domain_name}"
  type    = "CNAME"
  ttl     = 600
  records = ["${aws_ses_domain_dkim.main.dkim_tokens[count.index]}.dkim.amazonses.com"]
}

# SPF. `~all` (softfail) rather than `-all`: a hard fail on a misconfiguration
# means silently undeliverable signup emails, which is worse than a spam-folder
# risk while this is being set up.
resource "aws_route53_record" "spf" {
  zone_id = aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "TXT"
  ttl     = 600
  records = ["v=spf1 include:amazonses.com ~all"]
}

# DMARC in monitor-only mode (p=none). Reporting without enforcement is the
# right starting point: enforcing before DKIM and SPF are confirmed aligned is
# how a domain starts rejecting its own mail.
resource "aws_route53_record" "dmarc" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "_dmarc.${var.domain_name}"
  type    = "TXT"
  ttl     = 600
  records = ["v=DMARC1; p=none; rua=mailto:${var.dmarc_report_email}"]
}
