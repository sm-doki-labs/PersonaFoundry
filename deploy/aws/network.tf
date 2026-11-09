variable "region" {
  default = "ap-northeast-2"
}
variable "vpc_cidr" {
  description = "공장 전용 VPC 대역. 회사 dev VPC(10.0.0.0/16)와 겹치지 않게 둔다"
  default     = "10.42.0.0/16"
}
variable "azs" {
  default = ["ap-northeast-2a", "ap-northeast-2c"]
}
variable "zone_id" {
  default = "Z00132772A7MXMF56ML5V"
}
variable "hostname" {
  default = "factory.dev.dokilabs.com"
}
# 공장 전용 네트워크. 회사 dev VPC·NAT·보안 그룹과 아무것도 나눠 쓰지 않는다.
# 태스크는 공용 서브넷에서 자기 공인 IP로 바로 나간다(NAT 없음). 들어오는 길은 ALB뿐이다.
resource "aws_vpc" "factory" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "persona-factory-dev" }
}
resource "aws_internet_gateway" "factory" {
  vpc_id = aws_vpc.factory.id
  tags   = { Name = "persona-factory-dev" }
}
resource "aws_subnet" "public" {
  for_each                = { for i, az in var.azs : az => i }
  vpc_id                  = aws_vpc.factory.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, each.value)
  map_public_ip_on_launch = false
  tags                    = { Name = "persona-factory-dev-public-${each.key}" }
}
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.factory.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.factory.id
  }
  tags = { Name = "persona-factory-dev-public" }
}
resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}
# S3(원문 버킷·ECR 이미지 층)는 게이트웨이 엔드포인트로 VPC 안에서 받는다. 무료다.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.factory.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.public.id]
}
locals {
  name   = "persona-factory-dev"
  origin = "https://${var.hostname}"
  prefix = "sources/"
}
resource "aws_security_group" "factory" {
  for_each = toset(["alb", "task", "efs"])
  name     = "${local.name}-${each.key}"
  vpc_id   = aws_vpc.factory.id
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
