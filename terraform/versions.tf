terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Local state keeps the demo self-contained. For a shared environment switch
  # to the S3 backend (Terraform >= 1.10 locks natively with use_lockfile):
  #
  # backend "s3" {
  #   bucket       = "<state-bucket>"
  #   key          = "shopstack/terraform.tfstate"
  #   region       = "us-east-1"
  #   encrypt      = true
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
