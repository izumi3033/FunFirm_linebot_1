"""管理ボット（FunFirm_host）: 管理者3人と1対1でやりとりする。

これから載せる機能: 週次レポートの送信・質問への回答・センサーCSVの受け取り・LIFF画面向けAPI。
今は土台だけで、次のことができる。
  - 「ID」と送ると、その人のユーザーIDを返す（管理者のIDを集めて ALLOWED_USER_IDS に登録するため）
  - ALLOWED_USER_IDS に入っていない人には「管理者専用」と返す（空なら全員に返事する＝テスト用）
グループでの投稿は日報ボットの担当なので無視する。
データは日報ボットと同じ保存先（STORAGE_BACKEND / GCS_BUCKET）を読む。
"""
import os

from fastapi import FastAPI, HTTPException, Request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient, Configuration, MessagingApi, ReplyMessageRequest, TextMessage,
)
from linebot.v3.webhooks import FollowEvent, MessageEvent, TextMessageContent

from common.env import load_bot_env
from common.storage import get_storage

ENV_FILE = load_bot_env("assistant")  # ローカルでは .env.assistant
config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
storage = get_storage()
ALLOWED_USER_IDS = {u.strip() for u in os.getenv("ALLOWED_USER_IDS", "").split(",") if u.strip()}
app = FastAPI()
print(f"[start] assistant_bot env={ENV_FILE} storage={storage.describe()} "
      f"allowed={len(ALLOWED_USER_IDS) or '全員（テスト）'}")


@app.get("/")
def health():
    return {"status": "ok", "bot": "assistant", "storage": os.getenv("STORAGE_BACKEND", "local")}


@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = (await request.body()).decode()
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="invalid signature")
    return "OK"


def reply(reply_token: str, text: str):
    with ApiClient(config) as client:
        MessagingApi(client).reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=text)])
        )


def is_allowed(user_id: str) -> bool:
    return not ALLOWED_USER_IDS or user_id in ALLOWED_USER_IDS


@handler.add(FollowEvent)
def on_follow(event: FollowEvent):
    user_id = event.source.user_id
    print(f"[follow] user_id={user_id}")  # これを控えて ALLOWED_USER_IDS に登録する
    reply(event.reply_token, "友だち追加ありがとうございます。白石農園の管理用ボットです。")


@handler.add(MessageEvent)
def on_message(event: MessageEvent):
    src = event.source
    if src.type != "user":  # グループは日報ボットの担当
        return
    msg = event.message
    text = msg.text.strip() if isinstance(msg, TextMessageContent) else ""
    print(f"[message] user_id={src.user_id} type={msg.type} text={text[:40]}")

    if text.upper() == "ID":
        reply(event.reply_token, f"あなたのユーザーIDです。\n{src.user_id}")
        return
    if not is_allowed(src.user_id):
        reply(event.reply_token, "このボットは白石農園の管理者専用です。")
        return
    reply(event.reply_token, "準備中です。週次レポートや質問への回答は、これから使えるようになります。")
