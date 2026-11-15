# =============================================================================
# Cloud Café Order Processor - Variables
# =============================================================================

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "s3_bucket_name" {
  description = "S3 bucket name for order storage (add a unique suffix to ensure global uniqueness)"
  type        = string
  default     = "cloud-cafe-orders"
}

variable "sns_email" {
  description = "Email address for order notifications"
  type        = string
}

variable "lambda_function_name" {
  description = "Name of the Lambda function"
  type        = string
  default     = "cloud-cafe-order-processor"
}

variable "ec2_instance_type" {
  description = "EC2 instance type for the order submission server"
  type        = string
  default     = "t3.medium"
}

variable "project_name" {
  description = "Project name used for tagging and resource naming"
  type        = string
  default     = "cloud-cafe"
}
