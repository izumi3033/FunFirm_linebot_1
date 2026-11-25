# FunFirm LINEボット

白石農園のデータ一元化システムのLINEボット。役割の違う2つのボットを、1つのリポジトリで管理する。

| ボット | LINE（プロバイダー／アカウント） | 役割 |
|---|---|---|
| 日報ボット `report_bot/` | FunFirm／linebot@funfirm.jp | 農園の日報グループに入り、投稿（文字・写真・ファイル）を保存して日報単位にまとめる。ボットからは何も送らない |
| 管理ボット `assistant_bot/` | FunFirm_host／linebot2@funfirm.jp | 管理者グループと1対1でやりとりする。週次レポート・質問への回答・CSVの受け取り（これから実装） |

- データの保存先は **Supabase**（DB＋写真のStorage）。2つのボットで同じ場所を使う
- プロバイダーが別なので、同じ人でもボットごとにLINEのユーザーIDが違う
- LIFF用のLINEログインチャネルは、管理ボットと同じプロバイダー（FunFirm_host 側）に作る
- 設計の詳細：技術要件書・構築報告書（チームの共有ドキュメント）、DB設計は [`db/README.md`](db/README.md)

## フォルダ

| 場所 | 役割 |
|---|---|
| `report_bot/main.py` | 日報ボット本体 |
| `assistant_bot/main.py` | 管理ボット本体（今は土台：「ID」と送るとユーザーIDを返す） |
| `common/report_store.py` | LINEのメッセージを Supabase に保存し、日報にまとめる |
| `common/db.py` | Supabase（Postgres）への接続 |
| `common/supabase_storage.py` | Supabase Storage への写真・ファイルの保存 |
| `common/env.py` | ボットごとの `.env.<ボット名>` を読む |
| `common/storage.py`・`common/build_reports.py` | 旧方式（Macの `data/` / Cloud Storage）の保存と日報まとめ |
| `db/` | Supabase のテーブル定義（`migrations/`）と設計メモ |
| `scripts/check_supabase.py` | Supabase につながるか確認する（値は表示しない） |
| `scripts/import_line_export.py` | LINEのトーク履歴（.txt）を取り込む |
| `scripts/migrate_local_data.py` | 旧形式の `data/` を新形式に移す（1回だけ） |
| `Dockerfile`・`deploy/` | Cloud Run 用（`BOT=report` / `BOT=assistant`） |

## 最初の準備（1人1回）

```bash
git clone https://github.com/izumi3033/FunFirm_linebot_1.git Fun-farm_Line
cd Fun-farm_Line
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
brew install cloudflared        # 手元で試すときのトンネル
```

### 鍵のファイルを作る

リポジトリ直下に、ボットごとのファイルを作る（**GitHubには上がらない設定**。値はチーム内で安全な方法で受け渡す）。

- `.env.report` … 日報ボット（FunFirm）
- `.env.assistant` … 管理ボット（FunFirm_host）

中身はどちらも同じ形で、LINEの値だけがボットごとに違う。

```dotenv
# LINE（LINE Developers → チャネル基本設定 → チャネルシークレット / Messaging API設定 → アクセストークン（長期））
LINE_CHANNEL_SECRET=
LINE_CHANNEL_ACCESS_TOKEN=

# 保存先: supabase（本番と同じ）/ local（Macの data/）/ gcs（旧方式）
STORAGE_BACKEND=supabase
DATA_DIR=data

# Supabase（Connect → Direct → Session pooler / Project Settings → Data API / API Keys の secret key）
DATABASE_URL=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=

# 管理ボットだけ: 使える管理者のユーザーID（カンマ区切り。空なら全員＝テスト用）
ALLOWED_USER_IDS=
```

入れ間違いが多いところ:
- `STORAGE_BACKEND` は **`supabase`** という文字（`SUPABASE_URL` ではない）
- `DATA_DIR` は **`data`** のまま（接続文字列を入れない）
- `DATABASE_URL` は **Session pooler** の文字列で、`[YOUR-PASSWORD]` を角かっこごとパスワードに置き換える
- `SUPABASE_SERVICE_KEY` は **secret key（`sb_secret_…`）**。publishable key（`sb_publishable_…`）ではない

確認:

```bash
python -m scripts.check_supabase              # .env.report を確認
python -m scripts.check_supabase assistant    # .env.assistant を確認
```

最後に「結果: すべてOK」と出ればよい。

## 手元（Mac）で動かす

**ボット1つにつき、ターミナルが2つ必要**（uvicorn と cloudflared を同時に動かし続ける）。どちらかを `Ctrl+C` で止めると、LINEから届かなくなる。

日報ボットの場合:

```bash
# ターミナル1：ボット本体
cd ~/Fun-farm_Line && source .venv/bin/activate
uvicorn report_bot.main:app --reload --port 8000

# ターミナル2：トンネル（ターミナル1は止めない）
cloudflared tunnel --protocol http2 --url http://127.0.0.1:8000
```

