variable "region" {
  default = "ap-northeast-2"
}
variable "vpc_name" {
  default = "influencer-dev-vpc"
}
variable "public_subnet_names" {
  default = ["influencer-dev-public-ap-northeast-2a", "influencer-dev-public-ap-northeast-2c"]
}
variable "private_subnet_names" {
  default = ["influencer-dev-private-ap-northeast-2a", "influencer-dev-private-ap-northeast-2c"]
}
variable "zone_id" {
  default = "Z00132772A7MXMF56ML5V"
}
variable "hostname" {
  default = "factory.dev.dokilabs.com"
}
data "aws_vpc" "dev" {
  filter {
    name   = "tag:Name"
    values = [var.vpc_name]
  }
}
data "aws_subnet" "public" {
  for_each = toset(var.public_subnet_names)
  vpc_id   = data.aws_vpc.dev.id
  tags     = { Name = each.key }
}
data "aws_subnet" "private" {
  for_each = toset(var.private_subnet_names)
  vpc_id   = data.aws_vpc.dev.id
  tags     = { Name = each.key }
}
locals {
  name   = "persona-factory-dev"
  origin = "https://${var.hostname}"
  prefix = "sources/"
}
resource "aws_security_group" "factory" {
  for_each = toset(["alb", "task", "efs"])
  name     = "${local.name}-${each.key}"
  vpc_id   = data.aws_vpc.dev.id
}
resource "aws_vpc_security_group_ingress_rule" "web" {
  for_each          = toset(["80", "443"])
  security_group_id = aws_security_group.factory["alb"].id
  ip_protocol       = "tcp"
  from_port         = tonumber(each.key)
  to_port           = tonumber(each.key)
  cidr_ipv4         = "0.0.0.0/0"
}
resource "aws_vpc_security_group_ingress_rule" "app" {
  security_group_id            = aws_security_group.factory["task"].id
  referenced_security_group_id = aws_security_group.factory["alb"].id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
}
resource "aws_vpc_security_group_ingress_rule" "nfs" {
  security_group_id            = aws_security_group.factory["efs"].id
  referenced_security_group_id = aws_security_group.factory["task"].id
  ip_protocol                  = "tcp"
  from_port                    = 2049
  to_port                      = 2049
}
resource "aws_vpc_security_group_egress_rule" "https" {
  for_each          = toset(["alb", "task"])
  security_group_id = aws_security_group.factory[each.key].id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}
resource "aws_vpc_security_group_egress_rule" "app" {
  security_group_id            = aws_security_group.factory["alb"].id
  referenced_security_group_id = aws_security_group.factory["task"].id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
}
resource "aws_vpc_security_group_egress_rule" "nfs" {
  security_group_id            = aws_security_group.factory["task"].id
  referenced_security_group_id = aws_security_group.factory["efs"].id
  ip_protocol                  = "tcp"
  from_port                    = 2049
  to_port                      = 2049
}
