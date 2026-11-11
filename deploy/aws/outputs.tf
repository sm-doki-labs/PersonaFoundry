output "url" {
  value = local.origin
}
output "ecr_url" {
  value = aws_ecr_repository.app.repository_url
}
output "cluster" {
  value = aws_ecs_cluster.app.name
}
output "service" {
  value = aws_ecs_service.app.name
}
output "user_pool_id" {
  value = aws_cognito_user_pool.team.id
}
output "region" {
  value = var.region
}
