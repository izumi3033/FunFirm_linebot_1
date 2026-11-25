#!/usr/bin/env bash
# Cloud Run にデプロイする（コードを変えるたびに実行）
# 使い方: BOT=report bash deploy/deploy.sh   /   BOT=assistant bash deploy/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/config.sh

# 管理ボットだけ: 使える管理者のIDを .env.assistant から渡す（カンマを含むので区切り文字を @ にする）
ENV_VARS="^@^STORAGE_BACKEND=gcs@GCS_BUCKET=${BUCKET}@APP_MODULE=${APP_MODULE}"
if [ "${BOT}" = "assistant" ] && [ -f .env.assistant ]; then
  ALLOWED=$(grep -E '^ALLOWED_USER_IDS=' .env.assistant | cut -d= -f2- || true)
  ENV_VARS="${ENV_VARS}@ALLOWED_USER_IDS=${ALLOWED}"
fi

gcloud run deploy "${SERVICE}" \
  --project="${PROJECT_ID}" --region="${REGION}" --source=. \
  --service-account="${SA_EMAIL}" \
  --allow-unauthenticated \
  --min-instances=0 --max-instances=2 --memory=512Mi --timeout=60 \
  --set-env-vars="${ENV_VARS}" \
  --set-secrets="LINE_CHANNEL_SECRET=${SECRET_CHANNEL}:latest,LINE_CHANNEL_ACCESS_TOKEN=${SECRET_TOKEN}:latest"

URL=$(gcloud run services describe "${SERVICE}" --project="${PROJECT_ID}" --region="${REGION}" --format='value(status.url)')
echo ""
echo "== デプロイ完了（${BOT} ボット）"
echo "LINE Developers の Webhook URL に登録: ${URL}/callback"
