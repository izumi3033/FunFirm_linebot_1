"""Supabase につながるか確かめる（値そのものは表示しない）。

使い方: python -m scripts.check_supabase            … .env.report を使う
        python -m scripts.check_supabase assistant  … .env.assistant を使う
"""
import re
import sys

import httpx
import psycopg

from common.env import load_bot_env
import os

bot = sys.argv[1] if len(sys.argv) > 1 else "report"
print(f"設定ファイル: {load_bot_env(bot)}")
url = os.getenv("DATABASE_URL", "")
surl = os.getenv("SUPABASE_URL", "").rstrip("/")
key = os.getenv("SUPABASE_SERVICE_KEY", "")
ok = True

# 1. 設定の形
print("DATABASE_URL:", "空です" if not url else "OK",
      "" if "pooler.supabase.com" in url else "（Session pooler の文字列ではないかも）",
      "（[YOUR-PASSWORD] のままです）" if "[YOUR-PASSWORD]" in url else "")
print("SUPABASE_URL:", surl or "空です")
print("SUPABASE_SERVICE_KEY:", "空です" if not key else f"{key[:10]}…（{len(key)}文字）")
if key.startswith("sb_publishable_"):
    print("  !! これは publishable key です。secret key（sb_secret_…）を入れてください"); ok = False

# 2. DB
EXPECTED = {"users", "line_groups", "daily_reports", "line_messages", "attachments", "houses",
            "house_aliases", "report_houses", "report_tasks", "task_houses", "sensors",
            "sensor_imports", "sensor_readings", "weather_obs", "question_logs", "weekly_reports"}
try:
    with psycopg.connect(url, connect_timeout=10) as conn:
        tables = {r[0] for r in conn.execute(
            "select table_name from information_schema.tables where table_schema='public'")}
        missing = EXPECTED - tables
        print(f"DB: 接続OK（テーブル {len(tables & EXPECTED)}/{len(EXPECTED)}）")
        if missing:
            print("  !! まだ無いテーブル:", ", ".join(sorted(missing)))
            print("     → SQL Editor で db/migrations/0001_init.sql を実行してください"); ok = False
except Exception as e:
    print("DB: 接続できません →", re.sub(r"postgres(ql)?://\S+", "<url>", str(e))[:300]); ok = False

# 3. Storage
try:
    r = httpx.get(f"{surl}/storage/v1/bucket",
                  headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=15)
    if r.status_code == 200:
        ids = [b["id"] for b in r.json()]
        print("Storage: 接続OK　バケット:", ids or "なし")
        if "line-attachments" not in ids:
            print("  !! line-attachments バケットがありません（0001_init.sql の最後で作られます）"); ok = False
    else:
        print(f"Storage: エラー {r.status_code} → {r.text[:200]}"); ok = False
except Exception as e:
    print("Storage: 接続できません →", str(e)[:200]); ok = False

print("\n結果:", "すべてOK" if ok else "上の !! を直してください")
