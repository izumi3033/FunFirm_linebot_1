# デプロイ設定（環境ごとに書き換える）。dev = テスト用bot / prod = 本番bot
ENV_NAME="${ENV_NAME:-dev}"
PROJECT_ID="${PROJECT_ID:-ここにGCPプロジェクトID}"
REGION="asia-northeast1"                       # 東京
SERVICE="linebot-${ENV_NAME}"                  # Cloud Run のサービス名
BUCKET="${PROJECT_ID}-linebot-${ENV_NAME}"     # Cloud Storage のバケット名
SA_NAME="linebot-${ENV_NAME}"                  # Cloud Run が使うサービスアカウント
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SECRET_CHANNEL="line-channel-secret-${ENV_NAME}"
SECRET_TOKEN="line-channel-access-token-${ENV_NAME}"
