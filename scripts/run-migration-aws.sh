#!/usr/bin/env bash
set -euo pipefail

# Run database migrations on AWS RDS
# Usage: ./scripts/run-migration-aws.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TF_DIR="$PROJECT_ROOT/infra/terraform"

cd "$TF_DIR"

# Get secret ARN from Terraform
SECRET_ARN=$(terraform output -raw db_credentials_secret_arn 2>/dev/null || echo "")

if [[ -z "$SECRET_ARN" ]]; then
  echo "Error: Could not get DB credentials secret ARN. Make sure Terraform has been applied."
  exit 1
fi

# Get PostgreSQL URL from Secrets Manager (standard format for psql)
echo "Fetching database credentials from Secrets Manager..."
PG_URL=$(aws secretsmanager get-secret-value --secret-id "$SECRET_ARN" --query SecretString --output text | jq -r '.url')

if [[ -z "$PG_URL" || "$PG_URL" == "null" ]]; then
  echo "Error: Could not retrieve database URL from secret"
  exit 1
fi

echo "Running migrations..."
cd "$PROJECT_ROOT"

# Note: This requires network access to RDS. 
# Options:
#   1. Run from a bastion host in the VPC
#   2. Use AWS Session Manager to connect to an ECS task
#   3. Set up VPN/Direct Connect
#   4. Temporarily allow your IP in the RDS security group

PG_DSN="$PG_URL" ./scripts/migrate.sh

echo "Migrations complete!"

