resource "google_secret_manager_secret" "database_url" {
  secret_id = "database-url"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = "postgresql://rag:${random_password.database.result}@/rag?host=/cloudsql/${google_sql_database_instance.main.connection_name}"
}

data "google_secret_manager_secret" "llm_api" {
  secret_id = "llm-api"
}
