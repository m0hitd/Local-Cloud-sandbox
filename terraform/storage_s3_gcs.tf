resource "aws_s3_bucket" "artifacts" {
  bucket        = "sandbox-artifacts"
  force_destroy = true
}

resource "google_storage_bucket" "gcs_artifacts" {
  name                        = "sandbox-gcs-artifacts"
  location                    = "US"
  force_destroy               = true
  uniform_bucket_level_access = true
}
