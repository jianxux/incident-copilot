# Terraform Backend Configuration
# 
# This file configures the S3 backend for storing Terraform state remotely.
# This enables team collaboration and state locking via DynamoDB.
#
# SETUP INSTRUCTIONS:
# 1. Create an S3 bucket for state storage (enable versioning)
# 2. Create a DynamoDB table for state locking
# 3. Uncomment the backend configuration below and update values
#
# AWS CLI commands to create the backend resources:
#
# S3 Bucket:
#   aws s3api create-bucket \
#     --bucket incident-copilot-terraform-state \
#     --region us-west-2 \
#     --create-bucket-configuration LocationConstraint=us-west-2
#
#   aws s3api put-bucket-versioning \
#     --bucket incident-copilot-terraform-state \
#     --versioning-configuration Status=Enabled
#
#   aws s3api put-bucket-encryption \
#     --bucket incident-copilot-terraform-state \
#     --server-side-encryption-configuration \
#       '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
#
# DynamoDB Table:
#   aws dynamodb create-table \
#     --table-name incident-copilot-terraform-locks \
#     --attribute-definitions AttributeName=LockID,AttributeType=S \
#     --key-schema AttributeName=LockID,KeyType=HASH \
#     --billing-mode PAY_PER_REQUEST \
#     --region us-west-2

# Uncomment and configure for production use:
# terraform {
#   backend "s3" {
#     bucket         = "incident-copilot-terraform-state"
#     key            = "aws/terraform.tfstate"
#     region         = "us-west-2"
#     encrypt        = true
#     dynamodb_table = "incident-copilot-terraform-locks"
#     
#     # Optional: Use a specific profile
#     # profile = "production"
#   }
# }

# For local development, Terraform will use the local backend by default.
# The state file will be stored in terraform.tfstate in this directory.
