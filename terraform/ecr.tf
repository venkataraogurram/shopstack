locals {
  services = toset(["catalog", "cart", "order"])
}

resource "aws_ecr_repository" "service" {
  for_each = local.services

  name                 = "${var.project}/${each.key}"
  image_tag_mutability = "IMMUTABLE" # a tag always points at the same digest
  force_delete         = true        # demo only: allow terraform destroy with images present

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "service" {
  for_each   = aws_ecr_repository.service
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep the 10 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
