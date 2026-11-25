"""Supabase Storage への写真・ファイルの保存（非公開バケット line-attachments）。

SUPABASE_URL と SUPABASE_SERVICE_KEY（secret key）を使う。サーバーの中だけで使うこと。
"""
import os

import httpx

BUCKET = "line-attachments"


def _base() -> tuple[str, dict]:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return url, {"apikey": key, "Authorization": f"Bearer {key}"}


def upload(path: str, data: bytes, content_type: str) -> str:
    """path（例: groups/<グループID>/2026-11-25/<ID>.jpg）に保存して path を返す。同じ path は上書き。"""
    url, headers = _base()
    r = httpx.post(f"{url}/storage/v1/object/{BUCKET}/{path}", content=data, timeout=60,
                   headers={**headers, "Content-Type": content_type, "x-upsert": "true"})
    r.raise_for_status()
    return path


def signed_url(path: str, expires_in: int = 3600) -> str:
    """画面で写真を見せるための期限付きURL（既定1時間）。"""
    url, headers = _base()
    r = httpx.post(f"{url}/storage/v1/object/sign/{BUCKET}/{path}", json={"expiresIn": expires_in},
                   headers=headers, timeout=15)
    r.raise_for_status()
    return f"{url}/storage/v1{r.json()['signedURL']}"
