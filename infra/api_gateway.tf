# HTTP API (not REST API): ~1/3 the cost per request and no fixed monthly
# minimum. CORS is left to FastAPI's CORSMiddleware (CORS_ORIGINS), so no
# cors_configuration here (API Gateway's would shadow it).
resource "aws_apigatewayv2_api" "api" {
  name          = "${var.project_name}-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.fn["api"].invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# Same integration as $default; these exist only so they can get a stricter
# throttle (registering calls Yahoo synchronously, and both start backfills).
# Replaces the Redis-backed RATE_LIMIT_WRITE_PER_MINUTE, which is a no-op in AWS.
resource "aws_apigatewayv2_route" "register_instrument" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "POST /v1/instruments"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "refresh_instrument" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "POST /v1/instruments/{ticker}/refresh"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  # No Redis in AWS, so the app's per-key limiter fails open: this free,
  # native throttle is the guardrail instead (API-wide, not per key -- HTTP
  # APIs have no usage plans). Well above expected quant-app traffic, well
  # below "Lambda/Supabase bill or saturation" territory. Over the limit
  # clients get 429 from API Gateway without invoking the Lambda.
  default_route_settings {
    throttling_rate_limit  = var.api_throttling_rate_limit
    throttling_burst_limit = var.api_throttling_burst_limit
  }

  route_settings {
    route_key              = aws_apigatewayv2_route.register_instrument.route_key
    throttling_rate_limit  = var.register_throttling_rate_limit
    throttling_burst_limit = var.register_throttling_burst_limit
  }

  route_settings {
    route_key              = aws_apigatewayv2_route.refresh_instrument.route_key
    throttling_rate_limit  = var.register_throttling_rate_limit
    throttling_burst_limit = var.register_throttling_burst_limit
  }
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fn["api"].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}
