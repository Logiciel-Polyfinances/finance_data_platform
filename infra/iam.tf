data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

locals {
  ssm_parameter_arn_prefix = "arn:aws:ssm:${var.aws_region}:${var.aws_account_id}:parameter"
}

# Two roles instead of one shared role, so each side only reads the secrets it
# actually uses. Neither has any database permission: Gold is Supabase
# (outside AWS), reached over the public internet with credentials from SSM.
# No VPC either -- nothing private to reach, and staying out of a VPC avoids
# NAT gateway cost.

resource "aws_iam_role" "api" {
  name               = "${var.project_name}-api-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "api_permissions" {
  statement {
    sid       = "OwnLogGroup"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda["api"].arn}:*"]
  }

  # POST /v1/instruments lands the ticker's Yahoo .info in bronze/ before
  # validating it (run_register_ticker.fetch_ticker_info).
  statement {
    sid       = "DataLakeObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.data_lake.arn}/*"]
  }

  # Without ListBucket, S3 answers a GetObject on a missing key with 403
  # AccessDenied instead of 404 NoSuchKey.
  statement {
    sid       = "ListDataLake"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data_lake.arn]
  }

  statement {
    sid     = "ReadOwnSecrets"
    effect  = "Allow"
    actions = ["ssm:GetParameters", "ssm:GetParameter"]
    resources = [
      "${local.ssm_parameter_arn_prefix}${local.ssm_database_url}",
      "${local.ssm_parameter_arn_prefix}${local.ssm_api_key}",
    ]
  }

  # POST /v1/instruments and .../refresh start a ticker's price and SEC
  # fundamentals backfills.
  statement {
    sid       = "StartBackfills"
    effect    = "Allow"
    actions   = ["states:StartExecution"]
    resources = [local.prices_daily_sfn_arn, local.fanout_sfn_arn]
  }

  # SecureStrings use the AWS-managed alias/aws/ssm key; scoped by
  # kms:ViaService rather than a key lookup (same pattern as finXplore).
  statement {
    sid       = "DecryptSecretsViaSsm"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = ["arn:aws:kms:${var.aws_region}:${var.aws_account_id}:key/*"]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "api" {
  name   = "${var.project_name}-api-lambda-policy"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api_permissions.json
}

resource "aws_iam_role" "etl" {
  name               = "${var.project_name}-etl-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "etl_permissions" {
  statement {
    sid     = "OwnLogGroups"
    effect  = "Allow"
    actions = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [
      for name, fn in local.lambda_functions : "${aws_cloudwatch_log_group.lambda[name].arn}:*" if fn.role == "etl"
    ]
  }

  statement {
    sid       = "DataLakeObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.data_lake.arn}/*"]
  }

  statement {
    sid       = "ListDataLake"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data_lake.arn]
  }

  statement {
    sid     = "ReadOwnSecrets"
    effect  = "Allow"
    actions = ["ssm:GetParameters", "ssm:GetParameter"]
    resources = [
      "${local.ssm_parameter_arn_prefix}${local.ssm_database_url}",
      "${local.ssm_parameter_arn_prefix}${local.ssm_fred_api_key}",
      "${local.ssm_parameter_arn_prefix}${local.ssm_openfigi_api_key}",
    ]
  }

  statement {
    sid       = "DecryptSecretsViaSsm"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = ["arn:aws:kms:${var.aws_region}:${var.aws_account_id}:key/*"]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "etl" {
  name   = "${var.project_name}-etl-lambda-policy"
  role   = aws_iam_role.etl.id
  policy = data.aws_iam_policy_document.etl_permissions.json
}
