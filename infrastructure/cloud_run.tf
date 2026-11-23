resource "google_cloud_run_v2_job" "migrate" {
  name                = "egg-rag-migrate"
  location            = var.region
  deletion_protection = false
  run_execution_token = var.image_tag

  template {
    template {
      service_account = google_service_account.jobs.email

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.main.connection_name]
        }
      }

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/egg-rag/migrate:${var.image_tag}"

        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_url.secret_id
              version = "latest"
            }
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_iam_member.jobs_database_url,
  ]
}

resource "google_cloud_run_v2_job" "ingest" {
  name                = "egg-rag-ingest"
  location            = var.region
  deletion_protection = false
  run_execution_token = var.image_tag

  template {
    template {
      service_account       = google_service_account.jobs.email
      timeout               = "1800s"
      execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.main.connection_name]
        }
      }

      volumes {
        name = "models"
        gcs {
          bucket        = var.models_bucket
          read_only     = true
          mount_options = ["implicit-dirs"]
        }
      }

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/egg-rag/ingest:${var.image_tag}"

        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }

        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_url.secret_id
              version = "latest"
            }
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }

        volume_mounts {
          name       = "models"
          mount_path = "/models"
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_iam_member.jobs_database_url,
    google_storage_bucket_iam_member.jobs_models,
    google_cloud_run_v2_job.migrate,
  ]
}

resource "google_cloud_run_v2_service" "search" {
  name                = "egg-rag-search"
  location            = var.region
  deletion_protection = false

  template {
    service_account       = google_service_account.search.email
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }

    volumes {
      name = "models"
      gcs {
        bucket        = var.models_bucket
        read_only     = true
        mount_options = ["implicit-dirs"]
      }
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/egg-rag/search:${var.image_tag}"

      resources {
        limits = {
          cpu    = "1"
          memory = "4Gi"
        }
        startup_cpu_boost = true
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "LLM_API"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.llm_api.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "ALLOWED_EMAIL"
        value = var.allowed_email
      }

      env {
        name  = "GOOGLE_CLIENT_ID"
        value = var.google_client_id
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      volume_mounts {
        name       = "models"
        mount_path = "/models"
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_iam_member.search_database_url,
    google_secret_manager_secret_iam_member.search_llm_api,
    google_storage_bucket_iam_member.search_models,
    google_cloud_run_v2_job.ingest,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.search.name
  location = google_cloud_run_v2_service.search.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
