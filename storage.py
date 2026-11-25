"""保存先の切り替え: ローカルのフォルダ（テスト） / Cloud Storage（本番）

環境変数 STORAGE_BACKEND で選ぶ。
  local … DATA_DIR（既定 data）以下に保存する
  gcs   … GCS_BUCKET のバケットに保存する
どちらも「キー（data/ からの相対パス）→ 中身」で扱うので、呼び出す側は保存先を意識しない。
"""
import os
from pathlib import Path


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root)

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream"):
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def list(self, prefix: str) -> list[str]:
        base = self.root / prefix
        if not base.exists():
            return []
        return sorted(str(p.relative_to(self.root)) for p in base.rglob("*")
                      if p.is_file() and p.name != ".DS_Store")

    def describe(self) -> str:
        return f"local:{self.root.resolve()}"


class GCSStorage:
    def __init__(self, bucket: str):
        from google.cloud import storage  # 本番でだけ必要なので遅延 import

        self.bucket = storage.Client().bucket(bucket)
        self.name = bucket

    def exists(self, key: str) -> bool:
        return self.bucket.blob(key).exists()

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream"):
        self.bucket.blob(key).upload_from_string(data, content_type=content_type)

    def get(self, key: str) -> bytes:
        return self.bucket.blob(key).download_as_bytes()

    def list(self, prefix: str) -> list[str]:
        return sorted(b.name for b in self.bucket.list_blobs(prefix=prefix))

    def describe(self) -> str:
        return f"gs://{self.name}"


def get_storage():
    backend = os.getenv("STORAGE_BACKEND", "local")
    if backend == "gcs":
        bucket = os.environ["GCS_BUCKET"]
        return GCSStorage(bucket)
    return LocalStorage(os.getenv("DATA_DIR", "data"))
