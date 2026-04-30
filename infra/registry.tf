# One ECR repository per deployable service. CI builds ARM images, pushes here,
# and the k3s node pulls them.

resource "aws_ecr_repository" "services" {
  for_each = toset(var.ecr_repositories)

  name                 = "${var.project}/${each.key}"
  image_tag_mutability = "MUTABLE" # CI moves a "latest" tag alongside the commit SHA.

  image_scanning_configuration {
    # Free on push, and the ML image pulls a large dependency tree worth
    # watching for known CVEs.
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name = "${var.project}-${each.key}"
  }
}

# Without lifecycle policies, every merge's image is stored and billed forever.
# ECR storage is $0.10/GB-month and these images are hundreds of MB each, so
# this is the difference between cents and dollars per month.
resource "aws_ecr_lifecycle_policy" "services" {
  for_each = aws_ecr_repository.services

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after ${var.ecr_untagged_expiry_days} days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.ecr_untagged_expiry_days
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep only the newest ${var.ecr_max_tagged_images} tagged images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = var.ecr_max_tagged_images
        }
        action = { type = "expire" }
      },
    ]
  })
}
