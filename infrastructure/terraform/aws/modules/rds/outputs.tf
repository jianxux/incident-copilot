output "db_instance_id" {
  description = "ID of the RDS instance"
  value       = aws_db_instance.main.id
}

output "db_instance_arn" {
  description = "ARN of the RDS instance"
  value       = aws_db_instance.main.arn
}

output "db_instance_address" {
  description = "Address of the RDS instance"
  value       = aws_db_instance.main.address
}

output "db_instance_endpoint" {
  description = "Endpoint of the RDS instance"
  value       = aws_db_instance.main.endpoint
}

output "db_instance_port" {
  description = "Port of the RDS instance"
  value       = aws_db_instance.main.port
}

output "db_instance_name" {
  description = "Name of the database"
  value       = aws_db_instance.main.db_name
}

output "db_instance_username" {
  description = "Master username"
  value       = aws_db_instance.main.username
  sensitive   = true
}

output "db_security_group_id" {
  description = "ID of the database security group"
  value       = aws_security_group.db.id
}

output "db_subnet_group_name" {
  description = "Name of the DB subnet group"
  value       = aws_db_subnet_group.main.name
}

output "db_parameter_group_name" {
  description = "Name of the DB parameter group"
  value       = aws_db_parameter_group.main.name
}

output "secret_arn" {
  description = "ARN of the Secrets Manager secret"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "secret_name" {
  description = "Name of the Secrets Manager secret"
  value       = aws_secretsmanager_secret.db_credentials.name
}

output "connection_string" {
  description = "PostgreSQL connection string (without password)"
  value       = "postgresql://${aws_db_instance.main.username}@${aws_db_instance.main.endpoint}/${aws_db_instance.main.db_name}"
  sensitive   = true
}
