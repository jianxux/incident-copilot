# VPC Outputs
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

output "availability_zones" {
  description = "Availability zones in use"
  value       = module.vpc.availability_zones
}

# ECS Outputs
output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = module.ecs.cluster_name
}

output "ecs_cluster_arn" {
  description = "ARN of the ECS cluster"
  value       = module.ecs.cluster_arn
}

output "ecs_service_name" {
  description = "Name of the ECS service"
  value       = module.ecs.service_name
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = module.ecs.alb_dns_name
}

output "alb_zone_id" {
  description = "Zone ID of the ALB (for Route53 alias)"
  value       = module.ecs.alb_zone_id
}

output "ecs_security_group_id" {
  description = "ID of the ECS security group"
  value       = module.ecs.ecs_security_group_id
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group name"
  value       = module.ecs.cloudwatch_log_group_name
}

# RDS Outputs
output "db_instance_endpoint" {
  description = "RDS instance endpoint"
  value       = module.rds.db_instance_endpoint
}

output "db_instance_address" {
  description = "RDS instance address"
  value       = module.rds.db_instance_address
}

output "db_instance_port" {
  description = "RDS instance port"
  value       = module.rds.db_instance_port
}

output "db_secret_arn" {
  description = "ARN of the database credentials secret"
  value       = module.rds.secret_arn
}

output "db_security_group_id" {
  description = "ID of the database security group"
  value       = module.rds.db_security_group_id
}

# Redis Outputs
output "redis_endpoint" {
  description = "Redis primary endpoint"
  value       = module.redis.primary_endpoint_address
}

output "redis_reader_endpoint" {
  description = "Redis reader endpoint"
  value       = module.redis.reader_endpoint_address
}

output "redis_port" {
  description = "Redis port"
  value       = module.redis.port
}

output "redis_security_group_id" {
  description = "ID of the Redis security group"
  value       = module.redis.security_group_id
}

# Connection Information
output "application_url" {
  description = "Application URL (HTTP)"
  value       = "http://${module.ecs.alb_dns_name}"
}

output "database_connection_info" {
  description = "Database connection information"
  value = {
    host     = module.rds.db_instance_address
    port     = module.rds.db_instance_port
    database = var.database_name
    secret   = module.rds.secret_name
  }
}

output "redis_connection_info" {
  description = "Redis connection information"
  value = {
    host = module.redis.primary_endpoint_address
    port = module.redis.port
  }
}

# AWS Account Info
output "aws_account_id" {
  description = "AWS Account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "AWS Region"
  value       = data.aws_region.current.name
}
