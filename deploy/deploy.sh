#!/usr/bin/env bash
# Cloud Run にデプロイする（コードを変えるたびに実行）
# 使い方: PROJECT_ID=xxx ENV_NAME=dev bash deploy/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/config.sh

gcloud run deploy "${SERVICE}" \
  --project="${PROJECT_ID}" --region="${REGION}" --source=. \
  --service-account="${SA_EMAIL}" \
  --allow-unauthenticated \
  --min-instances=0 --max-instances=2 --memory=512Mi --timeout=60 \
  --set-env-vars="STORAGE_BACKEND=gcs,GCS_BUCKET=${BUCKET}" \
  --set-secrets="LINE_CHANNEL_SECRET=${SECRET_CHANNEL}:latest,LINE_CHANNEL_ACCESS_TOKEN=${SECRET_TOKEN}:latest"

URL=$(gcloud run services describe "${SERVICE}" --project="${PROJECT_ID}" --region="${REGION}" --format='value(status.url)')
echo ""
echo "== デプロイ完了"
echo "LINE Developers の Webhook URL に登録: ${URL}/callback"
