# EventBridge Scheduler (not classic EventBridge rules): native timezone
# support, so the former DAG crons are kept as-is in America/Montreal (DST
# handled by AWS) instead of being hand-converted to UTC.
locals {
  # EventBridge cron fields: minutes hours day-of-month month day-of-week year.
  sfn_schedules = {
    prices-daily = {
      description = "yf_prices_1d_daily: 16:05 on weekdays"
      cron        = "cron(5 16 ? * MON-FRI *)"
      target_arn  = aws_sfn_state_machine.prices_daily.arn
      input       = {}
    }
    sec-fundamentals = {
      description = "sec_fundamentals_weekly: Monday 07:00, US tickers"
      cron        = "cron(0 7 ? * MON *)"
      target_arn  = aws_sfn_state_machine.fanout.arn
      # SEC EDGAR is the strictest upstream (10 req/s, fair-access policy).
      input = { mode = "us_only", run_function = aws_lambda_function.fn["sec-fundamentals"].arn, max_concurrency = 3 }
    }
    yf-fundamentals = {
      description = "yf_fundamentals_weekly: Monday 08:00, non-US tickers"
      cron        = "cron(0 8 ? * MON *)"
      target_arn  = aws_sfn_state_machine.fanout.arn
      input       = { mode = "non_us_only", run_function = aws_lambda_function.fn["yf-fundamentals"].arn, max_concurrency = 5 }
    }
    fred-macro = {
      description = "fred_macro_weekly: Monday 06:00"
      cron        = "cron(0 6 ? * MON *)"
      target_arn  = aws_sfn_state_machine.fred_macro.arn
      input       = {}
    }
    openfigi-mapping = {
      description = "openfigi_mapping_weekly: Monday 08:00, all tickers"
      cron        = "cron(0 8 ? * MON *)"
      target_arn  = aws_sfn_state_machine.fanout.arn
      input       = { mode = "all", run_function = aws_lambda_function.fn["figi"].arn, max_concurrency = 5 }
    }
  }

  lambda_schedules = {
    fundamental-ratios = {
      description = "fundamental_ratios_weekly: Monday 09:00 (after the fundamentals runs)"
      cron        = "cron(0 9 ? * MON *)"
      function    = "fundamental-ratios"
    }
    instrument-metrics = {
      description = "instrument_metrics_daily: 03:00 every day"
      cron        = "cron(0 3 * * ? *)"
      function    = "metrics"
    }
  }
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.aws_account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.project_name}-scheduler-role"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler_permissions" {
  statement {
    sid     = "StartStateMachines"
    effect  = "Allow"
    actions = ["states:StartExecution"]
    resources = [
      aws_sfn_state_machine.prices_daily.arn,
      aws_sfn_state_machine.fanout.arn,
      aws_sfn_state_machine.fred_macro.arn,
    ]
  }

  statement {
    sid       = "InvokeScheduledFunctions"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [for s in local.lambda_schedules : aws_lambda_function.fn[s.function].arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "${var.project_name}-scheduler-policy"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler_permissions.json
}

resource "aws_scheduler_schedule_group" "fdp" {
  name = var.project_name
}

resource "aws_scheduler_schedule" "sfn" {
  for_each = local.sfn_schedules

  name        = "${var.project_name}-${each.key}"
  group_name  = aws_scheduler_schedule_group.fdp.name
  description = each.value.description
  state       = var.schedules_enabled ? "ENABLED" : "DISABLED"

  schedule_expression          = each.value.cron
  schedule_expression_timezone = var.schedule_timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = each.value.target_arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode(each.value.input)

    # Retries of the *delivery* (StartExecution call) only; task-level retries
    # are in the state machines.
    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 3
    }
  }
}

resource "aws_scheduler_schedule" "lambda" {
  for_each = local.lambda_schedules

  name        = "${var.project_name}-${each.key}"
  group_name  = aws_scheduler_schedule_group.fdp.name
  description = each.value.description
  state       = var.schedules_enabled ? "ENABLED" : "DISABLED"

  schedule_expression          = each.value.cron
  schedule_expression_timezone = var.schedule_timezone

  flexible_time_window {
    mode = "OFF"
  }

  # Invoked asynchronously; the function's own retries (2) are configured by
  # aws_lambda_function_event_invoke_config.scheduled in lambda.tf.
  target {
    arn      = aws_lambda_function.fn[each.value.function].arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({})

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 3
    }
  }
}

# fred-macro moved from a direct Lambda target to its own state machine; same
# schedule name, so update it in place rather than destroy + create (which races
# on the name).
moved {
  from = aws_scheduler_schedule.lambda["fred-macro"]
  to   = aws_scheduler_schedule.sfn["fred-macro"]
}
