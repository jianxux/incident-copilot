# Staging environment configuration
# Balanced between dev (cost) and prod (reliability)

project_name = "incident-copilot"
environment  = "staging"
aws_region   = "us-west-2"

# VPC - 2 AZs for staging (balance cost vs redundancy)
vpc_cidr           = "10.20.0.0/16"
availability_zones = ["us-west-2a", "us-west-2b"]

public_subnet_cidrs   = ["10.20.1.0/24", "10.20.2.0/24"]
private_subnet_cidrs  = ["10.20.11.0/24", "10.20.12.0/24"]
database_subnet_cidrs = ["10.20.21.0/24", "10.20.22.0/24"]

# Single NAT gateway for cost optimization
enable_nat_gateway = true
single_nat_gateway = true

# ECS - medium sizing, closer to prod for realistic testing
ecs_task_cpu      = 512
ecs_task_memory   = 1024
ecs_desired_count = 2
ecs_min_count     = 1
ecs_max_count     = 6

container_port    = 8000
container_image   = "incident-copilot:staging"
health_check_path = "/health"

# RDS - production-like but smaller instance class
db_instance_class          = "db.t3.medium"
db_allocated_storage       = 50
db_max_allocated_storage   = 200
db_name                    = "incident_copilot"
db_username                = "postgres"
db_engine_version          = "16.1"
db_multi_az                = true  # Enable for staging to catch multi-AZ issues
db_backup_retention_period = 7
db_deletion_protection     = false
db_skip_final_snapshot     = false

# Redis - 2-node cluster for failover testing
redis_node_type          = "cache.t3.medium"
redis_num_cache_nodes    = 2
redis_engine_version     = "7.1"
redis_automatic_failover = true
redis_at_rest_encryption = true
redis_transit_encryption = true  # Enable to test TLS connections

# ALB
alb_ssl_certificate_arn = ""
alb_internal            = false

# Logging - moderate retention
log_retention_days        = 30
enable_container_insights = true

additional_tags = {
  Environment = "staging"
  Purpose     = "pre-production-testing"
}
