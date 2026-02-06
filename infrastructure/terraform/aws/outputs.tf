################################################################################
# Outputs - VPC
################################################################################

output "vpc_id" {
  description = "ID of the VPC"
  value       = module.vpc.vpc_id
}

output "vpc_cidr" {
  description = "CIDR block of the VPC"
  value       = module.vpc.vpc_cidr
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = module.vpc.public_subnet_ids
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = module.vpc.private_subnet_ids
}

output "database_subnet_ids" {
  description = "IDs of database subnets"
  value       = module.vpc.database_subnet_ids
}

output "nat_gateway_ips" {
  description = "Public IPs of NAT Gateways"
  value       = module.vpc.nat_gateway_ips
}

################################################################################
# Outputs - ECS
################################################################################

output "ecs_cluster_id" {
  description = "ID of the ECS cluster"
  value       = module.ecs.cluster_id
}

output "ecs_cluster_arn" {
  description = "ARN of the ECS cluster"
  value       = module.ecs.cluster_arn
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = module.ecs.cluster_name
}

output "ecs_service_name" {
  description = "Name of the ECS service"
  value       = module.ecs.service_name
}

output "ecs_task_definition_arn" {
  description = "ARN of the ECS task definition"
  value       = module.ecs.task_definition_arn
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = module.ecs.alb_dns_name
}

output "alb_arn" {
  description = "ARN of the Application Load Balancer"
  value       = module.ecs.alb_arn
}

output "alb_zone_id" {
  description = "Zone ID of the Application Load Balancer"
  value       = module.ecs.alb_zone_id
}

output "target_group_arn" {
  description = "ARN of the target group"
  value       = module.ecs.target_group_arn
}

################################################################################
# Outputs - RDS
################################################################################

output "rds_endpoint" {
  description = "Endpoint of the RDS instance"
  value       = module.rds.endpoint
}

output "rds_arn" {
  description = "ARN of the RDS instance"
  value       = module.rds.arn
}

output "rds_identifier" {
  description = "Identifier of the RDS instance"
  value       = module.rds.identifier
}

output "rds_port" {
  description = "Port of the RDS instance"
  value       = module.rds.port
}

output "db_secret_arn" {
  description = "ARN of the Secrets Manager secret containing DB credentials"
  value       = aws_secretsmanager_secret.db_password.arn
}

################################################################################
# Outputs - ElastiCache
################################################################################

output "redis_primary_endpoint" {
  description = "Primary endpoint of the Redis replication group"
  value       = module.elasticache.primary_endpoint
}

output "redis_reader_endpoint" {
  description = "Reader endpoint of the Redis replication group"
  value       = module.elasticache.reader_endpoint
}

output "redis_port" {
  description = "Port of the Redis cluster"
  value       = module.elasticache.port
}

output "redis_arn" {
  description = "ARN of the Redis replication group"
  value       = module.elasticache.arn
}

################################################################################
# Outputs - Security Groups
################################################################################

output "alb_security_group_id" {
  description = "ID of the ALB security group"
  value       = module.security.alb_security_group_id
}

output "ecs_security_group_id" {
  description = "ID of the ECS tasks security group"
  value       = module.security.ecs_security_group_id
}

output "rds_security_group_id" {
  description = "ID of the RDS security group"
  value       = module.security.rds_security_group_id
}

output "redis_security_group_id" {
  description = "ID of the Redis security group"
  value       = module.security.redis_security_group_id
}

################################################################################
# Outputs - IAM
################################################################################

output "ecs_task_role_arn" {
  description = "ARN of the ECS task role"
  value       = module.ecs.task_role_arn
}

output "ecs_execution_role_arn" {
  description = "ARN of the ECS execution role"
  value       = module.ecs.execution_role_arn
}

################################################################################
# Outputs - Application URLs
################################################################################

output "application_url" {
  description = "URL to access the application"
  value       = "http://${module.ecs.alb_dns_name}"
}

output "connection_strings" {
  description = "Connection strings for the application (sensitive)"
  sensitive   = true
  value = {
    database = "postgresql://${var.db_username}@${module.rds.endpoint}/${var.db_name}"
    redis    = "redis://${module.elasticache.primary_endpoint}:${var.redis_port}"
  }
}
