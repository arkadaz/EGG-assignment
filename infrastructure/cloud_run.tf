resource "google_cloud_run_v2_job" "migrate" {
  name                = "egg-rag-migrate"
  location            = var.region
  deletion_protection = false

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
        image = "us-docker.pkg.dev/cloudrun/container/job"

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

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
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

  template {
    template {
      service_account = google_service_account.jobs.email
      timeout         = "1800s"

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.main.connection_name]
        }
      }

      containers {
        image = "us-docker.pkg.dev/cloudrun/container/job"

        resources {
          limits = {
            cpu    = "2"
            memory = "2Gi"
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
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }

  depends_on = [
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_iam_member.jobs_database_url,
  ]
}

resource "google_cloud_run_v2_service" "search" {
  name                = "egg-rag-search"
  location            = var.region
  deletion_protection = false

  template {
    service_account = google_service_account.search.email

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

    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
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

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }

  depends_on = [
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_iam_member.search_database_url,
    google_secret_manager_secret_iam_member.search_llm_api,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.search.name
  location = google_cloud_run_v2_service.search.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
