variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC"
  type        = string
}

variable "public_subnet_ids" {
  description = "IDs of public subnets for ALB"
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "IDs of private subnets for ECS tasks"
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "Security group ID for ALB"
  type        = string
}

variable "ecs_security_group_id" {
  description = "Security group ID for ECS tasks"
  type        = string
}

variable "task_cpu" {
  description = "CPU units for the task"
  type        = number
}

variable "task_memory" {
  description = "Memory for the task in MB"
  type        = number
}

variable "desired_count" {
  description = "Desired number of tasks"
  type        = number
}

variable "min_count" {
  description = "Minimum number of tasks"
  type        = number
}

variable "max_count" {
  description = "Maximum number of tasks"
  type        = number
}

variable "container_port" {
  description = "Port exposed by the container"
  type        = number
}

variable "container_image" {
  description = "Docker image for the application"
  type        = string
}

variable "health_check_path" {
  description = "Health check endpoint path"
  type        = string
}

variable "alb_ssl_certificate_arn" {
  description = "ARN of SSL certificate for HTTPS"
  type        = string
  default     = ""
}

variable "alb_internal" {
  description = "Whether the ALB is internal"
  type        = bool
  default     = false
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

variable "environment_variables" {
  description = "Environment variables for the container"
  type        = map(string)
  default     = {}
}

variable "secrets" {
  description = "Secrets from SSM Parameter Store"
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
