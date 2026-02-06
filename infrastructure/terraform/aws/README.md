# AWS Terraform Infrastructure for Incident Copilot

This directory contains production-ready Terraform configuration for deploying the Incident Copilot application on AWS.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                    VPC                                       │
│                              (10.0.0.0/16)                                   │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        Public Subnets                                  │ │
│  │  ┌──────────────────┐                                                  │ │
│  │  │   ALB (HTTP/S)   │◄──── Internet Gateway                           │ │
│  │  │                  │                                                  │ │
│  │  └────────┬─────────┘                                                  │ │
│  └───────────┼────────────────────────────────────────────────────────────┘ │
│              │                                                               │
│  ┌───────────▼────────────────────────────────────────────────────────────┐ │
│  │                        Private Subnets                                 │ │
│  │                                                                        │ │
│  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────────────────────┐  │ │
│  │  │ ECS Fargate │   │ ECS Fargate │   │      ElastiCache Redis      │  │ │
│  │  │   Task 1    │   │   Task N    │   │      (Multi-node HA)        │  │ │
│  │  └──────┬──────┘   └──────┬──────┘   └─────────────────────────────┘  │ │
│  │         │                 │                                            │ │
│  │         └────────┬────────┘                                            │ │
│  │                  │           NAT Gateway(s)                            │ │
│  └──────────────────┼─────────────────────────────────────────────────────┘ │
│                     │                                                        │
│  ┌──────────────────▼─────────────────────────────────────────────────────┐ │
│  │                      Database Subnets (Isolated)                       │ │
│  │                                                                        │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │ │
│  │  │                    RDS PostgreSQL (Multi-AZ)                    │  │ │
│  │  │                    Encrypted at rest (KMS)                      │  │ │
│  │  └─────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components

### Networking (VPC Module)
- VPC with public, private, and database subnets across 3 AZs
- Internet Gateway for public internet access
- NAT Gateway(s) for private subnet outbound access
- VPC Flow Logs for network monitoring
- VPC Endpoints for AWS services (ECR, CloudWatch, Secrets Manager, SSM)

### Compute (ECS Module)
- ECS Fargate cluster with Container Insights
- Auto-scaling based on CPU, memory, and request count
- Application Load Balancer with access logging
- Task execution and task roles with least-privilege permissions
- Support for ECS Exec for debugging

### Database (RDS Module)
- PostgreSQL 16 with pgvector extension support
- Multi-AZ deployment for high availability
- Encrypted storage with customer-managed KMS key
- Enhanced monitoring and Performance Insights
- Automated backups with configurable retention
- CloudWatch alarms for CPU, storage, and connections

### Cache (ElastiCache Module)
- Redis 7 replication group
- Multi-node configuration with automatic failover
- Encryption at rest and in transit
- Auth token stored in Secrets Manager
- CloudWatch alarms for CPU, memory, and evictions

### Security
- Security groups with least-privilege access
- No public access to RDS or Redis
- VPC endpoints to avoid data traversing public internet
- Encryption at rest for all data stores
- Secrets stored in AWS Secrets Manager

## Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **Terraform** >= 1.5.0
3. **AWS Account** with permissions to create all resources
4. **ECR Repository** for Docker images
5. **SSM Parameters** for application secrets (see below)

## Quick Start

### 1. Initialize Terraform

```bash
cd infrastructure/terraform/aws
terraform init
```

### 2. Create SSM Parameters for Secrets

Before deploying, create the required SSM parameters:

```bash
# OpenAI API Key
aws ssm put-parameter \
  --name "/incident-copilot/prod/openai-api-key" \
  --type "SecureString" \
  --value "your-openai-api-key"

# Anthropic API Key (if using Claude)
aws ssm put-parameter \
  --name "/incident-copilot/prod/anthropic-api-key" \
  --type "SecureString" \
  --value "your-anthropic-api-key"

# PagerDuty Token
aws ssm put-parameter \
  --name "/incident-copilot/prod/pagerduty-token" \
  --type "SecureString" \
  --value "your-pagerduty-token"

# Slack Bot Token
aws ssm put-parameter \
  --name "/incident-copilot/prod/slack-bot-token" \
  --type "SecureString" \
  --value "your-slack-bot-token"
```

