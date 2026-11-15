# =============================================================================
# Cloud Café Order Processor - Outputs
# =============================================================================

output "s3_bucket_name" {
  description = "Name of the S3 bucket for order storage"
  value       = aws_s3_bucket.orders.id
}

output "s3_bucket_arn" {
  description = "ARN of the S3 bucket"
  value       = aws_s3_bucket.orders.arn
}

output "lambda_function_arn" {
  description = "ARN of the order processor Lambda function"
  value       = aws_lambda_function.order_processor.arn
}

output "lambda_function_name" {
  description = "Name of the order processor Lambda function"
  value       = aws_lambda_function.order_processor.function_name
}

output "sns_topic_arn" {
  description = "ARN of the SNS topic for order notifications"
  value       = aws_sns_topic.orders.arn
}

output "ec2_instance_profile_name" {
  description = "Name of the EC2 instance profile"
  value       = aws_iam_instance_profile.cloud_cafe_ec2_profile.name
}

output "ec2_role_arn" {
  description = "ARN of the EC2 IAM role"
  value       = aws_iam_role.cloud_cafe_ec2_role.arn
}
