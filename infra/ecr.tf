# One repository, one image for every Lambda (API + ETL): see Dockerfile.lambda
# for why it's an image and not a zip. deploy.yml creates this repository first
# (terraform apply -target), pushes the image tagged with the commit SHA, then
# applies the rest of the stack with -var image_tag=<sha>.
resource "aws_ecr_repository" "lambda" {
  name                 = "${var.project_name}-lambda"
  image_tag_mutability = "MUTABLE" # a re-run of the same commit re-pushes the same tag

  # Basic scanning is free.
  image_scanning_configuration {
    scan_on_push = true
  }
}

# ECR's free tier is 500 MB-month; unchanged dependency layers are shared
# between images, but still cap history so old images don't accumulate.
resource "aws_ecr_lifecycle_policy" "lambda" {
  repository = aws_ecr_repository.lambda.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the 5 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

# Lets the Lambda service pull the image, restricted to this project's functions.
data "aws_iam_policy_document" "ecr_lambda_pull" {
  statement {
    sid     = "LambdaECRImageRetrievalPolicy"
    effect  = "Allow"
    actions = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "aws:sourceArn"
      values   = ["arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:${var.project_name}-*"]
    }
  }
}

resource "aws_ecr_repository_policy" "lambda" {
  repository = aws_ecr_repository.lambda.name
  policy     = data.aws_iam_policy_document.ecr_lambda_pull.json
}
