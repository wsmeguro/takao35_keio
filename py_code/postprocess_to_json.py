#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, csv, argparse
from datetime import datetime
from make_timetable import shinjuku_to_takao3, takao3_to_shinjuku
from render_timetable_html import render
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "py_data", "keio"))
PUB_DIR = os.path.join(OUT_DIR, "publish")
os.makedirs(PUB_DIR, exist_ok=True)

ROUTE_KEYS = [
    "shinjuku_to_takao_direct",
    "shinjuku_to_keiohachioji",
    "kitano_to_takao",
    "takao_to_up",
    "kitano_to_shinjuku",
]

def load_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            # JSON文字列のstop_stationsをオブジェクトへ
            try:
                row["stop_stations"] = json.loads(row.get("stop_stations") or "[]")
            except Exception:
                row["stop_stations"] = []
            # 整形（Flutterで便利なキー名に）
            rows.append({
                "hour": int(row["hour"]),
                "minute": int(row["minute"]),
                "opId": row["operation_id"],
                "trainType": row["train_type"],
                "dest": row["destination"],
                "platform": row["platform"],
                "departHHMM": row["departure_dt"],
                "timeISO": row["time_iso"],
                "stops": row["stop_stations"],   # [{station,time},...]
            })
    # 出発時刻でソート
    rows.sort(key=lambda x: (x["hour"], x["minute"], x["opId"]))
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    ymd = args.date.replace("-", "")
    doc = {
        "generatedAt": datetime.now().isoformat(),
        "serviceDate": args.date,
        "routes": {}
    }

    # weekday/holiday × route をまとめて収集
    for day_type in ("weekday", "holiday"):
        for key in ROUTE_KEYS:
            # 例: 20250817_weekday_shinjuku_to_takao_direct.csv
            csv_name = f"{ymd}_{day_type}_{key}.csv"
            path = os.path.join(OUT_DIR, csv_name)
            if not os.path.exists(path):
                continue
            rows = load_csv(path)
            doc["routes"].setdefault(key, {})[day_type] = rows

    # まとめJSONを書き出し
    out_json = os.path.join(PUB_DIR, f"takao35_timetable_{ymd}.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print("Wrote:", out_json)

if __name__ == "__main__":
    main()
    shinjuku_to_takao3()
    takao3_to_shinjuku()
    render()
