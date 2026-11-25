"""LINEのメッセージを Supabase に保存し、日報（daily_reports）にまとめる。

まとめ方は build_reports.py と同じ:
  - 同じグループ・同じ人・同じ日の投稿で、その人の直前の日報から GAP 以内なら同じ日報
  - 引用返信（写真に返信して説明を書いた等）は、引用元と同じ日報（同じ日の中で）
本文は書き換えずにつなげるだけ。本文が増えたら extraction_status を pending に戻す（AIが読み直す）。
"""
from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb

JST = timezone(timedelta(hours=9))
GAP = timedelta(minutes=10)


def already_saved(conn, message_id: str) -> bool:
    return conn.execute("select 1 from line_messages where id = %s", (message_id,)).fetchone() is not None


def _user_id(conn, line_user_id, sender_name):
    if not line_user_id:
        return None
    return conn.execute(
        """insert into users (display_name, report_line_user_id) values (%s, %s)
           on conflict (report_line_user_id) do update set display_name = excluded.display_name
           returning id""", (sender_name, line_user_id)).fetchone()[0]


def _find_report(conn, group_id, user_id, sender_name, report_date, sent_at, quoted_id):
    if quoted_id:
        row = conn.execute(
            """select m.report_id from line_messages m join daily_reports r on r.id = m.report_id
               where m.id = %s and r.group_id = %s and r.report_date = %s""",
            (quoted_id, group_id, report_date)).fetchone()
        if row:
            return row[0]
    row = conn.execute(
        """select id from daily_reports
           where group_id = %s and report_date = %s
             and (case when %s::bigint is not null then user_id = %s::bigint else sender_name = %s end)
             and ended_at >= %s and started_at <= %s
           order by ended_at desc limit 1""",
        (group_id, report_date, user_id, user_id, sender_name, sent_at - GAP, sent_at + GAP)).fetchone()
    return row[0] if row else None


def save_message(conn, *, message_id: str, group_id: str, line_user_id, sender_name: str,
                 sent_at: datetime, msg_type: str, text, quoted_id=None, raw=None,
                 attachment: dict | None = None, source: str = "line_bot"):
    """1件保存して日報IDを返す。同じメッセージが2回来たら何もせず None を返す。

    attachment = {"kind": "image"|"file"|"video", "storage_path": ..., "file_name": ...,
                  "mime_type": ..., "size_bytes": ...}
    """
    report_date = sent_at.astimezone(JST).date()
    with conn.transaction():
        conn.execute("insert into line_groups (id, kind) values (%s, 'report') on conflict do nothing",
                     (group_id,))
        user_id = _user_id(conn, line_user_id, sender_name)
        inserted = conn.execute(
            """insert into line_messages
                 (id, group_id, user_id, sender_name, sent_at, type, text, quoted_message_id, source, raw)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               on conflict (id) do nothing returning id""",
            (message_id, group_id, user_id, sender_name, sent_at, msg_type, text, quoted_id, source,
             Jsonb(raw) if raw is not None else None)).fetchone()
        if not inserted:
            return None

        report_id = _find_report(conn, group_id, user_id, sender_name, report_date, sent_at, quoted_id)
        if report_id is None:
            report_id = conn.execute(
                """insert into daily_reports
                     (group_id, report_date, user_id, sender_name, started_at, ended_at, body)
                   values (%s, %s, %s, %s, %s, %s, %s) returning id""",
                (group_id, report_date, user_id, sender_name, sent_at, sent_at, text or "")).fetchone()[0]
        else:
            conn.execute(
                """update daily_reports set
                     started_at = least(started_at, %s),
                     ended_at   = greatest(ended_at, %s),
                     body = case when %s::text is null or %s::text = '' then body
                                 when body = '' then %s::text
                                 else body || E'\\n' || %s::text end,
                     extraction_status = case when %s::text is null or %s::text = '' then extraction_status
                                              else 'pending' end
                   where id = %s""",
                (sent_at, sent_at, text, text, text, text, text, text, report_id))
        conn.execute("update line_messages set report_id = %s where id = %s", (report_id, message_id))

        if attachment:
            conn.execute(
                """insert into attachments
                     (message_id, report_id, kind, storage_path, file_name, mime_type, size_bytes, sent_at)
                   values (%s, %s, %s, %s, %s, %s, %s, %s) on conflict (message_id) do nothing""",
                (message_id, report_id, attachment["kind"], attachment["storage_path"],
                 attachment.get("file_name"), attachment.get("mime_type"), attachment.get("size_bytes"),
                 sent_at))
    return report_id
