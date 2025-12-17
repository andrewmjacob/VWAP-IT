#!/usr/bin/env bash
set -euo pipefail

# Build and push Docker image to ECR
# Usage: ./scripts/push-image.sh [tag]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TF_DIR="$PROJECT_ROOT/infra/terraform"

TAG="${1:-latest}"

cd "$TF_DIR"

# Get ECR repository URL from Terraform output
ECR_URL=$(terraform output -raw ecr_repository_url 2>/dev/null || echo "")

if [[ -z "$ECR_URL" ]]; then
  echo "Error: Could not get ECR URL. Make sure Terraform has been applied."
  exit 1
fi

AWS_REGION=$(terraform output -raw 2>/dev/null | grep -A1 "aws_region" | tail -1 || echo "us-east-1")

echo "ECR Repository: $ECR_URL"
echo "Tag: $TAG"

# Login to ECR
echo "Logging into ECR..."
aws ecr get-login-password --region "${AWS_REGION:-us-east-1}" | \
  docker login --username AWS --password-stdin "${ECR_URL%/*}"

# Build and push
cd "$PROJECT_ROOT"
echo "Building Docker image..."
docker build -t "$ECR_URL:$TAG" .

echo "Pushing to ECR..."
docker push "$ECR_URL:$TAG"

echo "Done! Image pushed: $ECR_URL:$TAG"

# Update ECS service to use new image
echo ""
echo "To deploy the new image, run:"
echo "  aws ecs update-service --cluster tip-dev --service tip-dev-wsb-connector --force-new-deployment"

