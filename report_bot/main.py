"""日報ボット（FunFirm）: グループLINEの投稿を受け取り、保存して日報単位にまとめる。

保存先は STORAGE_BACKEND で切り替える（storage.py）
  local … Mac の data/ フォルダ（テスト用）
  gcs   … Cloud Storage のバケット（Cloud Run 本番用）
botからは一切メッセージを送らない（受け取って保存するだけ）。
"""
import json
import mimetypes
import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import ApiClient, Configuration, MessagingApi, MessagingApiBlob
from linebot.v3.webhooks import (
    FileMessageContent, ImageMessageContent, JoinEvent, LeaveEvent,
    MessageEvent, TextMessageContent,
)

from common import build_reports
from common.env import load_bot_env
from common.storage import get_storage

ENV_FILE = load_bot_env("report")  # ローカルでは .env.report（なければ .env）。Cloud Run では環境変数とSecret Manager
config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
storage = get_storage()
JST = timezone(timedelta(hours=9))
app = FastAPI()
print(f"[start] report_bot env={ENV_FILE} storage={storage.describe()}")


@app.get("/")
def health():
    return {"status": "ok", "bot": "report", "storage": os.getenv("STORAGE_BACKEND", "local")}


@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = (await request.body()).decode()
    try:
        # 署名検証 + イベント処理。保存まで終えてから200を返す
        # （Cloud Runは応答後にCPUが絞られるため、処理を後回しにしない）
        handler.handle(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="invalid signature")
    return "OK"


def sender_name(api: MessagingApi, src) -> str:
    try:
        return api.get_group_member_profile(src.group_id, src.user_id).display_name
    except Exception:
        return "不明"


@handler.add(MessageEvent)
def on_message(event: MessageEvent):
    src = event.source
    if src.type != "group":  # 日報はグループだけ対象（1対1のトークは無視）
        return
    ts = datetime.fromtimestamp(event.timestamp / 1000, JST)
    date = ts.strftime("%Y-%m-%d")
    msg = event.message
    prefix = build_reports.group_prefix(src.group_id)
    raw_key = f"{prefix}/raw/{date}/{msg.id}.json"
    if storage.exists(raw_key):  # LINEの再送で同じメッセージが来たら何もしない
        print(f"[skip] 受信済み {msg.id}")
        return

    with ApiClient(config) as client:
        api = MessagingApi(client)
        record = {
            "id": msg.id,
            "source": "line_bot",
            "group_id": src.group_id,
            "date": date,
            "time": ts.strftime("%H:%M:%S"),
            "sender": sender_name(api, src),
            "sender_id": src.user_id,
            "type": msg.type,
            "text": msg.text if isinstance(msg, TextMessageContent) else None,
            # 引用返信なら引用元のID（写真に返信した説明文などを紐づける）
            "quoted_message_id": getattr(msg, "quoted_message_id", None),
            "received_at": datetime.now(JST).isoformat(timespec="seconds"),
        }
        image_set = getattr(msg, "image_set", None)  # 複数枚まとめて送った写真
        if image_set:
            record["image_set"] = {"id": image_set.id, "index": image_set.index, "total": image_set.total}

        if isinstance(msg, (ImageMessageContent, FileMessageContent)):
            content = MessagingApiBlob(client).get_message_content(msg.id)
            file_name = getattr(msg, "file_name", None)
            ext = os.path.splitext(file_name)[1] if file_name else ".jpg"
            att_key = f"{prefix}/attachments/{date}/{msg.id}{ext}"
            ctype = mimetypes.guess_type(att_key)[0] or "application/octet-stream"
            storage.put(att_key, content, ctype)
            record["attachment"] = att_key
            if file_name:
                record["file_name"] = file_name

    storage.put(raw_key, json.dumps(record, ensure_ascii=False, indent=2).encode(),
                "application/json; charset=utf-8")
    print(f'[saved] {date} {record["time"]} {record["sender"]}: {record["text"] or record["type"]}')

    try:  # その日の日報をまとめ直す
        build_reports.rebuild_day(storage, src.group_id, date)
    except Exception as e:
        print(f"[reports] まとめ直しに失敗: {e}")


@handler.add(JoinEvent)
def on_join(event: JoinEvent):
    print(f"[join] group_id={event.source.group_id}")  # これを控えて農園と紐づける


@handler.add(LeaveEvent)
def on_leave(event: LeaveEvent):
    print(f"[leave] group_id={event.source.group_id}")
