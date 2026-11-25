"""旧形式の data/（raw/日付/ID.json, attachments/日付/）を新形式に移す。

新形式: groups/<group_id>/raw/<日付>/<ID>.json, groups/<group_id>/attachments/<日付>/<ID>.jpg
移し先は STORAGE_BACKEND で決まる（local なら data/groups/ 、gcs ならバケット）。
旧ファイルは消さない（確認後に手で消す）。
使い方: python -m scripts.migrate_local_data [--src data]
"""
import argparse
import json
import mimetypes
from pathlib import Path

from common import build_reports
from common.storage import get_storage

ap = argparse.ArgumentParser()
ap.add_argument("--src", default="data", help="旧形式の data フォルダ")
args = ap.parse_args()
src = Path(args.src)
st = get_storage()
moved, days = 0, set()

for raw in sorted((src / "raw").glob("*/*.json")):
    rec = json.loads(raw.read_text(encoding="utf-8"))
    gid, date = rec["group_id"], rec["date"]
    prefix = build_reports.group_prefix(gid)
    old_att = rec.get("attachment")
    if old_att:
        p = Path(old_att)
        p = p if p.exists() else src / Path(*p.parts[1:])  # "data/attachments/..." → src/attachments/...
        new_att = f"{prefix}/attachments/{date}/{p.name}"
        st.put(new_att, p.read_bytes(), mimetypes.guess_type(p.name)[0] or "application/octet-stream")
        rec["attachment"] = new_att
    rec.setdefault("quoted_message_id", None)
    st.put(f"{prefix}/raw/{date}/{rec['id']}.json",
           json.dumps(rec, ensure_ascii=False, indent=2).encode(), "application/json; charset=utf-8")
    moved += 1
    days.add((gid, date))

for gid, date in sorted(days):
    build_reports.rebuild_day(st, gid, date)
print(f"{st.describe()}: {moved}件を移し、{len(days)}日分の日報を作り直しました")
