output "region" {
  value = var.region
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "vpc_id" {
  value = module.vpc.vpc_id
}

output "ecr_repository_urls" {
  description = "Image repository per service"
  value       = { for k, r in aws_ecr_repository.service : k => r.repository_url }
}

output "dynamodb_tables" {
  value = {
    carts  = aws_dynamodb_table.carts.name
    orders = aws_dynamodb_table.orders.name
  }
}

output "pod_identity_role_arns" {
  value = {
    cart          = module.cart_pod_identity.iam_role_arn
    order         = module.order_pod_identity.iam_role_arn
    lb_controller = module.lb_controller_pod_identity.iam_role_arn
    cloudwatch    = module.cloudwatch_observability_pod_identity.iam_role_arn
  }
}

output "github_actions_role_arn" {
  description = "Set this as the AWS_ROLE_ARN repository variable in GitHub"
  value       = aws_iam_role.github_actions.arn
}

output "configure_kubectl" {
  value = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}
