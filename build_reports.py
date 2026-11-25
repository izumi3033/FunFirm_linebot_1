"""元データ（1メッセージずつ）を「日報」単位にまとめる。

LINEではテキストと写真は別々のメッセージとして届くため、次のルールでひとまとめにする:
  - 同じグループ・同じ人・同じ日の投稿で、前の投稿から GAP_MIN 分以内なら同じ日報
  - 引用返信（写真に返信して説明を書いた等）は、引用元と同じ日報に入れる（同じ日の中で）
出力（グループ・日付ごと）:
  groups/<group_id>/reports/<日付>.jsonl … 日報1件 = 1行（プログラム用）
  groups/<group_id>/reports/<日付>.md    … 人が読む / AIに読ませる用
使い方: python build_reports.py [--gap 10]   … 保存済みの全データをまとめ直す
"""
import argparse
import json
from datetime import datetime

from storage import get_storage

GAP_MIN = 10
MISSING_LABEL = {"image": "［写真あり（画像は未取得）］", "video": "［動画あり］", "file": "［ファイルあり（未取得）］"}


def group_prefix(group_id: str) -> str:
    return f"groups/{group_id}"


def load_day(storage, group_id: str, date: str) -> list[dict]:
    msgs = []
    for key in storage.list(f"{group_prefix(group_id)}/raw/{date}/"):
        if key.endswith(".json"):
            msgs.append(json.loads(storage.get(key)))
    return msgs


def _ts(m):
    return datetime.fromisoformat(f'{m["date"]}T{m["time"]}')


def build(msgs: list[dict], gap_min: int = GAP_MIN) -> list[dict]:
    msgs = sorted(msgs, key=lambda m: (_ts(m), m["id"]))
    report_of, reports, last = {}, [], {}
    for m in msgs:
        key = m.get("sender_id") or m.get("sender")
        quoted = m.get("quoted_message_id")
        rep = None
        if quoted and quoted in report_of:
            rep = report_of[quoted]
        elif key in last:
            prev_rep, prev_t = last[key]
            if (_ts(m) - prev_t).total_seconds() <= gap_min * 60:
                rep = prev_rep
        if rep is None:
            rep = {"id": m["id"], "group_id": m.get("group_id"), "date": m["date"],
                   "start": m["time"], "end": m["time"], "sender": m.get("sender"),
                   "sender_id": m.get("sender_id"), "texts": [], "attachments": [],
                   "message_ids": []}
            reports.append(rep)
        rep["end"] = max(rep["end"], m["time"])
        rep["message_ids"].append(m["id"])
        if m.get("text"):
            rep["texts"].append(m["text"])
        if m.get("attachment"):
            rep["attachments"].append(m["attachment"])
        elif m.get("type") in MISSING_LABEL:  # .txt取り込みなどで中身がないもの
            rep["texts"].append(MISSING_LABEL[m["type"]])
        report_of[m["id"]] = rep
        last[key] = (rep, _ts(m))
    return reports


def to_markdown(date: str, reports: list[dict]) -> str:
    lines = [f"# 日報 {date}", ""]
    for r in reports:
        lines += [f'## {r["start"][:5]} {r["sender"]}', ""]
        lines += r["texts"] or ["（本文なし）"]
        for a in r["attachments"]:
            # reports/ から見た相対パス。Markdownビューアで写真がそのまま表示される
            rel = "../" + a.split("/", 2)[2] if a.startswith("groups/") else a
            lines += ["", f"![添付]({rel})"]
        lines.append("")
    return "\n".join(lines)


def rebuild_day(storage, group_id: str, date: str, gap_min: int = GAP_MIN) -> int:
    reports = build(load_day(storage, group_id, date), gap_min)
    base = f"{group_prefix(group_id)}/reports/{date}"
    jsonl = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in reports)
    storage.put(f"{base}.jsonl", jsonl.encode(), "application/x-ndjson; charset=utf-8")
    storage.put(f"{base}.md", to_markdown(date, reports).encode(), "text/markdown; charset=utf-8")
    return len(reports)


def rebuild_all(storage, gap_min: int = GAP_MIN):
    targets = set()
    for key in storage.list("groups/"):
        parts = key.split("/")  # groups/<gid>/raw/<date>/<id>.json
        if len(parts) == 5 and parts[2] == "raw":
            targets.add((parts[1], parts[3]))
    total = 0
    for gid, date in sorted(targets):
        total += rebuild_day(storage, gid, date, gap_min)
    return total, len(targets)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", type=int, default=GAP_MIN, help="同じ日報とみなす間隔（分）")
    args = ap.parse_args()
    st = get_storage()
    n, days = rebuild_all(st, args.gap)
    print(f"{st.describe()}: {days}日分・{n}件の日報にまとめました")
