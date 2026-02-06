# Production environment configuration

project_name = "incident-copilot"
environment  = "prod"
aws_region   = "us-west-2"

# VPC - full production setup across 3 AZs
vpc_cidr           = "10.0.0.0/16"
availability_zones = ["us-west-2a", "us-west-2b", "us-west-2c"]

public_subnet_cidrs   = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
private_subnet_cidrs  = ["10.0.11.0/24", "10.0.12.0/24", "10.0.13.0/24"]
database_subnet_cidrs = ["10.0.21.0/24", "10.0.22.0/24", "10.0.23.0/24"]

# High availability - NAT gateway per AZ
enable_nat_gateway = true
single_nat_gateway = false

# ECS - production sizing
ecs_task_cpu      = 1024
ecs_task_memory   = 2048
ecs_desired_count = 3
ecs_min_count     = 2
ecs_max_count     = 20

container_port    = 8000
container_image   = "incident-copilot:latest"
health_check_path = "/health"

# RDS - production instance with Multi-AZ
db_instance_class          = "db.r6g.large"
db_allocated_storage       = 100
db_max_allocated_storage   = 500
db_name                    = "incident_copilot"
db_username                = "postgres"
db_engine_version          = "16.1"
db_multi_az                = true
db_backup_retention_period = 30
db_deletion_protection     = true
db_skip_final_snapshot     = false

# Redis - production cluster
redis_node_type          = "cache.r6g.large"
redis_num_cache_nodes    = 3
redis_engine_version     = "7.1"
redis_automatic_failover = true
redis_at_rest_encryption = true
redis_transit_encryption = true

# ALB - HTTPS with SSL certificate
# alb_ssl_certificate_arn = "arn:aws:acm:us-west-2:ACCOUNT:certificate/CERT_ID"
alb_ssl_certificate_arn = ""
alb_internal            = false

# Logging
log_retention_days        = 90
enable_container_insights = true

additional_tags = {
  Environment  = "production"
  Compliance   = "soc2"
  DataClass    = "confidential"
}
