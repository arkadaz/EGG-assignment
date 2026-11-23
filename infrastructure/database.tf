resource "random_id" "database_suffix" {
  byte_length = 2
}

resource "google_sql_database_instance" "main" {
  name                = "egg-rag-${random_id.database_suffix.hex}"
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = false

  settings {
    tier              = "db-f1-micro"
    edition           = "ENTERPRISE"
    availability_type = "ZONAL"

    backup_configuration {
      enabled = true
    }
  }
}

resource "google_sql_database" "rag" {
  name            = "rag"
  instance        = google_sql_database_instance.main.name
  deletion_policy = "ABANDON"
}

resource "random_password" "database" {
  length  = 32
  special = false
}

resource "google_sql_user" "rag" {
  name            = "rag"
  instance        = google_sql_database_instance.main.name
  password        = random_password.database.result
  deletion_policy = "ABANDON"
}
