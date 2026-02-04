variable "identifier" {
  description = "Identifier for the RDS instance"
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC"
  type        = string
}

variable "subnet_ids" {
  description = "IDs of subnets for the DB subnet group"
  type        = list(string)
}

variable "database_name" {
  description = "Name of the database to create"
  type        = string
}

variable "master_username" {
  description = "Master username for the database"
  type        = string
  default     = "postgres"
}

variable "port" {
  description = "Port for the database"
  type        = number
  default     = 5432
}

variable "engine_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "15.4"
}

variable "instance_class" {
  description = "Instance class for the database"
  type        = string
  default     = "db.t3.medium"
}

variable "parameter_group_family" {
  description = "Family for the parameter group"
  type        = string
  default     = "postgres15"
}

variable "parameters" {
  description = "Additional parameters for the parameter group"
  type = list(object({
    name         = string
    value        = string
    apply_method = optional(string)
  }))
  default = []
}

variable "allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "max_allocated_storage" {
  description = "Maximum allocated storage in GB for autoscaling"
  type        = number
  default     = 100
}

variable "storage_type" {
  description = "Storage type (gp2, gp3, io1)"
  type        = string
  default     = "gp3"
}

variable "kms_key_arn" {
  description = "ARN of KMS key for encryption"
  type        = string
  default     = null
}

variable "multi_az" {
  description = "Enable Multi-AZ deployment"
  type        = bool
  default     = false
}

variable "backup_retention_period" {
  description = "Backup retention period in days"
  type        = number
  default     = 7
}

variable "backup_window" {
  description = "Preferred backup window"
  type        = string
  default     = "03:00-04:00"
}

variable "maintenance_window" {
  description = "Preferred maintenance window"
  type        = string
  default     = "Mon:04:00-Mon:05:00"
}

variable "skip_final_snapshot" {
  description = "Skip final snapshot on deletion"
  type        = bool
  default     = false
}

variable "performance_insights_enabled" {
  description = "Enable Performance Insights"
  type        = bool
  default     = true
}

variable "performance_insights_retention_period" {
  description = "Performance Insights retention period in days"
  type        = number
  default     = 7
}

variable "monitoring_interval" {
  description = "Enhanced monitoring interval in seconds (0 to disable)"
  type        = number
  default     = 60
}

variable "cloudwatch_logs_exports" {
  description = "List of log types to export to CloudWatch"
  type        = list(string)
  default     = ["postgresql", "upgrade"]
}

variable "auto_minor_version_upgrade" {
  description = "Enable auto minor version upgrade"
  type        = bool
  default     = true
}

variable "apply_immediately" {
  description = "Apply changes immediately"
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Enable deletion protection"
  type        = bool
  default     = true
}

variable "ca_cert_identifier" {
  description = "CA certificate identifier"
  type        = string
  default     = "rds-ca-rsa2048-g1"
}

variable "allowed_security_group_ids" {
  description = "Security group IDs allowed to access the database"
  type        = list(string)
  default     = []
}

variable "allowed_cidr_blocks" {
  description = "CIDR blocks allowed to access the database"
  type        = list(string)
  default     = []
}

variable "secret_recovery_window_days" {
  description = "Recovery window for Secrets Manager secret"
  type        = number
  default     = 7
}

# CloudWatch Alarms
variable "create_cloudwatch_alarms" {
  description = "Create CloudWatch alarms"
  type        = bool
  default     = true
}

variable "alarm_actions" {
  description = "List of ARNs to notify on alarm"
  type        = list(string)
  default     = []
}

variable "cpu_alarm_threshold" {
  description = "CPU utilization alarm threshold"
  type        = number
  default     = 80
}

variable "memory_alarm_threshold" {
  description = "Freeable memory alarm threshold in bytes"
  type        = number
  default     = 100000000 # 100MB
}

variable "storage_alarm_threshold" {
  description = "Free storage alarm threshold in bytes"
  type        = number
  default     = 5000000000 # 5GB
}

variable "connections_alarm_threshold" {
  description = "Database connections alarm threshold"
  type        = number
  default     = 100
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