1. ターミナル1に `[start] report_bot env=.env.report storage=https://…supabase.co` と出ることを確認（`storage=local:…` なら `.env.report` の `STORAGE_BACKEND` を確認）
2. ターミナル2に出た `https://〜.trycloudflare.com` の末尾に `/callback` を付けて、LINE Developers → **FunFirm** → Messaging API設定 → Webhook URL に登録し「検証」
3. ターミナル1に `POST /callback ... 200 OK` が出ればつながっている
4. テスト用グループに投稿すると `[saved] supabase report=…` と出て、Supabase の `daily_reports` などに入る

管理ボットは、`assistant_bot.main:app`・ポート `8001`・登録先は **FunFirm_host** に読み替える。

管理ボットを使える人を決める手順:
1. 管理者が管理ボットを友だち追加し、「ID」と送る
2. 返ってきたIDを `.env.assistant` の `ALLOWED_USER_IDS` にカンマ区切りで入れる

### うまくいかないとき

| 症状 | 原因 | 対処 |
|---|---|---|
| `zsh: command not found: uvicorn` | 仮想環境が有効でない | `source .venv/bin/activate` |
| 投稿してもターミナル1に何も出ない | ボットが止まっている／Webhook URLが古い | ターミナル1でuvicornが動いているか確認。cloudflaredを起動し直したらURLを登録し直す。「Webhookの利用」がオンか確認 |
| `POST /callback` は出るが `[saved]` が出ない | 1対1のトークに投稿している | 日報ボットはグループの投稿だけ保存する。ボットを招待したグループで投稿する |
| 「検証」で 400 Bad Request | 別のボットのURLを登録している | 日報ボット（8000）のURLは FunFirm、管理ボット（8001）のURLは FunFirm_host に |
| cloudflared が `429` | トンネルを短時間に作りすぎ | 数分待ってからやり直す |
| 起動時に `storage=local:…` と出る | `STORAGE_BACKEND` が `supabase` になっていない | `.env.report` を直して uvicorn を起動し直す（`--reload` でも `.env` の変更は読み直さない） |

## チームでのルール

- **Webhook URLは1つのボットに1つだけ。** 手元で試すためにURLを書き換えると、その間ほかの人のMacにも本番にも届かなくなる。書き換える前にチームに一声かけ、終わったら元に戻す
- **Supabase のDBは全員で共有している。** テストの投稿も本番と同じDBに入るので、テストはテスト用グループで行う
- `git pull` のあとは `pip install -r requirements.txt` も実行する（ライブラリが増えていることがある）
- テーブルを変えるときは `db/migrations/0002_xxx.sql` のように番号を増やして追加する（既存のファイルは書き換えない）

## 秘密情報の扱い

- `.env.report`・`.env.assistant`・`data/`・`imports/` は GitHub に上げない（`.gitignore` 設定済み）。`git add .` しても入らないが、`git status` で念のため確認する
- LINEの鍵、DBのパスワード、Supabase の secret key、Claude API のキーは **LINEやチャットに貼らない**
- ターミナルのログを共有するときは、`postgresql://` やキーが写っていないか確認してから貼る
- 漏れたかもしれないときは、すぐに再発行する（Supabase：Reset database password / API Keys、LINE：アクセストークン再発行）
- `data/`・`imports/` にはパートさんの実名入りの日報が入っている。外に出さない

## Google Cloud で動かす（準備中）

```bash
brew install --cask google-cloud-sdk
gcloud auth login
# deploy/config.sh の PROJECT_ID を書き換える

BOT=report    bash deploy/setup_gcp.sh   # 初回だけ
BOT=assistant bash deploy/setup_gcp.sh
BOT=report    bash deploy/deploy.sh      # コードを変えるたび
BOT=assistant bash deploy/deploy.sh
```

> ⚠ 今の `deploy/` は旧方式（Cloud Storage に保存、`STORAGE_BACKEND=gcs`）のまま。Supabase 用の値（`DATABASE_URL` など）を Secret Manager から渡すように直してから使う。

最後に表示される `https://<ボット>-bot-dev-xxxx.a.run.app/callback` を、それぞれの Webhook URL に登録して「検証」。

ログを見る:

```bash
gcloud run services logs read report-bot-dev --region asia-northeast1 --limit 50
gcloud run services logs read assistant-bot-dev --region asia-northeast1 --limit 50
```

## 旧方式（Macの data/ に保存）について

`STORAGE_BACKEND=local` のときは `data/groups/<グループID>/` に `raw/`（元データ）・`attachments/`（写真）・`reports/`（日報の .md / .jsonl）を作る。
まとめ直し: `python -m common.build_reports`、トーク履歴の取り込み: `python -m scripts.import_line_export imports/トーク履歴.txt --group <グループID> --write`（Supabase への取り込みは今後対応）。
