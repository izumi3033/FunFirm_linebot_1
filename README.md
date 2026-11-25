# 記録蓄積BOT

グループLINEの投稿（テキスト・写真）を受け取り、保存して日報単位にまとめるbot。
botからは何も送信しない。構成の詳細は「記録蓄積BOT システム構成書」を参照。

## ファイル

| ファイル | 役割 |
|---|---|
| `main.py` | Webhookを受けて保存する（bot本体） |
| `storage.py` | 保存先の切り替え（local = data/ / gcs = Cloud Storage） |
| `build_reports.py` | 1メッセージずつの元データを日報単位にまとめる |
| `migrate_local_data.py` | 旧形式の data/ を新形式に移す（1回だけ） |
| `Dockerfile` | Cloud Run 用のコンテナ定義 |
| `deploy/config.sh` | GCPのプロジェクトID・リージョン・名前の設定 |
| `deploy/setup_gcp.sh` | 初回だけ: API有効化・バケット・サービスアカウント・シークレット |
| `deploy/deploy.sh` | Cloud Run へデプロイ |

## Macでテスト（従来どおり）

```bash
cd ~/Fun-farm_Line && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000                         # ターミナル1
cloudflared tunnel --protocol http2 --url http://127.0.0.1:8000 # ターミナル2
```

`.env` の `STORAGE_BACKEND=local` なら `data/groups/<グループID>/` に保存される。

## Google Cloud で動かす

```bash
brew install --cask google-cloud-sdk
gcloud auth login
# deploy/config.sh の PROJECT_ID を書き換える
bash deploy/setup_gcp.sh   # 初回だけ
bash deploy/deploy.sh      # コードを変えるたび
```

最後に表示される `https://linebot-dev-xxxx.a.run.app/callback` を LINE Developers の Webhook URL に登録して「検証」。
これ以降は Mac と cloudflared は不要。

## 保存のされ方

```
groups/<グループID>/
  raw/<日付>/<メッセージID>.json        元データ（1メッセージ1ファイル）
  attachments/<日付>/<メッセージID>.jpg  写真・ファイル
  reports/<日付>.md                     日報（人とAIが読む用）
  reports/<日付>.jsonl                  日報（プログラム用）
```

日報をまとめ直す: `python build_reports.py`（`--gap 30` で30分以内を1件に）

## ログを見る（Cloud Run）

```bash
gcloud run services logs read linebot-dev --region asia-northeast1 --limit 50
```
