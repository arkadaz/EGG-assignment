output "search_url" {
  value = google_cloud_run_v2_service.search.uri
}

output "database_instance" {
  value = google_sql_database_instance.main.connection_name
}
