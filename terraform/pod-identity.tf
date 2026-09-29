# One IAM role per workload, bound to a Kubernetes ServiceAccount with EKS Pod
# Identity. Pods receive short-lived credentials for exactly the actions and
# tables they need; the node role carries no application permissions.

module "cart_pod_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "~> 2.9"

  name            = "${var.project}-cart"
  use_name_prefix = false

  attach_custom_policy = true
  policy_statements = [{
    sid       = "CartTable"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:DescribeTable"]
    resources = [aws_dynamodb_table.carts.arn]
  }]

  associations = {
    cart = {
      cluster_name    = module.eks.cluster_name
      namespace       = var.app_namespace
      service_account = "cart"
    }
  }
}

module "order_pod_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "~> 2.9"

  name            = "${var.project}-order"
  use_name_prefix = false

  attach_custom_policy = true
  policy_statements = [{
    sid       = "OrdersTable"
    actions   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:DescribeTable"]
    resources = [aws_dynamodb_table.orders.arn]
  }]

  associations = {
    order = {
      cluster_name    = module.eks.cluster_name
      namespace       = var.app_namespace
      service_account = "order"
    }
  }
}

# AWS Load Balancer Controller (installed with Helm, see scripts/install-addons.sh)
module "lb_controller_pod_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "~> 2.9"

  name            = "${var.project}-aws-load-balancer-controller"
  use_name_prefix = false

  attach_aws_lb_controller_policy = true

  associations = {
    controller = {
      cluster_name    = module.eks.cluster_name
      namespace       = "kube-system"
      service_account = "aws-load-balancer-controller"
    }
  }
}

# CloudWatch Observability add-on (Container Insights + Fluent Bit log shipping).
# The association itself is declared on the add-on in eks.tf.
module "cloudwatch_observability_pod_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "~> 2.9"

  name            = "${var.project}-cloudwatch-observability"
  use_name_prefix = false

  attach_aws_cloudwatch_observability_policy = true
}
