# S3 Bucket for Data Lake
resource "aws_s3_bucket" "data_lake" {
  bucket = "${var.project_name}-${var.environment}-data-lake-${random_id.bucket_suffix.hex}"

  tags = {
    Name = "${var.project_name}-${var.environment}-data-lake"
  }
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Bucket versioning
resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Block public access
resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle rules for cost optimization
resource "aws_s3_bucket_lifecycle_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  # Move raw data to Infrequent Access after 30 days
  rule {
    id     = "raw-to-ia"
    status = "Enabled"

    filter {
      prefix = "raw/"
    }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }
  }

  # Move enriched data to IA after 60 days
  rule {
    id     = "enriched-to-ia"
    status = "Enabled"

    filter {
      prefix = "enriched/"
    }

    transition {
      days          = 60
      storage_class = "STANDARD_IA"
    }
  }

  # Keep events and indexes in standard longer (frequently queried)
  rule {
    id     = "events-to-ia"
    status = "Enabled"

    filter {
      prefix = "events/"
    }

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
  }
}

