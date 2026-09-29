module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.26"

  name               = var.project
  kubernetes_version = var.kubernetes_version

  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.private_subnets

  endpoint_public_access       = true
  endpoint_public_access_cidrs = var.endpoint_public_access_cidrs
  endpoint_private_access      = true

  # Whoever runs terraform apply becomes cluster admin through an EKS access entry
  enable_cluster_creator_admin_permissions = true
  authentication_mode                      = "API"

  enabled_log_types                      = ["api", "audit", "authenticator"]
  cloudwatch_log_group_retention_in_days = 7
  deletion_protection                    = false

  addons = {
    vpc-cni = {
      before_compute = true
      most_recent    = true
      # Prefix delegation hands each ENI /28 prefixes instead of single IPs,
      # lifting the pod ceiling on small instances (t3.medium: 17 -> 110).
      # Without it an HPA scale-out stalled with "0/2 nodes: Too many pods".
      configuration_values = jsonencode({
        env = {
          ENABLE_PREFIX_DELEGATION = "true"
          WARM_PREFIX_TARGET       = "1"
        }
      })
    }
    kube-proxy = {
      before_compute = true
      most_recent    = true
    }
    coredns = {
      most_recent = true
    }
    eks-pod-identity-agent = {
      before_compute = true
      most_recent    = true
    }
    metrics-server = {
      most_recent = true
    }
    amazon-cloudwatch-observability = {
      most_recent = true
      # v6+ enables Application Signals "auto-monitor" by default, which mutates
      # every pod to inject OpenTelemetry init containers. Those containers do
      # not satisfy the "restricted" Pod Security Standard enforced on the
      # shopstack namespace, so pod creation is rejected. Keep Container
      # Insights + log shipping; turn off automatic instrumentation.
      configuration_values = jsonencode({
        manager = {
          applicationSignals = {
            autoMonitor = {
              monitorAllServices = false
            }
          }
        }
      })
      pod_identity_association = [{
        role_arn        = module.cloudwatch_observability_pod_identity.iam_role_arn
        service_account = "cloudwatch-agent"
      }]
    }
  }

  eks_managed_node_groups = {
    general = {
      name           = "${var.project}-general"
      ami_type       = "AL2023_x86_64_STANDARD"
      instance_types = var.node_instance_types
      capacity_type  = "ON_DEMAND"

      min_size     = var.node_group_size.min
      max_size     = var.node_group_size.max
      desired_size = var.node_group_size.desired

      subnet_ids = module.vpc.private_subnets

      # Pair with VPC CNI prefix delegation above: kubelet must also be told it
      # may schedule more pods than the ENI/IP formula allows.
      cloudinit_pre_nodeadm = [{
        content_type = "application/node.eks.aws"
        content      = <<-EOT
          ---
          apiVersion: node.eks.aws/v1alpha1
          kind: NodeConfig
          spec:
            kubelet:
              config:
                maxPods: 110
        EOT
      }]

      metadata_options = {
        http_tokens                 = "required" # IMDSv2 only
        http_put_response_hop_limit = 1          # pods cannot reach the node's instance role
      }

      update_config = {
        max_unavailable_percentage = 33
      }

      labels = {
        workload = "general"
      }
    }
  }

  tags = {
    Name = var.project
  }
}
