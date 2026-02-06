################################################################################
# ElastiCache Redis Module
################################################################################

################################################################################
# Subnet Group
################################################################################

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.name_prefix}-redis-subnet-group"
  subnet_ids = var.subnet_ids

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-redis-subnet-group"
  })
}

################################################################################
# Parameter Group
################################################################################

resource "aws_elasticache_parameter_group" "main" {
  name   = "${var.name_prefix}-redis7-params"
  family = var.parameter_family

  # Performance and memory optimization
  parameter {
    name  = "maxmemory-policy"
    value = "volatile-lru"
  }

  parameter {
    name  = "timeout"
    value = "300"
  }

  parameter {
    name  = "tcp-keepalive"
    value = "300"
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-redis7-params"
  })
}

################################################################################
# Redis Replication Group (Cluster Mode Disabled)
################################################################################

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${var.name_prefix}-redis"
  description          = "Redis cluster for ${var.name_prefix}"

  # Engine configuration
  engine               = "redis"
  engine_version       = var.engine_version
  node_type            = var.node_type
  port                 = var.port
  parameter_group_name = aws_elasticache_parameter_group.main.name

  # Cluster configuration (cluster mode disabled, multi-node for HA)
  num_cache_clusters         = var.num_cache_nodes
  automatic_failover_enabled = var.automatic_failover && var.num_cache_nodes > 1

  # Network configuration
  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = var.security_group_ids

  # Encryption
  at_rest_encryption_enabled = var.at_rest_encryption
  transit_encryption_enabled = var.transit_encryption
  kms_key_id                 = var.at_rest_encryption ? aws_kms_key.redis[0].arn : null

  # Auth (required when transit encryption is enabled)
  auth_token = var.transit_encryption ? random_password.auth_token[0].result : null

  # Maintenance
  maintenance_window       = "sun:05:00-sun:06:00"
  snapshot_window          = "04:00-05:00"
  snapshot_retention_limit = 7
  auto_minor_version_upgrade = true

  # Notifications
  notification_topic_arn = aws_sns_topic.redis_notifications.arn

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-redis"
  })

  lifecycle {
    ignore_changes = [num_cache_clusters]
  }
}

################################################################################
# Auth Token (for TLS connections)
################################################################################

resource "random_password" "auth_token" {
  count = var.transit_encryption ? 1 : 0

  length           = 64
  special          = false
  override_special = "!&#$^<>-"
}

################################################################################
# KMS Key for Encryption at Rest
################################################################################

resource "aws_kms_key" "redis" {
  count = var.at_rest_encryption ? 1 : 0

  description             = "KMS key for Redis encryption - ${var.name_prefix}"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      }
    ]
  })

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-redis-kms-key"
  })
}

resource "aws_kms_alias" "redis" {
  count = var.at_rest_encryption ? 1 : 0

  name          = "alias/${var.name_prefix}-redis"
  target_key_id = aws_kms_key.redis[0].key_id
}

################################################################################
# SNS Topic for Notifications
################################################################################

resource "aws_sns_topic" "redis_notifications" {
  name = "${var.name_prefix}-redis-notifications"

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-redis-notifications"
  })
}

################################################################################
# CloudWatch Alarms
################################################################################

resource "aws_cloudwatch_metric_alarm" "redis_cpu" {
  alarm_name          = "${var.name_prefix}-redis-cpu-utilization"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = 75
  alarm_description   = "Redis CPU utilization is above 75%"

  dimensions = {
    CacheClusterId = "${aws_elasticache_replication_group.main.replication_group_id}-001"
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "redis_memory" {
  alarm_name          = "${var.name_prefix}-redis-memory-utilization"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DatabaseMemoryUsagePercentage"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "Redis memory utilization is above 80%"

  dimensions = {
    CacheClusterId = "${aws_elasticache_replication_group.main.replication_group_id}-001"
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "redis_connections" {
  alarm_name          = "${var.name_prefix}-redis-connections"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CurrConnections"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = 1000
  alarm_description   = "Redis current connections above 1000"

  dimensions = {
    CacheClusterId = "${aws_elasticache_replication_group.main.replication_group_id}-001"
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "redis_evictions" {
  alarm_name          = "${var.name_prefix}-redis-evictions"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Evictions"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Sum"
  threshold           = 100
  alarm_description   = "Redis evictions are occurring"

  dimensions = {
    CacheClusterId = "${aws_elasticache_replication_group.main.replication_group_id}-001"
  }

  tags = var.tags
}

################################################################################
# Store Auth Token in Secrets Manager
################################################################################

resource "aws_secretsmanager_secret" "redis_auth" {
  count = var.transit_encryption ? 1 : 0

  name                    = "${var.name_prefix}-redis-auth-token"
  description             = "Redis auth token for ${var.name_prefix}"
  recovery_window_in_days = 7

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "redis_auth" {
  count = var.transit_encryption ? 1 : 0

  secret_id = aws_secretsmanager_secret.redis_auth[0].id
  secret_string = jsonencode({
    auth_token       = random_password.auth_token[0].result
    primary_endpoint = aws_elasticache_replication_group.main.primary_endpoint_address
    reader_endpoint  = aws_elasticache_replication_group.main.reader_endpoint_address
    port             = var.port
  })
}

################################################################################
# Data Sources
################################################################################

data "aws_caller_identity" "current" {}
