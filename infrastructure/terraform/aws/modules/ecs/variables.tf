variable "cluster_name" {
  description = "Name of the ECS cluster"
  type        = string
}

variable "service_name" {
  description = "Name of the ECS service"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
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

variable "container_name" {
  description = "Name of the container"
  type        = string
  default     = "app"
}

variable "container_image" {
  description = "Docker image for the container"
  type        = string
}

variable "container_port" {
  description = "Port the container listens on"
  type        = number
  default     = 8000
}

variable "task_cpu" {
  description = "CPU units for the task (1024 = 1 vCPU)"
  type        = number
  default     = 256
}

variable "task_memory" {
  description = "Memory for the task in MB"
  type        = number
  default     = 512
}

variable "desired_count" {
  description = "Desired number of tasks"
  type        = number
  default     = 2
}

variable "health_check_path" {
  description = "Path for health checks"
  type        = string
  default     = "/health"
}

variable "health_check_grace_period" {
  description = "Health check grace period in seconds"
  type        = number
  default     = 60
}

variable "platform_version" {
  description = "Fargate platform version"
  type        = string
  default     = "LATEST"
}

variable "enable_execute_command" {
  description = "Enable ECS Exec for debugging"
  type        = bool
  default     = false
}

variable "enable_container_insights" {
  description = "Enable Container Insights for the cluster"
  type        = bool
  default     = true
}

variable "enable_spot" {
  description = "Enable Fargate Spot capacity"
  type        = bool
  default     = false
}

variable "spot_weight" {
  description = "Weight for Fargate Spot capacity provider"
  type        = number
  default     = 50
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

# Environment variables and secrets
variable "environment_variables" {
  description = "Environment variables for the container"
  type = list(object({
    name  = string
    value = string
  }))
  default = []
}

variable "secrets" {
  description = "Secrets from Secrets Manager or Parameter Store"
  type = list(object({
    name      = string
    valueFrom = string
  }))
  default = []
}

variable "secrets_arns" {
  description = "ARNs of secrets the task execution role can access"
  type        = list(string)
  default     = ["*"]
}

variable "kms_key_arn" {
  description = "ARN of KMS key for decrypting secrets"
  type        = string
  default     = null
}

# IAM permissions
variable "s3_bucket_arns" {
  description = "ARNs of S3 buckets the task role can access"
  type        = list(string)
  default     = []
}

variable "sqs_queue_arns" {
  description = "ARNs of SQS queues the task role can access"
  type        = list(string)
  default     = []
}

# Load Balancer
variable "internal_alb" {
  description = "Whether the ALB is internal"
  type        = bool
  default     = false
}

variable "allowed_cidr_blocks" {
  description = "CIDR blocks allowed to access the ALB"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "ssl_certificate_arn" {
  description = "ARN of ACM certificate for HTTPS"
  type        = string
  default     = null
}

variable "ssl_policy" {
  description = "SSL policy for HTTPS listener"
  type        = string
  default     = "ELBSecurityPolicy-TLS13-1-2-2021-06"
}

variable "enable_deletion_protection" {
  description = "Enable deletion protection for ALB"
  type        = bool
  default     = false
}

variable "enable_stickiness" {
  description = "Enable session stickiness"
  type        = bool
  default     = false
}

variable "alb_access_logs_bucket" {
  description = "S3 bucket for ALB access logs"
  type        = string
  default     = ""
}

# Auto Scaling
variable "enable_autoscaling" {
  description = "Enable auto scaling"
  type        = bool
  default     = true
}

variable "min_capacity" {
  description = "Minimum number of tasks"
  type        = number
  default     = 1
}

variable "max_capacity" {
  description = "Maximum number of tasks"
  type        = number
  default     = 10
}

variable "cpu_target_value" {
  description = "Target CPU utilization percentage"
  type        = number
  default     = 70
}

variable "memory_target_value" {
  description = "Target memory utilization percentage"
  type        = number
  default     = 70
}

variable "enable_request_count_scaling" {
  description = "Enable scaling based on request count"
  type        = bool
  default     = false
}

variable "request_count_target_value" {
  description = "Target request count per target"
  type        = number
  default     = 1000
}

variable "scale_in_cooldown" {
  description = "Scale in cooldown period in seconds"
  type        = number
  default     = 300
}

variable "scale_out_cooldown" {
  description = "Scale out cooldown period in seconds"
  type        = number
  default     = 60
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
