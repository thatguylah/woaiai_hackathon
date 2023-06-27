output "queue_arn" {
  description = "ARN of the created SQS queue"
  value       = aws_sqs_queue.msg_incoming_queue.arn
}

output "bucket_arn" {
  description = "ARN of the created S3 bucket"
  value       = aws_s3_bucket.telegram_bot_images.arn
}

# output "lambda_role_arn" {
#   description = "ARN of the created IAM role for Lambda"
#   value       = aws_iam_role.lambda_role.arn
# }

# output "layer_arn" {
#   description = "ARN of the created Lambda layer"
#   value       = aws_lambda_layer_version.my_layer.arn
# }
