variable "cluster_id" {
  description = "ID of the ElastiCache cluster"
  type        = string
}

variable "description" {
  description = "Description of the replication group"
  type        = string
  default     = "Redis cluster"
}

variable "vpc_id" {
  description = "ID of the VPC"
  type        = string
}

variable "subnet_ids" {
  description = "IDs of subnets for the subnet group"
  type        = list(string)
}

variable "engine_version" {
  description = "Redis engine version"
  type        = string
  default     = "7.0"
}

variable "node_type" {
  description = "Node type for the cluster"
  type        = string
  default     = "cache.t3.micro"
}

variable "port" {
  description = "Port for Redis"
  type        = number
  default     = 6379
}

variable "parameter_group_family" {
  description = "Family for the parameter group"
  type        = string
  default     = "redis7"
}

variable "parameters" {
  description = "Additional parameters for the parameter group"
  type = list(object({
    name  = string
    value = string
  }))
  default = []
}

variable "maxmemory_policy" {
  description = "Maxmemory policy for Redis"
  type        = string
  default     = "volatile-lru"
}

# Cluster Mode Disabled settings
variable "num_cache_nodes" {
  description = "Number of cache nodes (replicas + 1 primary)"
  type        = number
  default     = 2
}

# Cluster Mode Enabled settings
variable "cluster_mode_enabled" {
  description = "Enable Redis cluster mode"
  type        = bool
  default     = false
}

variable "num_node_groups" {
  description = "Number of node groups (shards) for cluster mode"
  type        = number
  default     = 2
}

variable "replicas_per_node_group" {
  description = "Number of replicas per node group"
  type        = number
  default     = 1
}

variable "multi_az_enabled" {
  description = "Enable Multi-AZ"
  type        = bool
  default     = true
}

# Security
variable "at_rest_encryption_enabled" {
  description = "Enable encryption at rest"
  type        = bool
  default     = true
}

variable "transit_encryption_enabled" {
  description = "Enable encryption in transit"
  type        = bool
  default     = true
}

variable "auth_token" {
  description = "Auth token for Redis (required if transit encryption is enabled)"
  type        = string
  default     = null
  sensitive   = true
}

variable "kms_key_arn" {
  description = "ARN of KMS key for encryption"
  type        = string
  default     = null
}

variable "allowed_security_group_ids" {
  description = "Security group IDs allowed to access Redis"
  type        = list(string)
  default     = []
}

variable "allowed_cidr_blocks" {
  description = "CIDR blocks allowed to access Redis"
  type        = list(string)
  default     = []
}

# Maintenance
variable "maintenance_window" {
  description = "Preferred maintenance window"
  type        = string
  default     = "mon:05:00-mon:06:00"
}

variable "snapshot_window" {
  description = "Daily snapshot window"
  type        = string
  default     = "03:00-04:00"
}

variable "snapshot_retention_limit" {
  description = "Number of days to retain snapshots"
  type        = number
  default     = 7
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

variable "notification_topic_arn" {
  description = "ARN of SNS topic for notifications"
  type        = string
  default     = null
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
  description = "Memory usage percentage alarm threshold"
  type        = number
  default     = 80
}

variable "connections_alarm_threshold" {
  description = "Current connections alarm threshold"
  type        = number
  default     = 1000
}

variable "evictions_alarm_threshold" {
  description = "Evictions alarm threshold"
  type        = number
  default     = 100
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
