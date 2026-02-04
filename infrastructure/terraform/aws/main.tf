# Incident Copilot - AWS Infrastructure
# Production-ready Terraform configuration

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Data Sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# VPC Module
module "vpc" {
  source = "./modules/vpc"

  name       = local.name_prefix
  vpc_cidr   = var.vpc_cidr
  az_count   = var.az_count
  aws_region = var.aws_region

  enable_nat_gateway   = var.enable_nat_gateway
  single_nat_gateway   = var.single_nat_gateway
  enable_vpc_endpoints = var.enable_vpc_endpoints
  enable_flow_logs     = var.enable_flow_logs

  tags = local.common_tags
}

# ECS Module
module "ecs" {
  source = "./modules/ecs"

  cluster_name = "${local.name_prefix}-cluster"
  service_name = "${local.name_prefix}-api"
  aws_region   = var.aws_region

  vpc_id             = module.vpc.vpc_id
  public_subnet_ids  = module.vpc.public_subnet_ids
  private_subnet_ids = module.vpc.private_subnet_ids

  # Container configuration
  container_name  = "incident-copilot-api"
  container_image = var.container_image
  container_port  = var.container_port
  task_cpu        = var.task_cpu
  task_memory     = var.task_memory
  desired_count   = var.desired_count

  # Health check
  health_check_path = "/health"

  # Environment variables
  environment_variables = [
    {
      name  = "ENVIRONMENT"
      value = var.environment
    },
    {
      name  = "AWS_REGION"
      value = var.aws_region
    },
    {
      name  = "DATABASE_HOST"
      value = module.rds.db_instance_address
    },
    {
      name  = "DATABASE_PORT"
      value = tostring(module.rds.db_instance_port)
    },
    {
      name  = "DATABASE_NAME"
      value = var.database_name
    },
    {
      name  = "REDIS_HOST"
      value = module.redis.primary_endpoint_address
    },
    {
      name  = "REDIS_PORT"
      value = tostring(module.redis.port)
    }
  ]

  # Secrets from Secrets Manager
  secrets = [
    {
      name      = "DATABASE_URL"
      valueFrom = "${module.rds.secret_arn}:password::"
    }
  ]

  secrets_arns = [module.rds.secret_arn]

  # Auto scaling
  enable_autoscaling = var.enable_autoscaling
  min_capacity       = var.min_capacity
  max_capacity       = var.max_capacity
  cpu_target_value   = var.cpu_target_value

  # SSL
  ssl_certificate_arn = var.ssl_certificate_arn

  # Logging
  log_retention_days = var.log_retention_days

  # Features
  enable_container_insights = var.enable_container_insights
  enable_execute_command    = var.enable_execute_command

  tags = local.common_tags
}

# RDS Module
module "rds" {
  source = "./modules/rds"

  identifier    = "${local.name_prefix}-db"
  vpc_id        = module.vpc.vpc_id
  subnet_ids    = module.vpc.database_subnet_ids
  database_name = var.database_name

  # Instance configuration
  instance_class        = var.db_instance_class
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  engine_version        = var.db_engine_version

  # High Availability
  multi_az = var.db_multi_az

  # Security
  allowed_security_group_ids = [module.ecs.ecs_security_group_id]

  # Backup
  backup_retention_period = var.db_backup_retention_period
  skip_final_snapshot     = var.environment != "prod"

  # Monitoring
  performance_insights_enabled = var.db_performance_insights
  monitoring_interval          = var.db_monitoring_interval

  # Protection
  deletion_protection = var.environment == "prod"

  tags = local.common_tags
}

# Redis Module
module "redis" {
  source = "./modules/redis"

  cluster_id  = "${local.name_prefix}-redis"
  description = "Redis cache for ${var.project_name} ${var.environment}"
  vpc_id      = module.vpc.vpc_id
  subnet_ids  = module.vpc.private_subnet_ids

  # Instance configuration
  node_type       = var.redis_node_type
  num_cache_nodes = var.redis_num_cache_nodes
  engine_version  = var.redis_engine_version

  # High Availability
  multi_az_enabled = var.redis_multi_az

  # Security
  allowed_security_group_ids = [module.ecs.ecs_security_group_id]
  transit_encryption_enabled = var.redis_transit_encryption
  at_rest_encryption_enabled = var.redis_at_rest_encryption

  # Backup
  snapshot_retention_limit = var.redis_snapshot_retention

  tags = local.common_tags
}
