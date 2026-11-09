resource "aws_ecr_repository" "app" {
  name                 = local.name
  image_tag_mutability = "IMMUTABLE_WITH_EXCLUSION"
  image_tag_mutability_exclusion_filter {
    filter      = "release"
    filter_type = "WILDCARD"
  }
  image_scanning_configuration {
    scan_on_push = true
  }
}
resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name}"
  retention_in_days = 14
}
resource "aws_ecs_cluster" "app" {
  name = local.name
}
locals {
  ecs_trust = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}
resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = local.ecs_trust
}
resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = local.ecs_trust
}
resource "aws_iam_role_policy" "execution" {
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = "ecr:GetAuthorizationToken", Resource = "*" },
      { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"], Resource = aws_ecr_repository.app.arn },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.app.arn}:*" },
      { Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = values(aws_secretsmanager_secret.key)[*].arn }
    ]
  })
}
resource "aws_iam_role_policy" "task" {
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource = "${aws_s3_bucket.sources.arn}/${local.prefix}*" },
      { Effect = "Allow", Action = "s3:ListBucket", Resource = aws_s3_bucket.sources.arn, Condition = { StringLike = { "s3:prefix" = "${local.prefix}*" } } },
      { Effect = "Allow", Action = ["elasticfilesystem:ClientMount", "elasticfilesystem:ClientWrite"], Resource = aws_efs_file_system.state.arn, Condition = { StringEquals = { "elasticfilesystem:AccessPointArn" = aws_efs_access_point.data.arn } } }
    ]
  })
}
resource "aws_ecs_task_definition" "app" {
  family                   = local.name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }
  volume {
    name = "state"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.state.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.data.id
        iam             = "ENABLED"
      }
    }
  }
  container_definitions = jsonencode([{
    name         = "factory"
    image        = "${aws_ecr_repository.app.repository_url}:release"
    essential    = true
    portMappings = [{ containerPort = 8080, protocol = "tcp" }]
    mountPoints  = [{ sourceVolume = "state", containerPath = "/data", readOnly = false }]
    environment = [for k, v in {
      CFP_SERVER_MODE  = "1", CFP_ROOT = "/data/factory", CFP_CONFIG = "/app/deploy/factory.server.toml",
      CFP_SOURCE_STORE = "s3", CFP_SOURCE_BUCKET = aws_s3_bucket.sources.id, CFP_SOURCE_PREFIX = local.prefix, AWS_REGION = var.region
    } : { name = k, value = v }]
    secrets = [for k, s in aws_secretsmanager_secret.key : { name = k, valueFrom = s.arn }]
    logConfiguration = { logDriver = "awslogs", options = {
      awslogs-group = aws_cloudwatch_log_group.app.name, awslogs-region = var.region, awslogs-stream-prefix = "app"
    } }
  }])
}
resource "aws_ecs_service" "app" {
  name                               = local.name
  cluster                            = aws_ecs_cluster.app.id
  task_definition                    = aws_ecs_task_definition.app.arn
  desired_count                      = 1
  launch_type                        = "FARGATE"
  platform_version                   = "1.4.0"
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100
  health_check_grace_period_seconds  = 60
  network_configuration {
    assign_public_ip = false
    subnets          = values(data.aws_subnet.private)[*].id
    security_groups  = [aws_security_group.factory["task"].id]
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "factory"
    container_port   = 8080
  }
  depends_on = [aws_lb_listener.https, aws_efs_mount_target.state, aws_iam_role_policy.task, aws_iam_role_policy.execution]
}
