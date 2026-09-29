# Every function runs the same container image (Dockerfile.lambda); only the
# handler (image_config.command), sizing and role differ.
locals {
  image_uri = "${aws_ecr_repository.lambda.repository_url}:${var.image_tag}"

  # memory: pandas/polars/pyarrow jobs get 1 GB (Lambda CPU scales with memory,
  # and it also shortens cold starts of this heavy image); timeout: per-ticker
  # steps are short, whole-universe steps get the 15 min maximum.
  lambda_functions = {
    api = {
      role        = "api"
      command     = "src.main.handler"
      memory_size = 1024
      # Below API Gateway's 30s integration limit, so the function times out
      # (and logs why) before the gateway does.
      timeout     = 28
      description = "FastAPI (Mangum) behind API Gateway HTTP API"
    }
    get-tickers = {
      role        = "etl"
      command     = "src.lambda_handlers.universe.handler"
      memory_size = 512
      timeout     = 60
      description = "Resolve the ticker universe for a Step Functions run"
    }
    prices-bronze = {
      role        = "etl"
      command     = "src.lambda_handlers.prices.bronze_handler"
      memory_size = 1024
      timeout     = 900 # one yf.download for the whole universe (or a multi-year backfill)
      description = "Daily prices: Yahoo -> bronze"
    }
    prices-silver = {
      role        = "etl"
      command     = "src.lambda_handlers.prices.silver_handler"
      memory_size = 1024
      timeout     = 300
      description = "Daily prices: bronze -> silver"
    }
    prices-gold = {
      role        = "etl"
      command     = "src.lambda_handlers.prices.gold_handler"
      memory_size = 1024
      timeout     = 300
      description = "Daily prices: silver -> gold (Supabase)"
    }
    sec-fundamentals = {
      role        = "etl"
      command     = "src.lambda_handlers.per_ticker.sec_fundamentals_handler"
      memory_size = 1024
      timeout     = 300 # companyfacts = a company's entire XBRL history in one JSON
      description = "SEC EDGAR fundamentals for one ticker"
    }
    yf-fundamentals = {
      role        = "etl"
      command     = "src.lambda_handlers.per_ticker.yf_fundamentals_handler"
      memory_size = 1024
      timeout     = 300
      description = "yfinance fundamentals for one non-US ticker"
    }
    figi = {
      role        = "etl"
      command     = "src.lambda_handlers.per_ticker.figi_handler"
      memory_size = 512
      timeout     = 120
      description = "OpenFIGI mapping for one ticker"
    }
    fred-series = {
      role        = "etl"
      command     = "src.lambda_handlers.fred_macro.series_handler"
      memory_size = 512
      timeout     = 60
      description = "Resolve the FRED series list for a Step Functions run"
    }
    fred-macro = {
      role        = "etl"
      command     = "src.lambda_handlers.fred_macro.handler"
      memory_size = 1024
      timeout     = 300
      description = "FRED macro/FX: one series"
    }
    fundamental-ratios = {
      role        = "etl"
      command     = "src.lambda_handlers.derived.ratios_handler"
      memory_size = 1024
      timeout     = 900
      description = "Derived fundamental ratios for the whole universe"
    }
    metrics = {
      role        = "etl"
      command     = "src.lambda_handlers.derived.metrics_handler"
      memory_size = 1024
      timeout     = 900
      description = "Derived risk KPIs + alpha/beta for the whole universe"
    }
  }

  lambda_common_env = {
    # Anything but "local" keeps the API key guard on (src/api/deps.py).
    ENV       = "prod"
    BUCKET_ID = aws_s3_bucket.data_lake.id
    # Resolved from SSM at cold start by src/core/ssm.py.
    DATABASE_URL_SSM_PARAM = local.ssm_database_url
    # Supabase's transaction pooler does the pooling (see Settings.db_null_pool).
    DB_NULL_POOL = "true"
    LOG_LEVEL    = "INFO"
    # AWS_REGION / AWS credentials are intentionally absent: the Lambda runtime
    # sets them itself (setting AWS_REGION fails the deploy). No REDIS_URL
    # either -- cache/rate limiter fail open; API Gateway throttles instead.
  }

  lambda_role_env = {
    api = {
      API_KEY_SSM_PARAM             = local.ssm_api_key
      CORS_ORIGINS                  = var.cors_origins
      PRICES_STATE_MACHINE_ARN      = local.prices_daily_sfn_arn
      FANOUT_STATE_MACHINE_ARN      = local.fanout_sfn_arn
      SEC_FUNDAMENTALS_FUNCTION_ARN = "arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:${var.project_name}-sec-fundamentals"
    }
    etl = {
      FRED_API_KEY_SSM_PARAM     = local.ssm_fred_api_key
      OPENFIGI_API_KEY_SSM_PARAM = local.ssm_openfigi_api_key
    }
  }

  lambda_role_arns = {
    api = aws_iam_role.api.arn
    etl = aws_iam_role.etl.arn
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each = local.lambda_functions

  name              = "/aws/lambda/${var.project_name}-${each.key}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "fn" {
  for_each = local.lambda_functions

  function_name = "${var.project_name}-${each.key}"
  description   = each.value.description
  role          = local.lambda_role_arns[each.value.role]
  package_type  = "Image"
  image_uri     = local.image_uri
  architectures = ["x86_64"]

  image_config {
    command = [each.value.command]
  }

  memory_size = each.value.memory_size
  timeout     = each.value.timeout

  environment {
    variables = merge(local.lambda_common_env, local.lambda_role_env[each.value.role])
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.api,
    aws_iam_role_policy.etl,
    aws_ecr_repository_policy.lambda,
  ]
}

# The two functions EventBridge Scheduler invokes directly are invoked
# asynchronously: retry a failed run twice, like the DAGs' default_args
# (Lambda spaces async retries ~1 then ~2 minutes apart).
resource "aws_lambda_function_event_invoke_config" "scheduled" {
  for_each = toset(["fundamental-ratios", "metrics"])

  function_name                = aws_lambda_function.fn[each.key].function_name
  maximum_retry_attempts       = 2
  maximum_event_age_in_seconds = 3600
}
