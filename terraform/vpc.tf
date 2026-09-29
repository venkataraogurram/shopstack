data "aws_availability_zones" "available" {
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.7"

  name = var.project
  cidr = var.vpc_cidr
  azs  = local.azs

  # Nodes and pods live in private subnets; only the ALB is public.
  private_subnets = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets  = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, 100 + i)]

  enable_nat_gateway   = true
  single_nat_gateway   = true # one NAT keeps the demo cheap; use one per AZ in production
  enable_dns_hostnames = true
  enable_dns_support   = true

  # Subnet discovery tags read by the AWS Load Balancer Controller
  public_subnet_tags = {
    "kubernetes.io/role/elb" = "1"
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = "1"
  }
}
