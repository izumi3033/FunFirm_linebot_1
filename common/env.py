"""ボットごとの .env を読む。

リポジトリ直下の .env.<ボット名>（.env.report / .env.assistant）を読む。
なければ .env を読む（日報ボットの従来の .env をそのまま使えるように）。
Cloud Run では .env は使わず、環境変数と Secret Manager から渡す。
"""
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def load_bot_env(bot: str) -> str:
    path = ROOT / f".env.{bot}"
    if not path.exists():
        path = ROOT / ".env"
    load_dotenv(path)
    return path.name
