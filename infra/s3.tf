# Bronze (raw JSON) and Silver (Parquet) data lake. One bucket with bronze/ and
# silver/ prefixes, not two buckets: that's the layout the code already uses
# (BUCKET_ID + write_bronze.py / write_silver.py key conventions, and each
# pipeline derives the silver bucket from the bronze URI). Gold lives in
# Supabase Postgres, not here.
resource "aws_s3_bucket" "data_lake" {
  bucket = "${var.project_name}-data-lake-${var.aws_account_id}"
}

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Versioning deliberately left off: every object is write-once (keys carry a
# run_id), and noncurrent versions would only add storage cost.

resource "aws_s3_bucket_lifecycle_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
