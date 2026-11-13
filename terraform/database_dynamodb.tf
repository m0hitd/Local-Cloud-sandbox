variable "postgres_password" {
  description = "Password for the local PostgreSQL container. Must match docker-compose.yml."
  type        = string
  default     = "localdevpassword"
  sensitive   = true
}

resource "aws_dynamodb_table" "orders" {
  name         = "sandbox-orders"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "order_id"

  attribute {
    name = "order_id"
    type = "S"
  }
}

resource "aws_secretsmanager_secret" "postgres" {
  name                    = "sandbox/postgres/credentials"
  description             = "Connection details for the local PostgreSQL container"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "postgres" {
  secret_id = aws_secretsmanager_secret.postgres.id
  secret_string = jsonencode({
    username = "sandbox_admin"
    password = var.postgres_password
    host     = "localhost"
    port     = 5432
    dbname   = "cloud_sandbox_db"
  })
}
