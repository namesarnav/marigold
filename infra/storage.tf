# One bucket, two prefixes: uploaded PDFs and model artifacts. A single bucket
# keeps the request-cost and management surface small; the prefixes are what the
# lifecycle rules key off.

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "artifacts" {
  bucket = "${var.project}-artifacts-${random_id.bucket_suffix.hex}"

  tags = {
    Name = "${var.project}-artifacts"
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Versioning is on for the model artifacts: a bad training run that overwrites a
# checkpoint should be recoverable. The lifecycle rules below stop old versions
# from accumulating cost indefinitely.
resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket     = aws_s3_bucket.artifacts.id
  depends_on = [aws_s3_bucket_versioning.artifacts]

  # Uploaded PDFs are only needed until text extraction and card generation
  # finish; the extracted text is what the app actually reads afterwards.
  # Keeping them for 90 days allows re-generating cards without a re-upload.
  rule {
    id     = "expire-uploaded-pdfs"
    status = "Enabled"

    filter {
      prefix = "uploads/"
    }

    expiration {
      days = 90
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }

  # Superseded model checkpoints: keep a short rollback window, then delete.
  rule {
    id     = "prune-old-model-versions"
    status = "Enabled"

    filter {
      prefix = "models/"
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  # Multipart uploads that failed halfway are billed for their uploaded parts
  # until aborted, and are invisible in the console's object listing.
  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 3
    }
  }
}
