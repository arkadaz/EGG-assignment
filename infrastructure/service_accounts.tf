resource "google_service_account" "jobs" {
  account_id   = "egg-rag-jobs"
  display_name = "egg-rag migrate and ingest jobs"
}

resource "google_service_account" "search" {
  account_id   = "egg-rag-search"
  display_name = "egg-rag search service"
}

resource "google_project_iam_member" "jobs_cloudsql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = google_service_account.jobs.member
}

resource "google_project_iam_member" "search_cloudsql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = google_service_account.search.member
}

resource "google_secret_manager_secret_iam_member" "jobs_database_url" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.jobs.member
}

resource "google_secret_manager_secret_iam_member" "search_database_url" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.search.member
}

resource "google_secret_manager_secret_iam_member" "search_llm_api" {
  secret_id = data.google_secret_manager_secret.llm_api.id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.search.member
}
