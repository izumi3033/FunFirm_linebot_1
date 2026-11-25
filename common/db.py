"""Supabase（Postgres）への接続。

DATABASE_URL は Supabase の「Session pooler」の接続文字列。
プーラー経由なので、prepared statement は使わない（prepare_threshold=None）。
"""
import os

import psycopg


def connect() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, prepare_threshold=None)
