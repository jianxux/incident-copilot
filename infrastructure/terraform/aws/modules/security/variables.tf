variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block of the VPC"
  type        = string
}

variable "container_port" {
  description = "Port exposed by the container"
  type        = number
}

variable "redis_port" {
  description = "Redis port"
  type        = number
  default     = 6379
}

variable "private_subnet_ids" {
  description = "IDs of private subnets for VPC endpoints"
  type        = list(string)
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
