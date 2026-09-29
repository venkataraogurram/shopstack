variable "region" {
  description = "AWS region for every resource"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Name prefix for all resources"
  type        = string
  default     = "shopstack"
}

variable "environment" {
  description = "Deployment environment label"
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "CIDR block for the cluster VPC"
  type        = string
  default     = "10.20.0.0/16"
}

variable "kubernetes_version" {
  description = "EKS control plane version"
  type        = string
  default     = "1.34"
}

variable "node_instance_types" {
  description = "Instance types for the managed node group"
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_group_size" {
  description = "Managed node group sizing"
  type = object({
    min     = number
    max     = number
    desired = number
  })
  default = {
    min     = 2
    max     = 4
    desired = 2
  }
}

variable "endpoint_public_access_cidrs" {
  description = "CIDRs allowed to reach the public EKS API endpoint. Narrow this to your office/VPN range."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "github_repository" {
  description = "GitHub repository (owner/name) allowed to assume the CI role via OIDC"
  type        = string
  default     = "venkataraogurram/shopstack"
}

variable "app_namespace" {
  description = "Kubernetes namespace the application is deployed to"
  type        = string
  default     = "shopstack"
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub OIDC provider. Set to false if the account already has one (it is account-wide, one per URL)."
  type        = bool
  default     = true
}

variable "github_owner_id" {
  description = "Numeric GitHub owner ID (gh api users/<owner> -q .id); part of the immutable OIDC subject"
  type        = number
  default     = 37859333
}

variable "github_repository_id" {
  description = "Numeric GitHub repository ID (gh api repos/<owner>/<repo> -q .id); part of the immutable OIDC subject"
  type        = number
  default     = 1395386103
}



