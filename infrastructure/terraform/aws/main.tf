################################################################################
# Main Terraform Configuration for Incident Copilot AWS Infrastructure
################################################################################

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  common_tags = merge(var.additional_tags, {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

# Generate random password for RDS
resource "random_password" "db_password" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

################################################################################
# VPC Module
################################################################################

module "vpc" {
  source = "./modules/vpc"

  name_prefix           = local.name_prefix
  vpc_cidr              = var.vpc_cidr
  availability_zones    = var.availability_zones
  public_subnet_cidrs   = var.public_subnet_cidrs
  private_subnet_cidrs  = var.private_subnet_cidrs
  database_subnet_cidrs = var.database_subnet_cidrs
  enable_nat_gateway    = var.enable_nat_gateway
  single_nat_gateway    = var.single_nat_gateway
  tags                  = local.common_tags
}

################################################################################
# Security Module
################################################################################

module "security" {
  source = "./modules/security"

  name_prefix        = local.name_prefix
  vpc_id             = module.vpc.vpc_id
  vpc_cidr           = var.vpc_cidr
  container_port     = var.container_port
  redis_port         = var.redis_port
  private_subnet_ids = module.vpc.private_subnet_ids
  tags               = local.common_tags
}

################################################################################
# RDS PostgreSQL Module
################################################################################

module "rds" {
  source = "./modules/rds"

  name_prefix              = local.name_prefix
  db_subnet_ids            = module.vpc.database_subnet_ids
  security_group_ids       = [module.security.rds_security_group_id]
  instance_class           = var.db_instance_class
  allocated_storage        = var.db_allocated_storage
  max_allocated_storage    = var.db_max_allocated_storage
  db_name                  = var.db_name
  username                 = var.db_username
  password                 = random_password.db_password.result
  engine_version           = var.db_engine_version
  multi_az                 = var.db_multi_az
  backup_retention_period  = var.db_backup_retention_period
  deletion_protection      = var.db_deletion_protection
  skip_final_snapshot      = var.db_skip_final_snapshot
  tags                     = local.common_tags
}

################################################################################
# ElastiCache Redis Module
################################################################################

module "elasticache" {
  source = "./modules/elasticache"

  name_prefix          = local.name_prefix
  subnet_ids           = module.vpc.private_subnet_ids
  security_group_ids   = [module.security.redis_security_group_id]
  node_type            = var.redis_node_type
  num_cache_nodes      = var.redis_num_cache_nodes
  engine_version       = var.redis_engine_version
  port                 = var.redis_port
  parameter_family     = var.redis_parameter_family
  automatic_failover   = var.redis_automatic_failover
  at_rest_encryption   = var.redis_at_rest_encryption
  transit_encryption   = var.redis_transit_encryption
  tags                 = local.common_tags
}

################################################################################
# ECS Fargate Module
################################################################################

module "ecs" {
  source = "./modules/ecs"

  name_prefix               = local.name_prefix
  vpc_id                    = module.vpc.vpc_id
  public_subnet_ids         = module.vpc.public_subnet_ids
  private_subnet_ids        = module.vpc.private_subnet_ids
  alb_security_group_id     = module.security.alb_security_group_id
  ecs_security_group_id     = module.security.ecs_security_group_id
  task_cpu                  = var.ecs_task_cpu
  task_memory               = var.ecs_task_memory
  desired_count             = var.ecs_desired_count
  min_count                 = var.ecs_min_count
  max_count                 = var.ecs_max_count
  container_port            = var.container_port
  container_image           = var.container_image
  health_check_path         = var.health_check_path
  alb_ssl_certificate_arn   = var.alb_ssl_certificate_arn
  alb_internal              = var.alb_internal
  log_retention_days        = var.log_retention_days
  enable_container_insights = var.enable_container_insights

  # Environment variables for the application
  environment_variables = {
    DATABASE_URL = "postgresql://${var.db_username}:${random_password.db_password.result}@${module.rds.endpoint}/${var.db_name}"
    REDIS_URL    = "redis://${module.elasticache.primary_endpoint}:${var.redis_port}"
    ENVIRONMENT  = var.environment
    PORT         = tostring(var.container_port)
  }

  # Secrets from SSM Parameter Store (to be created separately)
  secrets = {
    OPENAI_API_KEY    = "/${var.project_name}/${var.environment}/openai-api-key"
    ANTHROPIC_API_KEY = "/${var.project_name}/${var.environment}/anthropic-api-key"
    PAGERDUTY_TOKEN   = "/${var.project_name}/${var.environment}/pagerduty-token"
    SLACK_BOT_TOKEN   = "/${var.project_name}/${var.environment}/slack-bot-token"
  }

  tags = local.common_tags
}

################################################################################
# Store DB Password in Secrets Manager
################################################################################

resource "aws_secretsmanager_secret" "db_password" {
  name                    = "${local.name_prefix}-db-password"
  description             = "RDS PostgreSQL password for ${var.project_name}"
  recovery_window_in_days = 7

  tags = local.common_tags
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id = aws_secretsmanager_secret.db_password.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db_password.result
    host     = module.rds.endpoint
    port     = 5432
    dbname   = var.db_name
  })
}
