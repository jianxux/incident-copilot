# Staging Environment Configuration
# Production-like settings for testing

project_name = "incident-copilot"
environment  = "staging"
aws_region   = "us-west-2"

# VPC - Production-like but cost conscious
vpc_cidr             = "10.1.0.0/16"
az_count             = 3
enable_nat_gateway   = true
single_nat_gateway   = true  # Still use single NAT for staging
enable_vpc_endpoints = true
enable_flow_logs     = true

# ECS - Moderate resources
container_image = "placeholder:latest"  # Update with actual image
container_port  = 8000
task_cpu        = 512
task_memory     = 1024
desired_count   = 2

# Scaling - Moderate
enable_autoscaling = true
min_capacity       = 2
max_capacity       = 6
cpu_target_value   = 70

# SSL (optional for staging)
ssl_certificate_arn = null  # Add certificate ARN if needed

# Logging
log_retention_days        = 14
enable_container_insights = true
enable_execute_command    = true  # Enable for debugging

# RDS - Moderate
database_name              = "incident_copilot_staging"
db_instance_class          = "db.t3.small"
db_allocated_storage       = 30
db_max_allocated_storage   = 100
db_engine_version          = "15.4"
db_multi_az                = false  # Optional for staging
db_backup_retention_period = 3
db_performance_insights    = true
db_monitoring_interval     = 60

# Redis - Moderate
redis_node_type          = "cache.t3.small"
redis_num_cache_nodes    = 2
redis_engine_version     = "7.0"
redis_multi_az           = true
redis_transit_encryption = true
redis_at_rest_encryption = true
redis_snapshot_retention = 3
