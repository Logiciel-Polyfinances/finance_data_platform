terraform {
  # The S3 backend's use_lockfile (below) needs 1.10+.
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Shared Polyfinances state bucket; one key per project.
  backend "s3" {
    bucket       = "polyfinances-terraform-state-437848352148"
    key          = "finance_data_platform/terraform.tfstate"
    region       = "ca-central-1"
    use_lockfile = true
  }
}
