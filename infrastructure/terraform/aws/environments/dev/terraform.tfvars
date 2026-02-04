# Development Environment Configuration
# Cost-optimized settings for development

project_name = "incident-copilot"
environment  = "dev"
aws_region   = "us-west-2"

# VPC - Cost optimized
vpc_cidr             = "10.0.0.0/16"
az_count             = 2
enable_nat_gateway   = true
single_nat_gateway   = true  # Single NAT to save costs
enable_vpc_endpoints = false # Disable to save costs in dev
enable_flow_logs     = false

# ECS - Minimal resources
container_image = "placeholder:latest"  # Update with actual image
container_port  = 8000
task_cpu        = 256
task_memory     = 512
desired_count   = 1

# Scaling - Minimal
enable_autoscaling = true
min_capacity       = 1
max_capacity       = 3
cpu_target_value   = 70

# No SSL in dev (optional)
ssl_certificate_arn = null

# Logging
log_retention_days        = 7
enable_container_insights = false
enable_execute_command    = true  # Enable for debugging

# RDS - Minimal
database_name              = "incident_copilot_dev"
db_instance_class          = "db.t3.micro"
db_allocated_storage       = 20
db_max_allocated_storage   = 50
db_engine_version          = "15.4"
db_multi_az                = false
db_backup_retention_period = 1
db_performance_insights    = false
db_monitoring_interval     = 0

# Redis - Minimal
redis_node_type          = "cache.t3.micro"
redis_num_cache_nodes    = 1
redis_engine_version     = "7.0"
redis_multi_az           = false
redis_transit_encryption = false
redis_at_rest_encryption = false
redis_snapshot_retention = 0
