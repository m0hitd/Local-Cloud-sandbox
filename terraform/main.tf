terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

variable "localstack_endpoint" {
  description = "LocalStack gateway URL"
  type        = string
  default     = "http://localhost:4566"
}

variable "fake_gcs_endpoint" {
  description = "fake-gcs-server URL, without the /storage/v1 suffix"
  type        = string
  default     = "http://localhost:4443"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "gcp_project_id" {
  type    = string
  default = "local-analytics-project"
}

# Dummy credentials and skip flags keep the providers from contacting real clouds
provider "aws" {
  region     = var.aws_region
  access_key = "test"
  secret_key = "test"

  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true

  endpoints {
    ec2            = var.localstack_endpoint
    iam            = var.localstack_endpoint
    lambda         = var.localstack_endpoint
    dynamodb       = var.localstack_endpoint
    s3             = var.localstack_endpoint
    secretsmanager = var.localstack_endpoint
    sqs            = var.localstack_endpoint
    sts            = var.localstack_endpoint
  }

  default_tags {
    tags = {
      Project     = "local-multicloud-sandbox"
      Environment = "local"
      ManagedBy   = "terraform"
    }
  }
}

provider "google" {
  project                     = var.gcp_project_id
  access_token                = "local-fake-token"
  storage_custom_endpoint     = "${var.fake_gcs_endpoint}/storage/v1/"
  skip_credentials_validation = true
}

output "vm_instance_ids" {
  value = aws_instance.sandbox_vm[*].id
}

output "s3_artifacts_bucket" {
  value = aws_s3_bucket.artifacts.bucket
}

output "gcs_artifacts_bucket" {
  value = google_storage_bucket.gcs_artifacts.name
}

output "orders_table_name" {
  value = aws_dynamodb_table.orders.name
}
