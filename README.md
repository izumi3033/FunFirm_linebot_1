# FunFirm LINEボット

白石農園のデータ一元化システムのLINEボット。役割の違う2つのボットを、1つのリポジトリで管理する。

| ボット | LINE（プロバイダー／アカウント） | 役割 |
|---|---|---|
| 日報ボット `report_bot/` | FunFirm／linebot@funfirm.jp | 農園のグループに入り、投稿（テキスト・写真・ファイル）を保存して日報単位にまとめる。ボットからは何も送らない |
| 管理ボット `assistant_bot/` | FunFirm_host／linebot2@funfirm.jp | 管理者3人と1対1でやりとりする。週次レポート・質問への回答・CSVの受け取り（これから実装） |

2つのボットは同じ保存先（ローカルの `data/` または Cloud Storage のバケット）を使う。
プロバイダーが別なので、同じ人でもボットごとにユーザーIDが違う点に注意。
LIFF用のLINEログインチャネルは、管理ボットと同じプロバイダー（FunFirm_host 側）に作る。

## フォルダ

| 場所 | 役割 |
|---|---|
| `common/storage.py` | 保存先の切り替え（local = data/ / gcs = Cloud Storage） |
| `common/build_reports.py` | 1メッセージずつの元データを日報単位にまとめる |
| `common/env.py` | ボットごとの `.env.<ボット名>` を読む |
| `report_bot/main.py` | 日報ボット本体 |
| `assistant_bot/main.py` | 管理ボット本体（今は土台：「ID」と送るとユーザーIDを返す） |
| `scripts/import_line_export.py` | LINEのトーク履歴（.txt）を取り込む |
| `scripts/migrate_local_data.py` | 旧形式の data/ を新形式に移す（1回だけ） |
| `Dockerfile` | Cloud Run 用。`APP_MODULE` でどちらのボットを動かすか選ぶ |
| `deploy/` | GCPの初期設定とデプロイ（`BOT=report` / `BOT=assistant`） |

## 保存先（STORAGE_BACKEND）

| 値 | 保存先 |
|---|---|
| `supabase` | Supabase の DB（`line_messages`・`daily_reports`・`attachments`）と Storage（写真）。本番はこれ |
| `local` | このフォルダの `data/`（従来どおり） |
| `gcs` | Cloud Storage（従来どおり） |

`supabase` のときは `.env.report` に `DATABASE_URL`・`SUPABASE_URL`・`SUPABASE_SERVICE_KEY` が必要。
接続確認: `python -m scripts.check_supabase`。テーブル定義は `db/` を参照。

## 鍵の置き方

`.env.example` をコピーして、ボットごとに作る（GitHubには上がらない）。

- `.env.report` … 日報ボットの鍵（なければ従来の `.env` を読む）
- `.env.assistant` … 管理ボットの鍵と `ALLOWED_USER_IDS`

## Macでテスト

コマンドはすべてリポジトリ直下で実行する。

```bash
cd ~/Fun-farm_Line && source .venv/bin/activate
pip install -r requirements.txt

# 日報ボット
uvicorn report_bot.main:app --reload --port 8000
cloudflared tunnel --protocol http2 --url http://127.0.0.1:8000

# 管理ボット（別のターミナルで、ポートを変える）
uvicorn assistant_bot.main:app --reload --port 8001
cloudflared tunnel --protocol http2 --url http://127.0.0.1:8001
```

cloudflared が表示したURL＋`/callback` を、それぞれのチャネルの Webhook URL に登録して「検証」。

管理ボットを使える人を決める手順:
1. 管理者3人が管理ボットを友だち追加し、「ID」と送る
2. 返ってきたIDを `.env.assistant` の `ALLOWED_USER_IDS` にカンマ区切りで入れる（空のままだと全員が使える）

## Google Cloud で動かす

```bash
brew install --cask google-cloud-sdk
gcloud auth login
# deploy/config.sh の PROJECT_ID を書き換える

BOT=report    bash deploy/setup_gcp.sh   # 初回だけ
BOT=assistant bash deploy/setup_gcp.sh   # 初回だけ（バケット等は共有なので作成済みならスキップ）

BOT=report    bash deploy/deploy.sh      # コードを変えるたび
BOT=assistant bash deploy/deploy.sh
```

最後に表示される `https://<ボット>-bot-dev-xxxx.a.run.app/callback` を、それぞれの Webhook URL に登録して「検証」。

## 保存のされ方

```
groups/<グループID>/
  raw/<日付>/<メッセージID>.json        元データ（1メッセージ1ファイル）
  attachments/<日付>/<メッセージID>.jpg  写真・ファイル
  reports/<日付>.md                     日報（人とAIが読む用）
  reports/<日付>.jsonl                  日報（プログラム用）
```

日報をまとめ直す: `python -m common.build_reports`（`--gap 30` で30分以内を1件に）
トーク履歴の取り込み: `python -m scripts.import_line_export imports/トーク履歴.txt --group <グループID> --write`

## ログを見る（Cloud Run）

```bash
gcloud run services logs read report-bot-dev --region asia-northeast1 --limit 50
gcloud run services logs read assistant-bot-dev --region asia-northeast1 --limit 50
```
