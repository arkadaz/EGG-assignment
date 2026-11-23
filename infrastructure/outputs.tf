output "search_urls" {
  value = google_cloud_run_v2_service.search.urls
}

output "database_instance" {
  value = google_sql_database_instance.main.connection_name
}
