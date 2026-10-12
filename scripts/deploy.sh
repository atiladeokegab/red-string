#!/usr/bin/env bash
# Deploy the committed HEAD to Cloud Run and prove it answers.
#   PROJECT=<gcp-project-id> [REGION=europe-west1] [SERVICE=hackathon-starter] scripts/deploy.sh
# One-time GCP setup and rollback: docs/deploy.md.
set -euo pipefail

: "${PROJECT:?set PROJECT to the GCP project id}"
REGION="${REGION:-europe-west1}"
SERVICE="${SERVICE:-hackathon-starter}"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "deploy: the working tree is dirty; commit first so the commit label names what ships" >&2
  exit 1
fi
COMMIT="$(git rev-parse --short=12 HEAD)"

# ponytail: --max-instances 1 keeps the JSON store in one place; lift it with a shared store.
gcloud run deploy "$SERVICE" --source . --region "$REGION" --project "$PROJECT" \
  --allow-unauthenticated \
  --set-secrets ANTHROPIC_API_KEY=anthropic-api-key:latest,ADMIN_PASSWORD=admin-password:latest \
  --set-env-vars MODE=cloud \
  --labels "commit=$COMMIT" \
  --max-instances 1 \
  --quiet

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" \
  --format 'value(status.url)')"
echo "deployed $COMMIT to $URL"
curl -fsS --max-time 30 "$URL/health"
echo
