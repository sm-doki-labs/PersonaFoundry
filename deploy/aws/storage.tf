resource "aws_efs_file_system" "state" {
  encrypted = true
  tags      = { Name = local.name }
}
resource "aws_efs_mount_target" "state" {
  for_each        = aws_subnet.public
  file_system_id  = aws_efs_file_system.state.id
  subnet_id       = each.value.id
  security_groups = [aws_security_group.factory["efs"].id]
}
resource "aws_efs_access_point" "data" {
  file_system_id = aws_efs_file_system.state.id
  posix_user {
    uid = 10001
    gid = 10001
  }
  root_directory {
    path = "/data"
    creation_info {
      owner_uid   = 10001
      owner_gid   = 10001
      permissions = "0750"
    }
  }
}
resource "aws_s3_bucket" "sources" {
  bucket_prefix = "${local.name}-"
}
resource "aws_s3_bucket_public_access_block" "sources" {
  bucket                  = aws_s3_bucket.sources.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "sources" {
  bucket = aws_s3_bucket.sources.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
resource "aws_s3_bucket_cors_configuration" "sources" {
  bucket = aws_s3_bucket.sources.id
  cors_rule {
    allowed_origins = [local.origin]
    allowed_headers = ["*"]
    allowed_methods = ["PUT"]
    expose_headers  = ["ETag"]
    max_age_seconds = 900
  }
}
resource "aws_secretsmanager_secret" "key" {
  for_each = toset(["OPENAI_API_KEY", "GEMINI_API_KEY"])
  name     = "${local.name}/${each.key}"
}
