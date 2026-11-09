resource "aws_acm_certificate" "web" {
  domain_name       = var.hostname
  validation_method = "DNS"
  lifecycle {
    create_before_destroy = true
  }
}
resource "aws_route53_record" "validation" {
  zone_id = var.zone_id
  name    = one(aws_acm_certificate.web.domain_validation_options).resource_record_name
  type    = one(aws_acm_certificate.web.domain_validation_options).resource_record_type
  records = [one(aws_acm_certificate.web.domain_validation_options).resource_record_value]
  ttl     = 300
}
resource "aws_acm_certificate_validation" "web" {
  certificate_arn         = aws_acm_certificate.web.arn
  validation_record_fqdns = [aws_route53_record.validation.fqdn]
}
resource "aws_cognito_user_pool" "team" {
  name                     = local.name
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  admin_create_user_config {
    allow_admin_create_user_only = true
  }
}
data "aws_caller_identity" "current" {}
resource "aws_cognito_user_pool_domain" "team" {
  domain       = "${local.name}-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.team.id
}
resource "aws_cognito_user_pool_client" "alb" {
  name                                 = local.name
  user_pool_id                         = aws_cognito_user_pool.team.id
  generate_secret                      = true
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = ["${local.origin}/oauth2/idpresponse"]
}
resource "aws_lb" "web" {
  name            = local.name
  subnets         = values(data.aws_subnet.public)[*].id
  security_groups = [aws_security_group.factory["alb"].id]
  idle_timeout    = 180
}
resource "aws_lb_target_group" "app" {
  name                 = local.name
  vpc_id               = data.aws_vpc.dev.id
  target_type          = "ip"
  port                 = 8080
  protocol             = "HTTP"
  deregistration_delay = 15
  health_check {
    path    = "/api/health"
    matcher = "200"
  }
}
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.web.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = "redirect"
    redirect {
      host        = var.hostname
      protocol    = "HTTPS"
      port        = "443"
      status_code = "HTTP_301"
    }
  }
}
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.web.arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = aws_acm_certificate_validation.web.certificate_arn
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  default_action {
    order = 1
    type  = "authenticate-cognito"
    authenticate_cognito {
      user_pool_arn              = aws_cognito_user_pool.team.arn
      user_pool_client_id        = aws_cognito_user_pool_client.alb.id
      user_pool_domain           = aws_cognito_user_pool_domain.team.domain
      scope                      = "openid email"
      session_timeout            = 28800
      on_unauthenticated_request = "authenticate"
    }
  }
  default_action {
    order            = 2
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}
resource "aws_route53_record" "factory" {
  zone_id = var.zone_id
  name    = var.hostname
  type    = "A"
  alias {
    name                   = aws_lb.web.dns_name
    zone_id                = aws_lb.web.zone_id
    evaluate_target_health = true
  }
}
