# RDS PostgreSQL Module - Production-ready RDS instance with Secrets Manager

# Random password for RDS
resource "random_password" "master" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# Secrets Manager for database credentials
resource "aws_secretsmanager_secret" "db_credentials" {
  name_prefix             = "${var.identifier}-credentials-"
  description             = "Database credentials for ${var.identifier}"
  recovery_window_in_days = var.secret_recovery_window_days

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = var.master_username
    password = random_password.master.result
    host     = aws_db_instance.main.address
    port     = aws_db_instance.main.port
    database = var.database_name
    engine   = "postgres"
  })

  depends_on = [aws_db_instance.main]
}

# DB Subnet Group
resource "aws_db_subnet_group" "main" {
  name_prefix = "${var.identifier}-"
  description = "Subnet group for ${var.identifier}"
  subnet_ids  = var.subnet_ids

  tags = merge(var.tags, {
    Name = "${var.identifier}-subnet-group"
  })
}

# DB Parameter Group
resource "aws_db_parameter_group" "main" {
  name_prefix = "${var.identifier}-"
  family      = var.parameter_group_family
  description = "Parameter group for ${var.identifier}"

  dynamic "parameter" {
    for_each = var.parameters
    content {
      name         = parameter.value.name
      value        = parameter.value.value
      apply_method = lookup(parameter.value, "apply_method", "immediate")
    }
  }

  # Recommended PostgreSQL parameters
  parameter {
    name  = "log_statement"
    value = "all"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements"
  }

  tags = var.tags

  lifecycle {
    create_before_destroy = true
  }
}

# Security Group
resource "aws_security_group" "db" {
  name_prefix = "${var.identifier}-db-"
  description = "Security group for ${var.identifier}"
  vpc_id      = var.vpc_id

  tags = merge(var.tags, {
    Name = "${var.identifier}-db-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group_rule" "db_ingress" {
  count = length(var.allowed_security_group_ids)

  type                     = "ingress"
  from_port                = var.port
  to_port                  = var.port
  protocol                 = "tcp"
  security_group_id        = aws_security_group.db.id
  source_security_group_id = var.allowed_security_group_ids[count.index]
  description              = "PostgreSQL access from allowed security groups"
}

resource "aws_security_group_rule" "db_ingress_cidr" {
  count = length(var.allowed_cidr_blocks) > 0 ? 1 : 0

  type              = "ingress"
  from_port         = var.port
  to_port           = var.port
  protocol          = "tcp"
  security_group_id = aws_security_group.db.id
  cidr_blocks       = var.allowed_cidr_blocks
  description       = "PostgreSQL access from allowed CIDR blocks"
}

resource "aws_security_group_rule" "db_egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  security_group_id = aws_security_group.db.id
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "Allow all outbound traffic"
}

# IAM Role for Enhanced Monitoring
resource "aws_iam_role" "rds_monitoring" {
  count = var.monitoring_interval > 0 ? 1 : 0

  name_prefix = "${var.identifier}-monitoring-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "monitoring.rds.amazonaws.com"
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  count = var.monitoring_interval > 0 ? 1 : 0

  role       = aws_iam_role.rds_monitoring[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# RDS Instance
resource "aws_db_instance" "main" {
  identifier = var.identifier

  # Engine
  engine               = "postgres"
  engine_version       = var.engine_version
  instance_class       = var.instance_class
  parameter_group_name = aws_db_parameter_group.main.name

  # Storage
  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type          = var.storage_type
  storage_encrypted     = true
  kms_key_id            = var.kms_key_arn

  # Database
  db_name  = var.database_name
  username = var.master_username
  password = random_password.master.result
  port     = var.port

  # Network
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false

  # High Availability
  multi_az = var.multi_az

  # Backup
  backup_retention_period   = var.backup_retention_period
  backup_window             = var.backup_window
  maintenance_window        = var.maintenance_window
  copy_tags_to_snapshot     = true
  delete_automated_backups  = false
  final_snapshot_identifier = "${var.identifier}-final-snapshot"
  skip_final_snapshot       = var.skip_final_snapshot

  # Performance Insights
  performance_insights_enabled          = var.performance_insights_enabled
  performance_insights_retention_period = var.performance_insights_enabled ? var.performance_insights_retention_period : null
  performance_insights_kms_key_id       = var.performance_insights_enabled ? var.kms_key_arn : null

  # Enhanced Monitoring
  monitoring_interval = var.monitoring_interval
  monitoring_role_arn = var.monitoring_interval > 0 ? aws_iam_role.rds_monitoring[0].arn : null

  # Logging
  enabled_cloudwatch_logs_exports = var.cloudwatch_logs_exports

  # Maintenance
  auto_minor_version_upgrade  = var.auto_minor_version_upgrade
  allow_major_version_upgrade = false
  apply_immediately           = var.apply_immediately
  deletion_protection         = var.deletion_protection

  # CA Certificate
  ca_cert_identifier = var.ca_cert_identifier

  tags = var.tags

  lifecycle {
    ignore_changes = [password]
  }
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  count = var.create_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${var.identifier}-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = var.cpu_alarm_threshold
  alarm_description   = "RDS CPU utilization is too high"
  alarm_actions       = var.alarm_actions

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "memory_low" {
  count = var.create_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${var.identifier}-memory-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 3
  metric_name         = "FreeableMemory"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = var.memory_alarm_threshold
  alarm_description   = "RDS freeable memory is too low"
  alarm_actions       = var.alarm_actions

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "storage_low" {
  count = var.create_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${var.identifier}-storage-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 3
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = var.storage_alarm_threshold
  alarm_description   = "RDS free storage space is too low"
  alarm_actions       = var.alarm_actions

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "connections_high" {
  count = var.create_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${var.identifier}-connections-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = var.connections_alarm_threshold
  alarm_description   = "RDS database connections are too high"
  alarm_actions       = var.alarm_actions

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  tags = var.tags
}
