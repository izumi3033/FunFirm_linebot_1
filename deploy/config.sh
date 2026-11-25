# デプロイ設定。BOT でボットを、ENV_NAME で環境を選ぶ
#   BOT=report    … 日報ボット（FunFirm / linebot@funfirm.jp）
#   BOT=assistant … 管理ボット（FunFirm_host / linebot2@funfirm.jp）
BOT="${BOT:-report}"
ENV_NAME="${ENV_NAME:-dev}"
PROJECT_ID="${PROJECT_ID:-ここにGCPプロジェクトID}"
REGION="asia-northeast1"                       # 東京
SERVICE="${BOT}-bot-${ENV_NAME}"               # Cloud Run のサービス名（ボットごと）
APP_MODULE="${BOT}_bot.main:app"               # コンテナで動かすアプリ
BUCKET="${PROJECT_ID}-linebot-${ENV_NAME}"     # Cloud Storage のバケット（2つのボットで共有）
SA_NAME="linebot-${ENV_NAME}"                  # Cloud Run が使うサービスアカウント（共有）
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SECRET_CHANNEL="line-channel-secret-${BOT}-${ENV_NAME}"        # LINEの鍵はボットごと
SECRET_TOKEN="line-channel-access-token-${BOT}-${ENV_NAME}"
