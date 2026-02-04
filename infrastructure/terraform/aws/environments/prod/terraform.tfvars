# Production Environment Configuration
# High availability and security focused

project_name = "incident-copilot"
environment  = "prod"
aws_region   = "us-west-2"

# VPC - Full HA
vpc_cidr             = "10.2.0.0/16"
az_count             = 3
enable_nat_gateway   = true
single_nat_gateway   = false  # NAT per AZ for HA
enable_vpc_endpoints = true
enable_flow_logs     = true

# ECS - Production resources
container_image = "placeholder:latest"  # Update with actual image
container_port  = 8000
task_cpu        = 1024
task_memory     = 2048
desired_count   = 3

# Scaling - Production ready
enable_autoscaling = true
min_capacity       = 3
max_capacity       = 20
cpu_target_value   = 60

# SSL (required for production)
ssl_certificate_arn = null  # REQUIRED: Add your ACM certificate ARN

# Logging
log_retention_days        = 90
enable_container_insights = true
enable_execute_command    = false  # Disable in prod for security

# RDS - Production ready
database_name              = "incident_copilot"
db_instance_class          = "db.r6g.large"
db_allocated_storage       = 100
db_max_allocated_storage   = 500
db_engine_version          = "15.4"
db_multi_az                = true  # Required for production
db_backup_retention_period = 30
db_performance_insights    = true
db_monitoring_interval     = 60

# Redis - Production ready
redis_node_type          = "cache.r6g.large"
redis_num_cache_nodes    = 3
redis_engine_version     = "7.0"
redis_multi_az           = true
redis_transit_encryption = true
redis_at_rest_encryption = true
redis_snapshot_retention = 7
