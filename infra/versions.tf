terraform {
  required_version = ">= 1.10"

  cloud {
    organization = "ooad-lab7"

    workspaces {
      name = "successfulsuccess-dev"
    }
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      PROJECT_NAME = var.project_name
      ManagedBy    = "terraform"
      Environment  = "dev"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