### 3. Configure Variables

```bash
# Copy example variables
cp terraform.tfvars.example terraform.tfvars

# Edit for your environment
vim terraform.tfvars
```

### 4. Plan and Apply

```bash
# Review the plan
terraform plan -var-file=environments/prod.tfvars

# Apply changes
terraform apply -var-file=environments/prod.tfvars
```

## Environments

Pre-configured environments are available:

| Environment | File | Description |
|-------------|------|-------------|
| Development | `environments/dev.tfvars` | Cost-optimized, single NAT, smaller instances |
| Staging | `environments/staging.tfvars` | Pre-production testing, Multi-AZ RDS, 2-node Redis |
| Production | `environments/prod.tfvars` | Full HA setup, Multi-AZ everywhere, larger instances |

```bash
# Deploy development
terraform apply -var-file=environments/dev.tfvars

# Deploy staging
terraform apply -var-file=environments/staging.tfvars

# Deploy production
terraform apply -var-file=environments/prod.tfvars
```

## Remote State (Recommended)

For team collaboration, configure S3 backend:

1. Create S3 bucket and DynamoDB table:

```bash
aws s3 mb s3://incident-copilot-terraform-state
aws dynamodb create-table \
  --table-name incident-copilot-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

2. Uncomment backend configuration in `versions.tf`

3. Run `terraform init -migrate-state`

## Outputs

After successful deployment:

```bash
# Get ALB URL
terraform output application_url

# Get all outputs
terraform output

# Get sensitive outputs
terraform output -json connection_strings
```

## Updating the Application

To deploy a new container image:

```bash
# Update the container_image variable
terraform apply -var="container_image=123456789012.dkr.ecr.us-west-2.amazonaws.com/incident-copilot:v2.0.0"
```

Or force a new deployment through ECS:

```bash
aws ecs update-service \
  --cluster incident-copilot-prod-cluster \
  --service incident-copilot-prod-service \
  --force-new-deployment
```

## Cost Estimation

Estimated monthly costs (us-west-2, production configuration):

| Resource | Configuration | Est. Monthly Cost |
|----------|--------------|-------------------|
| ECS Fargate | 3x (1 vCPU, 2GB) | ~$90 |
| ALB | 1 load balancer | ~$20 |
| RDS | db.r6g.large Multi-AZ | ~$300 |
| ElastiCache | 3x cache.r6g.large | ~$400 |
| NAT Gateway | 3 gateways | ~$100 |
| VPC Endpoints | 5 interface endpoints | ~$50 |
| Data Transfer | ~100GB | ~$10 |
| **Total** | | **~$970/month** |

Development environment: ~$150/month

## Security Best Practices

1. **Enable MFA** on AWS accounts
2. **Use IAM roles** instead of access keys where possible
3. **Rotate secrets** regularly using Secrets Manager rotation
4. **Enable CloudTrail** for API auditing
5. **Review security groups** periodically
6. **Enable AWS Config** for compliance monitoring

## Troubleshooting

### ECS Tasks Not Starting

```bash
# Check service events
aws ecs describe-services \
  --cluster incident-copilot-prod-cluster \
  --services incident-copilot-prod-service

# Check task logs
aws logs tail /ecs/incident-copilot-prod/app --follow
```

### Database Connection Issues

```bash
# Verify security groups allow traffic
aws ec2 describe-security-group-rules \
  --filter Name=group-id,Values=sg-xxxxx
```

### Using ECS Exec

```bash
# Enable ECS Exec for debugging
aws ecs execute-command \
  --cluster incident-copilot-prod-cluster \
  --task <task-id> \
  --container app \
  --interactive \
  --command "/bin/sh"
```

## Cleanup

To destroy all resources:

```bash
# CAUTION: This will destroy all resources including databases!
terraform destroy -var-file=environments/prod.tfvars
```

**Note**: If `db_deletion_protection = true`, you must first disable it:

```bash
aws rds modify-db-instance \
  --db-instance-identifier incident-copilot-prod-postgres \
  --no-deletion-protection
```

## Contributing

1. Make changes in a feature branch
2. Run `terraform fmt` and `terraform validate`
3. Create a pull request with the plan output
4. Get approval before applying

## License

This infrastructure code is part of the Incident Copilot project.
