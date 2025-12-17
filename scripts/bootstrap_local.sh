#!/usr/bin/env bash
set -euo pipefail

AWS_ENDPOINT=${AWS_ENDPOINT_URL:-http://localhost:4566}
REGION=${AWS_REGION:-us-east-1}
BUCKET=${S3_BUCKET:-tip-dev}
QUEUE_NAME=${SQS_QUEUE_NAME:-events_out}
DLQ_NAME=${SQS_DLQ_NAME:-events_out_dlq}

aws --endpoint-url "$AWS_ENDPOINT" --region "$REGION" s3api create-bucket --bucket "$BUCKET" || true

DLQ_URL=$(aws --endpoint-url "$AWS_ENDPOINT" --region "$REGION" sqs create-queue --queue-name "$DLQ_NAME" --query QueueUrl --output text)

REDRIVE=$(jq -nc --arg arn "arn:aws:sqs:$REGION:000000000000:$DLQ_NAME" '{"deadLetterTargetArn":$arn,"maxReceiveCount":5}')
QUEUE_URL=$(aws --endpoint-url "$AWS_ENDPOINT" --region "$REGION" sqs create-queue --queue-name "$QUEUE_NAME" --attributes RedrivePolicy="$REDRIVE" --query QueueUrl --output text)

echo "Export these env vars:"
echo "S3_BUCKET=$BUCKET"
echo "AWS_REGION=$REGION"
echo "AWS_ENDPOINT_URL=$AWS_ENDPOINT"
echo "SQS_QUEUE_URL=$QUEUE_URL"
echo "SQS_DLQ_URL=$DLQ_URL"
