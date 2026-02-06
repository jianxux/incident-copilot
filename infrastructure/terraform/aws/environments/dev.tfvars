# Development environment configuration

project_name = "incident-copilot"
environment  = "dev"
aws_region   = "us-west-2"

# VPC - smaller for dev
vpc_cidr           = "10.10.0.0/16"
availability_zones = ["us-west-2a", "us-west-2b"]

public_subnet_cidrs   = ["10.10.1.0/24", "10.10.2.0/24"]
private_subnet_cidrs  = ["10.10.11.0/24", "10.10.12.0/24"]
database_subnet_cidrs = ["10.10.21.0/24", "10.10.22.0/24"]

# Cost optimization - single NAT gateway
enable_nat_gateway = true
single_nat_gateway = true

# ECS - smaller instances for dev
ecs_task_cpu      = 256
ecs_task_memory   = 512
ecs_desired_count = 1
ecs_min_count     = 1
ecs_max_count     = 3

container_port    = 8000
container_image   = "incident-copilot:dev"
health_check_path = "/health"

# RDS - smaller instance, no multi-AZ
db_instance_class          = "db.t3.micro"
db_allocated_storage       = 20
db_max_allocated_storage   = 50
db_name                    = "incident_copilot"
db_username                = "postgres"
db_engine_version          = "16.1"
db_multi_az                = false
db_backup_retention_period = 3
db_deletion_protection     = false
db_skip_final_snapshot     = true

# Redis - smaller instance
redis_node_type          = "cache.t3.micro"
redis_num_cache_nodes    = 1
redis_engine_version     = "7.1"
redis_automatic_failover = false
redis_at_rest_encryption = true
redis_transit_encryption = false

# ALB
alb_ssl_certificate_arn = ""
alb_internal            = false

# Logging
log_retention_days        = 7
enable_container_insights = false

additional_tags = {
  Environment = "development"
  CostOptimized = "true"
}
