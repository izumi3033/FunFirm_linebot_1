"""LINEの「トーク履歴を送信」で書き出した .txt を、botと同じ形式の元データとして取り込む。

- 1メッセージ = groups/<グループID>/raw/<日付>/<ID>.json（source は "line_export"）
- ID は「日付・時刻・名前・本文」から作るので、同じ .txt を何度取り込んでも重複しない
- 写真・スタンプは本文が "[写真]" などになっているだけで、中身は入っていない
- 取り込んだ日の日報（reports/）も作り直す

使い方:
  python import_line_export.py imports/トーク履歴.txt --group <グループID>            # 確認だけ（保存しない）
  python import_line_export.py imports/トーク履歴.txt --group <グループID> --write    # 保存する
  --until 2026-10-13 を付けると、その日より前だけを取り込む（botが受け取り始めた日を指定）
"""
import argparse
import hashlib
import json
import re
from collections import Counter

import build_reports
from storage import get_storage

# 日付の行: 2026/04/01(水) / 2026/4/1(水) / 2026.04.01 水曜日
DATE_RE = re.compile(r"^(\d{4})[/.](\d{1,2})[/.](\d{1,2})(?:\s*\(.\)|\s+.曜日)?\s*$")
# メッセージの行: 08:12<TAB>佐藤<TAB>本文（午前/午後表記も一応対応）
MSG_RE = re.compile(r"^(午前|午後)?(\d{1,2}):(\d{2})\t([^\t]*)\t?(.*)$")
SYSTEM_WORDS = ("が参加しました", "が退出しました", "を招待しました", "メッセージの送信を取り消しました",
                "がグループに参加しました", "をグループから削除しました", "がアルバム", "がノートに投稿しました")
TYPES = {"[写真]": "image", "[Photo]": "image", "[動画]": "video", "[Video]": "video",
         "[スタンプ]": "sticker", "[Sticker]": "sticker", "[ファイル]": "file", "[File]": "file",
         "[ボイスメッセージ]": "audio", "[位置情報]": "location"}


def parse(raw: str):
    msgs, date, cur = [], None, None
    for line in raw.replace("\r\n", "\n").split("\n"):
        line = line.lstrip("﻿")
        if m := DATE_RE.match(line):
            date = f"{m[1]}-{int(m[2]):02}-{int(m[3]):02}"
            cur = None
            continue
        if date and (m := MSG_RE.match(line)):
            h = int(m[2]) % 12 + (12 if m[1] == "午後" else 0) if m[1] else int(m[2])
            cur = {"date": date, "time": f"{h:02}:{m[3]}:00", "sender": m[4], "text": m[5]}
            msgs.append(cur)
            continue
        if cur is not None:  # 複数行メッセージの続き
            cur["text"] += "\n" + line
    out = []
    for c in msgs:
        t = c["text"].rstrip("\n")
        if len(t) >= 2 and t.startswith('"') and t.endswith('"'):
            t = t[1:-1].replace('""', '"')
        if not c["sender"] or any(w in t for w in SYSTEM_WORDS):
            continue  # システムメッセージ
        out.append({**c, "text": t, "type": TYPES.get(t.strip(), "text")})
    return out


def to_record(m: dict, group_id: str, seq: int) -> dict:
    key = f'{group_id}|{m["date"]}|{m["time"]}|{m["sender"]}|{m["text"]}|{seq}'
    return {
        "id": "x" + hashlib.sha1(key.encode()).hexdigest()[:17],
        "source": "line_export",
        "group_id": group_id,
        "date": m["date"],
        "time": m["time"],
        "sender": m["sender"],
        "sender_id": None,  # .txt にはユーザーIDがない
        "type": m["type"],
        "text": m["text"] if m["type"] == "text" else None,
        "quoted_message_id": None,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("txt", help="LINEから書き出した .txt")
    ap.add_argument("--group", required=True, help="取り込み先のグループID（Cから始まる）")
    ap.add_argument("--until", help="この日付より前だけ取り込む（例: 2026-10-13）")
    ap.add_argument("--write", action="store_true", help="付けたときだけ保存する")
    args = ap.parse_args()

    raw = open(args.txt, encoding="utf-8-sig").read()
    msgs = parse(raw)
    if args.until:
        msgs = [m for m in msgs if m["date"] < args.until]
    if not msgs:
        print("メッセージが見つかりませんでした。.txt の形式を確認してください（先頭20行を見せてください）")
        raise SystemExit(1)

    seen = Counter()
    records = []
    for m in msgs:  # 同じ分・同じ人・同じ本文が続いても別IDにする
        k = (m["date"], m["time"], m["sender"], m["text"])
        records.append(to_record(m, args.group, seen[k]))
        seen[k] += 1

    days = sorted({r["date"] for r in records})
    print(f"{len(records)}件 / {days[0]} 〜 {days[-1]}（{len(days)}日分）")
    print("送信者:", ", ".join(f"{n}({c})" for n, c in Counter(r["sender"] for r in records).most_common()))
    print("種類:", dict(Counter(r["type"] for r in records)))
    for r in records[:5]:
        print(" ", r["date"], r["time"], r["sender"], (r["text"] or f'[{r["type"]}]').replace("\n", " / ")[:40])

    if not args.write:
        print("\n確認だけしました。保存するには --write を付けて実行してください")
        raise SystemExit(0)

    st = get_storage()
    prefix = build_reports.group_prefix(args.group)
    new = 0
    for r in records:
        key = f'{prefix}/raw/{r["date"]}/{r["id"]}.json'
        if st.exists(key):
            continue
        st.put(key, json.dumps(r, ensure_ascii=False, indent=2).encode(), "application/json; charset=utf-8")
        new += 1
    for d in days:
        build_reports.rebuild_day(st, args.group, d)
    print(f"\n{st.describe()}: 新しく{new}件を保存し、{len(days)}日分の日報を作り直しました")
