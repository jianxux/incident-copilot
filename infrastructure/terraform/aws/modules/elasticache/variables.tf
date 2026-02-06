variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "subnet_ids" {
  description = "IDs of subnets for the cache"
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security group IDs for ElastiCache"
  type        = list(string)
}

variable "node_type" {
  description = "ElastiCache node type"
  type        = string
}

variable "num_cache_nodes" {
  description = "Number of cache nodes"
  type        = number
  default     = 2
}

variable "engine_version" {
  description = "Redis engine version"
  type        = string
}

variable "port" {
  description = "Redis port"
  type        = number
  default     = 6379
}

variable "parameter_family" {
  description = "Redis parameter group family"
  type        = string
  default     = "redis7"
}

variable "automatic_failover" {
  description = "Enable automatic failover"
  type        = bool
  default     = true
}

variable "at_rest_encryption" {
  description = "Enable encryption at rest"
  type        = bool
  default     = true
}

variable "transit_encryption" {
  description = "Enable encryption in transit"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
