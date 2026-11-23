terraform {
  required_version = ">= 1.11"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }

  backend "gcs" {
    bucket = "egg-interview-tfstate"
    prefix = "egg-rag"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
