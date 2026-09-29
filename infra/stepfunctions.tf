# STANDARD state machines replace the Airflow DAGs that have more than one
# step. Definitions live in statemachines/*.asl.json (JSONata query language)
# and get the Lambda ARNs + the shared retry policy injected by templatefile().
locals {
  # Airflow default_args: retries=2, retry_delay=5min. Lambda-service hiccups
  # (throttling, transient invoke errors) get their own fast retries first.
  sfn_lambda_retry = jsonencode([
    {
      ErrorEquals = [
        "Lambda.ServiceException",
        "Lambda.AWSLambdaException",
        "Lambda.SdkClientException",
        "Lambda.TooManyRequestsException",
      ]
      IntervalSeconds = 2
      MaxAttempts     = 6
      BackoffRate     = 2
      JitterStrategy  = "FULL"
    },
    {
      ErrorEquals     = ["States.ALL"]
      IntervalSeconds = 300
      MaxAttempts     = 2
      BackoffRate     = 1
    },
  ])

  # Functions the fan-out machine may run per ticker (its input names one).
  fanout_item_functions = ["sec-fundamentals", "yf-fundamentals", "figi"]

  sfn_invoked_functions = concat(
    ["get-tickers", "prices-bronze", "prices-silver", "prices-gold", "fred-series", "fred-macro"],
    local.fanout_item_functions,
  )

  # ARNs built from names, not resource attributes: the API function (same
  # for_each as the functions these machines invoke) and its role policy need
  # them, and referencing aws_sfn_state_machine.* there is a dependency cycle.
  sfn_arn_prefix        = "arn:aws:states:${var.aws_region}:${var.aws_account_id}:stateMachine"
  prices_daily_sfn_name = "${var.project_name}-prices-daily"
  fanout_sfn_name       = "${var.project_name}-fanout"
  prices_daily_sfn_arn  = "${local.sfn_arn_prefix}:${local.prices_daily_sfn_name}"
  fanout_sfn_arn        = "${local.sfn_arn_prefix}:${local.fanout_sfn_name}"
}

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.aws_account_id]
    }
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${var.project_name}-sfn-role"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

# Only the pipeline functions the machines actually call (not the API, not the
# EventBridge-only jobs). ":*" covers qualified (version/alias) invocations.
data "aws_iam_policy_document" "sfn_permissions" {
  statement {
    sid     = "InvokePipelineFunctions"
    effect  = "Allow"
    actions = ["lambda:InvokeFunction"]
    resources = flatten([
      for name in local.sfn_invoked_functions : [
        aws_lambda_function.fn[name].arn,
        "${aws_lambda_function.fn[name].arn}:*",
      ]
    ])
  }
}

resource "aws_iam_role_policy" "sfn" {
  name   = "${var.project_name}-sfn-policy"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn_permissions.json
}

# No CloudWatch logging configured on purpose (log ingestion costs money);
# the Step Functions console keeps every execution's full history for 90 days.
resource "aws_sfn_state_machine" "prices_daily" {
  name     = local.prices_daily_sfn_name
  role_arn = aws_iam_role.sfn.arn
  type     = "STANDARD"

  definition = templatefile("${path.module}/statemachines/prices_daily.asl.json", {
    get_tickers_arn   = aws_lambda_function.fn["get-tickers"].arn
    prices_bronze_arn = aws_lambda_function.fn["prices-bronze"].arn
    prices_silver_arn = aws_lambda_function.fn["prices-silver"].arn
    prices_gold_arn   = aws_lambda_function.fn["prices-gold"].arn
    retry             = local.sfn_lambda_retry
  })

  depends_on = [aws_iam_role_policy.sfn]
}

resource "aws_sfn_state_machine" "fanout" {
  name     = local.fanout_sfn_name
  role_arn = aws_iam_role.sfn.arn
  type     = "STANDARD"

  definition = templatefile("${path.module}/statemachines/fanout.asl.json", {
    get_tickers_arn = aws_lambda_function.fn["get-tickers"].arn
    retry           = local.sfn_lambda_retry
  })

  depends_on = [aws_iam_role_policy.sfn]
}

resource "aws_sfn_state_machine" "fred_macro" {
  name     = "${var.project_name}-fred-macro"
  role_arn = aws_iam_role.sfn.arn
  type     = "STANDARD"

  definition = templatefile("${path.module}/statemachines/fred_macro.asl.json", {
    fred_series_arn = aws_lambda_function.fn["fred-series"].arn
    fred_macro_arn  = aws_lambda_function.fn["fred-macro"].arn
    retry           = local.sfn_lambda_retry
  })

  depends_on = [aws_iam_role_policy.sfn]
}
