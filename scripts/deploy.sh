#!/usr/bin/env bash
set -euo pipefail

# Deploy script for Trading Intelligence Platform
# Usage: ./scripts/deploy.sh [plan|apply|destroy]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TF_DIR="$PROJECT_ROOT/infra/terraform"

ACTION="${1:-plan}"

cd "$TF_DIR"

case "$ACTION" in
  init)
    echo "Initializing Terraform..."
    terraform init
    ;;
  plan)
    echo "Planning infrastructure changes..."
    terraform plan -out=tfplan
    ;;
  apply)
    if [[ -f tfplan ]]; then
      echo "Applying planned changes..."
      terraform apply tfplan
      rm -f tfplan
    else
      echo "No plan file found. Run 'deploy.sh plan' first, or use 'deploy.sh apply-direct'"
      exit 1
    fi
    ;;
  apply-direct)
    echo "Applying changes directly..."
    terraform apply -auto-approve
    ;;
  destroy)
    echo "WARNING: This will destroy all infrastructure!"
    read -p "Are you sure? (yes/no): " confirm
    if [[ "$confirm" == "yes" ]]; then
      terraform destroy
    else
      echo "Aborted."
    fi
    ;;
  output)
    terraform output
    ;;
  *)
    echo "Usage: $0 [init|plan|apply|apply-direct|destroy|output]"
    exit 1
    ;;
esac

