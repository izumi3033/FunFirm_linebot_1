#!/usr/bin/env bash
# 初回だけ実行: API有効化・バケット・サービスアカウント・シークレットを作る
# 使い方: PROJECT_ID=xxx ENV_NAME=dev bash deploy/setup_gcp.sh  （本番は ENV_NAME=prod）
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/config.sh
# LINEの鍵は環境ごとに分ける: .env.dev / .env.prod があればそれを、なければ .env を読む
ENV_FILE=".env.${ENV_NAME}"; [ -f "${ENV_FILE}" ] || ENV_FILE=".env"
echo "== LINEの鍵を ${ENV_FILE} から読みます"
set -a; source "${ENV_FILE}"; set +a

echo "== プロジェクト: ${PROJECT_ID} / 環境: ${ENV_NAME}"
gcloud config set project "${PROJECT_ID}"

echo "== APIを有効化"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com storage.googleapis.com

echo "== バケット ${BUCKET}（東京・均一アクセス・公開禁止）"
gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${BUCKET}" --location="${REGION}" \
    --uniform-bucket-level-access --public-access-prevention

echo "== サービスアカウント ${SA_EMAIL}"
gcloud iam service-accounts describe "${SA_EMAIL}" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "${SA_NAME}" --display-name="LINE bot (${ENV_NAME})"
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/storage.objectAdmin" >/dev/null

echo "== シークレット（.env の値を登録）"
put_secret () {  # $1=名前 $2=値
  if gcloud secrets describe "$1" >/dev/null 2>&1; then
    printf '%s' "$2" | gcloud secrets versions add "$1" --data-file=- >/dev/null
  else
    printf '%s' "$2" | gcloud secrets create "$1" --replication-policy=automatic --data-file=- >/dev/null
  fi
  gcloud secrets add-iam-policy-binding "$1" --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" >/dev/null
}
put_secret "${SECRET_CHANNEL}" "${LINE_CHANNEL_SECRET:?.envにLINE_CHANNEL_SECRETがありません}"
put_secret "${SECRET_TOKEN}"   "${LINE_CHANNEL_ACCESS_TOKEN:?.envにLINE_CHANNEL_ACCESS_TOKENがありません}"

echo "== 完了。次は deploy/deploy.sh を実行してください"
