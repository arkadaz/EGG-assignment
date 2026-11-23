resource "google_artifact_registry_repository" "images" {
  repository_id = "egg-rag"
  location      = var.region
  format        = "DOCKER"
}
