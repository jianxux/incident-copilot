output "primary_endpoint" {
  description = "Primary endpoint address"
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "reader_endpoint" {
  description = "Reader endpoint address"
  value       = aws_elasticache_replication_group.main.reader_endpoint_address
}

output "port" {
  description = "Redis port"
  value       = var.port
}

output "arn" {
  description = "ARN of the replication group"
  value       = aws_elasticache_replication_group.main.arn
}

output "replication_group_id" {
  description = "ID of the replication group"
  value       = aws_elasticache_replication_group.main.replication_group_id
}

output "auth_token_secret_arn" {
  description = "ARN of the Secrets Manager secret containing the auth token"
  value       = var.transit_encryption ? aws_secretsmanager_secret.redis_auth[0].arn : null
}

output "kms_key_arn" {
  description = "ARN of the KMS key used for encryption"
  value       = var.at_rest_encryption ? aws_kms_key.redis[0].arn : null
}
