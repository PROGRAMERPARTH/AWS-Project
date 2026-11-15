# =============================================================================
# Cloud Café Order Processor - Main Infrastructure
# =============================================================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# -----------------------------------------------------------------------------
# S3 Bucket
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "orders" {
  bucket        = var.s3_bucket_name
  force_destroy = true

  tags = {
    Project = var.project_name
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "orders_encryption" {
  bucket = aws_s3_bucket.orders.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "orders_public_access" {
  bucket = aws_s3_bucket.orders.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# -----------------------------------------------------------------------------
# SNS Topic & Subscription
# -----------------------------------------------------------------------------
resource "aws_sns_topic" "orders" {
  name = "${var.project_name}-order-notifications"

  tags = {
    Project = var.project_name
  }
}

resource "aws_sns_topic_subscription" "order_email" {
  topic_arn = aws_sns_topic.orders.arn
  protocol  = "email"
  endpoint  = var.sns_email
}

# -----------------------------------------------------------------------------
# Lambda Function
# -----------------------------------------------------------------------------
data "archive_file" "lambda" {
  type        = "zip"
  source_file = "${path.module}/../lambda/lambda_function.py"
  output_path = "${path.module}/lambda_function.zip"
}

resource "aws_lambda_function" "order_processor" {
  function_name    = var.lambda_function_name
  runtime          = "python3.12"
  handler          = "lambda_function.lambda_handler"
  role             = aws_iam_role.cloud_cafe_lambda_role.arn
  timeout          = 30
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  environment {
    variables = {
      S3_BUCKET_NAME = aws_s3_bucket.orders.id
      SNS_TOPIC_ARN  = aws_sns_topic.orders.arn
      AWS_REGION     = var.aws_region
    }
  }

  tags = {
    Project = var.project_name
  }
}

# -----------------------------------------------------------------------------
# Lambda Permission (allow S3 to invoke)
# -----------------------------------------------------------------------------
resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.order_processor.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.orders.arn
}

# -----------------------------------------------------------------------------
# S3 Bucket Notification (trigger Lambda on new orders)
# -----------------------------------------------------------------------------
resource "aws_s3_bucket_notification" "order_created" {
  bucket = aws_s3_bucket.orders.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.order_processor.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "orders/"
    filter_suffix       = ".json"
  }

  depends_on = [aws_lambda_permission.allow_s3]
}
