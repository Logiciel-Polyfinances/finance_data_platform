output "api_url" {
  description = "Base URL of the API (internal UI at <api_url>/app/, docs at <api_url>/docs)"
  value       = aws_apigatewayv2_api.api.api_endpoint
}

output "data_lake_bucket" {
  description = "Bronze/Silver S3 bucket (BUCKET_ID)"
  value       = aws_s3_bucket.data_lake.id
}

output "ecr_repository_url" {
  value = aws_ecr_repository.lambda.repository_url
}

output "prices_daily_state_machine_arn" {
  value = aws_sfn_state_machine.prices_daily.arn
}

output "fanout_state_machine_arn" {
  value = aws_sfn_state_machine.fanout.arn
}

output "fred_macro_state_machine_arn" {
  value = aws_sfn_state_machine.fred_macro.arn
}

output "lambda_function_names" {
  value = { for k, fn in aws_lambda_function.fn : k => fn.function_name }
}

output "api_key_ssm_parameter" {
  description = "SSM parameter holding the master X-API-Key (aws ssm get-parameter --with-decryption --name ...)"
  value       = aws_ssm_parameter.api_key.name
}
