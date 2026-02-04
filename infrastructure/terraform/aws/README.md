# Incident Copilot - AWS Infrastructure

Production-ready Terraform infrastructure for deploying the Incident Copilot application on AWS.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                    VPC                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         Public Subnets (3 AZs)                        │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐       │   │
│  │  │   NAT Gateway   │  │   NAT Gateway   │  │   NAT Gateway   │       │   │
│  │  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘       │   │
│  │           │                    │                    │                 │   │
│  │  ┌────────┴────────────────────┴────────────────────┴────────┐       │   │
│  │  │              Application Load Balancer (ALB)               │       │   │
│  │  └────────────────────────────┬───────────────────────────────┘       │   │
│  └───────────────────────────────┼───────────────────────────────────────┘   │
│                                  │                                           │
│  ┌───────────────────────────────┼───────────────────────────────────────┐   │
│  │                Private Subnets (3 AZs)                                 │   │
│  │                               │                                        │   │
│  │  ┌────────────────────────────┴─────────────────────────────────┐     │   │
│  │  │                    ECS Fargate Cluster                        │     │   │
│  │  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                    │     │   │
│  │  │  │  Task 1  │  │  Task 2  │  │  Task N  │  (Auto-scaling)    │     │   │
│  │  │  └──────────┘  └──────────┘  └──────────┘                    │     │   │
│  │  └──────────────────────────────────────────────────────────────┘     │   │
│  │                               │                                        │   │
│  │  ┌────────────────────────────┴─────────────────────────────────┐     │   │
│  │  │                    ElastiCache Redis                          │     │   │
│  │  │  ┌──────────┐  ┌──────────┐                                  │     │   │
│  │  │  │ Primary  │  │ Replica  │  (Multi-AZ)                      │     │   │
│  │  │  └──────────┘  └──────────┘                                  │     │   │
│  │  └──────────────────────────────────────────────────────────────┘     │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │                      Database Subnets (3 AZs)                          │   │
│  │  ┌──────────────────────────────────────────────────────────────┐     │   │
│  │  │                    RDS PostgreSQL                             │     │   │
│  │  │  ┌──────────┐  ┌──────────┐                                  │     │   │
│  │  │  │ Primary  │  │ Standby  │  (Multi-AZ optional)             │     │   │
│  │  │  └──────────┘  └──────────┘                                  │     │   │
│  │  └──────────────────────────────────────────────────────────────┘     │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Modules

### VPC (`modules/vpc/`)
- VPC with customizable CIDR
- Public, private, and database subnets across 3 AZs
- Internet Gateway and NAT Gateways (single or per-AZ)
- VPC Endpoints for ECR, CloudWatch Logs, S3, Secrets Manager
- VPC Flow Logs

### ECS (`modules/ecs/`)
- ECS Cluster with Fargate capacity providers
- Task definitions with configurable CPU/memory
- ECS Service with auto-scaling (CPU, memory, request count)
- Application Load Balancer with HTTPS support
- CloudWatch log groups
- IAM roles for task execution and application

### RDS (`modules/rds/`)
- PostgreSQL RDS instance
- Multi-AZ support (optional)
- Automated backups and snapshots
- Performance Insights and Enhanced Monitoring
- Secrets Manager for credentials
- CloudWatch alarms

### Redis (`modules/redis/`)
- ElastiCache Redis cluster
- Multi-AZ support
- Encryption at rest and in transit
- Automated backups
- CloudWatch alarms

## Quick Start

### Prerequisites
- Terraform >= 1.5.0
- AWS CLI configured with appropriate credentials
- An AWS account with necessary permissions

### 1. Initialize Terraform

```bash
cd infrastructure/terraform/aws
terraform init
```

### 2. Configure Variables

```bash
# Copy the example file
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
vim terraform.tfvars
```

### 3. Plan and Apply

```bash
# Review changes
terraform plan

# Apply infrastructure
terraform apply
```

### 4. Environment-Specific Deployment

```bash
# For dev
terraform plan -var-file=environments/dev/terraform.tfvars
terraform apply -var-file=environments/dev/terraform.tfvars

# For staging
terraform plan -var-file=environments/staging/terraform.tfvars
terraform apply -var-file=environments/staging/terraform.tfvars

# For production
terraform plan -var-file=environments/prod/terraform.tfvars
terraform apply -var-file=environments/prod/terraform.tfvars
```

## Remote State Setup

For team collaboration, configure the S3 backend:

1. Create S3 bucket and DynamoDB table (see `backend.tf` for commands)
2. Uncomment the backend configuration in `backend.tf`
3. Run `terraform init` to migrate state

## Cost Estimates

| Environment | Monthly Cost (approx.) |
|------------|------------------------|
| Dev        | $50-100                |
| Staging    | $150-300               |
| Prod       | $500-1000+             |

*Costs vary based on usage and region. Use AWS Cost Calculator for precise estimates.*

## Security Considerations

- All data encrypted at rest and in transit
- Database credentials stored in Secrets Manager
- VPC endpoints reduce exposure to public internet
- Security groups follow least-privilege principle
- VPC Flow Logs enabled for network monitoring

## Outputs

After applying, Terraform outputs include:
- VPC and subnet IDs
- ECS cluster and service names
- ALB DNS name (application URL)
- RDS endpoint and credentials secret ARN
- Redis endpoint

```bash
# View outputs
terraform output

# Get specific output
terraform output alb_dns_name
terraform output db_secret_arn
```

## Troubleshooting

### ECS Tasks Not Starting
- Check CloudWatch logs: `/ecs/<cluster>/<service>`
- Verify container image exists in ECR
- Check security group rules

### Database Connection Issues
- Verify security group allows traffic from ECS
- Check Secrets Manager secret for correct credentials
- Ensure database subnet routing is correct

### Performance Issues
- Enable Container Insights for ECS metrics
- Enable Performance Insights for RDS
- Review CloudWatch alarms

## License

MIT License - See [LICENSE](../../../LICENSE) for details.
