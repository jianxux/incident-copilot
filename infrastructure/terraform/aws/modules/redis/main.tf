# ElastiCache Redis Module - Production-ready Redis cluster

# Subnet Group
resource "aws_elasticache_subnet_group" "main" {
  name        = "${var.cluster_id}-subnet-group"
  description = "Subnet group for ${var.cluster_id}"
  subnet_ids  = var.subnet_ids

  tags = var.tags
}

# Parameter Group
resource "aws_elasticache_parameter_group" "main" {
  name        = "${var.cluster_id}-params"
  family      = var.parameter_group_family
  description = "Parameter group for ${var.cluster_id}"

  dynamic "parameter" {
    for_each = var.parameters
    content {
      name  = parameter.value.name
      value = parameter.value.value
    }
  }

  # Default recommended parameters
  parameter {
    name  = "maxmemory-policy"
    value = var.maxmemory_policy
  }

  tags = var.tags

  lifecycle {
    create_before_destroy = true
  }
}

# Security Group
resource "aws_security_group" "redis" {
  name_prefix = "${var.cluster_id}-redis-"
  description = "Security group for ${var.cluster_id}"
  vpc_id      = var.vpc_id

  tags = merge(var.tags, {
    Name = "${var.cluster_id}-redis-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group_rule" "redis_ingress" {
  count = length(var.allowed_security_group_ids)

  type                     = "ingress"
  from_port                = var.port
  to_port                  = var.port
  protocol                 = "tcp"
  security_group_id        = aws_security_group.redis.id
  source_security_group_id = var.allowed_security_group_ids[count.index]
  description              = "Redis access from allowed security groups"
}

resource "aws_security_group_rule" "redis_ingress_cidr" {
  count = length(var.allowed_cidr_blocks) > 0 ? 1 : 0

  type              = "ingress"
  from_port         = var.port
  to_port           = var.port
  protocol          = "tcp"
  security_group_id = aws_security_group.redis.id
  cidr_blocks       = var.allowed_cidr_blocks
  description       = "Redis access from allowed CIDR blocks"
}

resource "aws_security_group_rule" "redis_egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  security_group_id = aws_security_group.redis.id
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "Allow all outbound traffic"
}

# ElastiCache Replication Group (Redis Cluster Mode Disabled)
resource "aws_elasticache_replication_group" "main" {
  count = var.cluster_mode_enabled ? 0 : 1

  replication_group_id = var.cluster_id
  description          = var.description

  # Engine
  engine               = "redis"
  engine_version       = var.engine_version
  node_type            = var.node_type
  port                 = var.port
  parameter_group_name = aws_elasticache_parameter_group.main.name

  # Replication
  num_cache_clusters         = var.num_cache_nodes
  automatic_failover_enabled = var.num_cache_nodes > 1 ? true : false
  multi_az_enabled           = var.num_cache_nodes > 1 ? var.multi_az_enabled : false

  # Network
  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  # Security
  at_rest_encryption_enabled = var.at_rest_encryption_enabled
  transit_encryption_enabled = var.transit_encryption_enabled
  auth_token                 = var.transit_encryption_enabled ? var.auth_token : null
  kms_key_id                 = var.kms_key_arn

  # Maintenance
  maintenance_window         = var.maintenance_window
  snapshot_window            = var.snapshot_window
  snapshot_retention_limit   = var.snapshot_retention_limit
  auto_minor_version_upgrade = var.auto_minor_version_upgrade
  apply_immediately          = var.apply_immediately

  # Notifications
  notification_topic_arn = var.notification_topic_arn

  tags = var.tags

  lifecycle {
    ignore_changes = [num_cache_clusters]
  }
}

# ElastiCache Replication Group (Redis Cluster Mode Enabled)
resource "aws_elasticache_replication_group" "cluster_mode" {
  count = var.cluster_mode_enabled ? 1 : 0

  replication_group_id = var.cluster_id
  description          = var.description

  # Engine
  engine               = "redis"
  engine_version       = var.engine_version
  node_type            = var.node_type
  port                 = var.port
  parameter_group_name = aws_elasticache_parameter_group.main.name

  # Cluster Mode
  num_node_groups         = var.num_node_groups
  replicas_per_node_group = var.replicas_per_node_group

  # Replication
  automatic_failover_enabled = true
  multi_az_enabled           = var.multi_az_enabled

  # Network
  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  # Security
  at_rest_encryption_enabled = var.at_rest_encryption_enabled
  transit_encryption_enabled = var.transit_encryption_enabled
  auth_token                 = var.transit_encryption_enabled ? var.auth_token : null
  kms_key_id                 = var.kms_key_arn

  # Maintenance
  maintenance_window         = var.maintenance_window
  snapshot_window            = var.snapshot_window
  snapshot_retention_limit   = var.snapshot_retention_limit
  auto_minor_version_upgrade = var.auto_minor_version_upgrade
  apply_immediately          = var.apply_immediately

  # Notifications
  notification_topic_arn = var.notification_topic_arn

  tags = var.tags
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  count = var.create_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${var.cluster_id}-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = var.cpu_alarm_threshold
  alarm_description   = "ElastiCache CPU utilization is too high"
  alarm_actions       = var.alarm_actions

  dimensions = {
    CacheClusterId = var.cluster_id
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "memory_high" {
  count = var.create_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${var.cluster_id}-memory-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "DatabaseMemoryUsagePercentage"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = var.memory_alarm_threshold
  alarm_description   = "ElastiCache memory usage is too high"
  alarm_actions       = var.alarm_actions

  dimensions = {
    CacheClusterId = var.cluster_id
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "connections_high" {
  count = var.create_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${var.cluster_id}-connections-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CurrConnections"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = var.connections_alarm_threshold
  alarm_description   = "ElastiCache connections are too high"
  alarm_actions       = var.alarm_actions

  dimensions = {
    CacheClusterId = var.cluster_id
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "evictions" {
  count = var.create_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${var.cluster_id}-evictions"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "Evictions"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Sum"
  threshold           = var.evictions_alarm_threshold
  alarm_description   = "ElastiCache evictions are too high"
  alarm_actions       = var.alarm_actions

  dimensions = {
    CacheClusterId = var.cluster_id
  }

  tags = var.tags
}
