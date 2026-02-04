output "replication_group_id" {
  description = "ID of the replication group"
  value       = var.cluster_mode_enabled ? aws_elasticache_replication_group.cluster_mode[0].id : aws_elasticache_replication_group.main[0].id
}

output "replication_group_arn" {
  description = "ARN of the replication group"
  value       = var.cluster_mode_enabled ? aws_elasticache_replication_group.cluster_mode[0].arn : aws_elasticache_replication_group.main[0].arn
}

output "primary_endpoint_address" {
  description = "Primary endpoint address"
  value       = var.cluster_mode_enabled ? aws_elasticache_replication_group.cluster_mode[0].primary_endpoint_address : aws_elasticache_replication_group.main[0].primary_endpoint_address
}

output "reader_endpoint_address" {
  description = "Reader endpoint address"
  value       = var.cluster_mode_enabled ? aws_elasticache_replication_group.cluster_mode[0].reader_endpoint_address : aws_elasticache_replication_group.main[0].reader_endpoint_address
}

output "configuration_endpoint_address" {
  description = "Configuration endpoint address (cluster mode only)"
  value       = var.cluster_mode_enabled ? aws_elasticache_replication_group.cluster_mode[0].configuration_endpoint_address : null
}

output "port" {
  description = "Port for Redis"
  value       = var.port
}

output "security_group_id" {
  description = "ID of the Redis security group"
  value       = aws_security_group.redis.id
}

output "subnet_group_name" {
  description = "Name of the subnet group"
  value       = aws_elasticache_subnet_group.main.name
}

output "parameter_group_name" {
  description = "Name of the parameter group"
  value       = aws_elasticache_parameter_group.main.name
}

output "connection_url" {
  description = "Redis connection URL"
  value       = var.transit_encryption_enabled ? "rediss://${var.cluster_mode_enabled ? aws_elasticache_replication_group.cluster_mode[0].primary_endpoint_address : aws_elasticache_replication_group.main[0].primary_endpoint_address}:${var.port}" : "redis://${var.cluster_mode_enabled ? aws_elasticache_replication_group.cluster_mode[0].primary_endpoint_address : aws_elasticache_replication_group.main[0].primary_endpoint_address}:${var.port}"
}
