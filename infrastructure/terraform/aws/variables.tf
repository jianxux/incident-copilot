# General Variables
variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "incident-copilot"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-west-2"
}

# VPC Variables
variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones"
  type        = number
  default     = 3
}

variable "enable_nat_gateway" {
  description = "Enable NAT gateway"
  type        = bool
  default     = true
}

variable "single_nat_gateway" {
  description = "Use single NAT gateway (cost savings for non-prod)"
  type        = bool
  default     = false
}

variable "enable_vpc_endpoints" {
  description = "Enable VPC endpoints for AWS services"
  type        = bool
  default     = true
}

variable "enable_flow_logs" {
  description = "Enable VPC flow logs"
  type        = bool
  default     = true
}

# ECS Variables
variable "container_image" {
  description = "Docker image for the application"
  type        = string
}

variable "container_port" {
  description = "Port the container listens on"
  type        = number
  default     = 8000
}

variable "task_cpu" {
  description = "CPU units for the ECS task"
  type        = number
  default     = 512
}

variable "task_memory" {
  description = "Memory for the ECS task in MB"
  type        = number
  default     = 1024
}

variable "desired_count" {
  description = "Desired number of ECS tasks"
  type        = number
  default     = 2
}

variable "enable_autoscaling" {
  description = "Enable ECS auto scaling"
  type        = bool
  default     = true
}

variable "min_capacity" {
  description = "Minimum number of ECS tasks"
  type        = number
  default     = 1
}

variable "max_capacity" {
  description = "Maximum number of ECS tasks"
  type        = number
  default     = 10
}

variable "cpu_target_value" {
  description = "Target CPU utilization for auto scaling"
  type        = number
  default     = 70
}

variable "ssl_certificate_arn" {
  description = "ARN of ACM certificate for HTTPS"
  type        = string
  default     = null
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "enable_container_insights" {
  description = "Enable Container Insights"
  type        = bool
  default     = true
}

variable "enable_execute_command" {
  description = "Enable ECS Exec for debugging"
  type        = bool
  default     = false
}

# RDS Variables
variable "database_name" {
  description = "Name of the database"
  type        = string
  default     = "incident_copilot"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "db_allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Maximum allocated storage in GB"
  type        = number
  default     = 100
}

variable "db_engine_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "15.4"
}

variable "db_multi_az" {
  description = "Enable Multi-AZ for RDS"
  type        = bool
  default     = false
}

variable "db_backup_retention_period" {
  description = "RDS backup retention period in days"
  type        = number
  default     = 7
}

variable "db_performance_insights" {
  description = "Enable RDS Performance Insights"
  type        = bool
  default     = true
}

variable "db_monitoring_interval" {
  description = "Enhanced monitoring interval in seconds"
  type        = number
  default     = 60
}

# Redis Variables
variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t3.micro"
}

variable "redis_num_cache_nodes" {
  description = "Number of Redis cache nodes"
  type        = number
  default     = 2
}

variable "redis_engine_version" {
  description = "Redis engine version"
  type        = string
  default     = "7.0"
}

variable "redis_multi_az" {
  description = "Enable Multi-AZ for Redis"
  type        = bool
  default     = true
}

variable "redis_transit_encryption" {
  description = "Enable Redis transit encryption"
  type        = bool
  default     = true
}

variable "redis_at_rest_encryption" {
  description = "Enable Redis at-rest encryption"
  type        = bool
  default     = true
}

variable "redis_snapshot_retention" {
  description = "Redis snapshot retention in days"
  type        = number
  default     = 7
}
