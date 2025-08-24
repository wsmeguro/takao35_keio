# -*- coding: utf-8 -*-
"""
keio_base.py
- /api/keio/timetable/4254/1/1 で取得した JSON の
  timetables[*].operations[*].minutes[*] を直接走査。
- minutes[*] の "id" が operation_id、"time" は ISO 時刻、"type" は種別。
- 候補（特急/Mt.TAKAO/快速特急）を stops API で確認し、最終が「高尾山口」だけ残す。
- CSVに保存。
"""

import csv
import json
import os
import time, random
from datetime import datetime
from typing import Dict, Any, List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import jpholiday

# ===== 設定 =====
BASE = "https://transfer-train.navitime.biz"
LANG = "ja"
# 既定日付（--date で上書き可能）
TARGET_DT = datetime(2025, 8, 17, 9, 0)

# 代表的なルート定義（CLI で --routes で選択）
ROUTES = {
    # 1) 新宿 → 下り（直行：最終が 高尾山口）
    "shinjuku_to_takao_direct": {
        "station": "4254", "line": "1", "direction": "1",
        "type_keywords": ("特急", "Mt.TAKAO", "快速特急"),
        "dest_final": "高尾山口",
        "outfile": "shinjuku_to_takao_direct.csv",
    },
    # 1') 新宿 → 下り（京王八王子行き特急）
    "shinjuku_to_keiohachioji": {
        "station": "4254", "line": "1", "direction": "1",
        "type_keywords": ("特急",),  # ライナーは除外
        "dest_final": "京王八王子",
        "outfile": "shinjuku_to_keiohachioji.csv",
    },
    # 2) 北野 → 高尾山口
    "kitano_to_takao": {
        "station": "8408", "line": "4", "direction": "1",
        "type_keywords": (),
        "dest_final": "高尾山口",
        "outfile": "kitano_to_takao.csv",
    },
    # 3) 高尾山口 →（上り：新宿・北野方面）※最終駅フィルタなし
    "takao_to_up": {
        "station": "2629", "line": "4", "direction": "0",
        "type_keywords": (),
        "dest_final": None,
        "outfile": "takao_to_up.csv",
    },
    # 4) 北野 → 新宿（上り）
    "kitano_to_shinjuku": {
        "station": "8408", "line": "1", "direction": "0",
        "type_keywords": ("特急", "京王ライナー", "快速特急"),
        "dest_final": "新宿",
        "outfile": "kitano_to_shinjuku.csv",
    },
}

def is_holiday(dt_str: str) -> bool:
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.weekday() >= 5 or jpholiday.is_holiday(dt.date())
    except Exception:
        return False

def referer_for(station: str, line: str, direction: str, day_type: str = "weekday") -> str:
    # target は UI ページの切替用だが、Cookie/キャッシュ分離のため Referer に反映
    return f"{BASE}/keio/directions/timetable?station={station}&line={line}&target={day_type}&direction={direction}"

sess = requests.Session()
sess.headers.update({
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ja",
    "Origin": BASE,
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
})
# No initial get to REFERER URL here

# --- robust retry & pool settings ---
retry_cfg = Retry(
    total=5,
    read=5,
    connect=3,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
adapter = HTTPAdapter(max_retries=retry_cfg, pool_connections=10, pool_maxsize=10)
sess.mount("https://", adapter)
sess.mount("http://", adapter)

def get_json(url: str, params: dict, *, timeout=(10, 45)) -> Dict[str, Any]:
    """
    GET JSON with retries/backoff via session adapter.
    timeout: (connect_timeout, read_timeout)
    """
    try:
        r = sess.get(url, params=params, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ReadTimeout as e:
        # bubble up with clearer message
        raise requests.exceptions.ReadTimeout(f"Read timeout: {url} params={params}") from e
    except requests.exceptions.RequestException as e:
        # include brief context
        raise

def fetch_timetable(dt: datetime, *, station: str, line: str, direction: str, day_type: str = "weekday") -> Dict[str, Any]:
    url = f"{BASE}/api/keio/timetable/{station}/{line}/{direction}"
    params = {"datetime": dt.strftime("%Y-%m-%dT%H:%M:00+09:00"), "lang": LANG}
    # 動的 Referer（Cookie 兼 相手側の緩い検査対策）
    sess.headers["Referer"] = referer_for(station, line, direction, day_type)
    r = sess.get(url, params=params, timeout=(10, 45), allow_redirects=True)
    print("[timetable] HTTP", r.status_code, r.headers.get("Content-Type"))
    r.raise_for_status()
    return r.json()

def fetch_stops(operation_id: str, dt: datetime, *, station: str, line: str, direction: str, day_type: str = "weekday") -> List[Dict[str, Any]]:
    url = f"{BASE}/api/keio/stops/{station}/{line}"
    params = {
        "operation_id": operation_id,
        "datetime": dt.strftime("%Y-%m-%dT%H:%M:00+09:00"),
        "lang": LANG,
        "direction": direction,
    }
    # polite small delay to avoid hammering the API
    time.sleep(1.0 + random.random() * 0.5)
    sess.headers["Referer"] = referer_for(station, line, direction, day_type)
    data = get_json(url, params, timeout=(10, 45))
    out: List[Dict[str, Any]] = []
    for s in data.get("stops", []):
        if isinstance(s, dict) and s:
            out.append(s)
    return out

def parse_iso_hhmm(dt_str: str) -> Optional[tuple]:
    # 例: "2025-08-18T20:41:00+09:00" → (20, 41)
    try:
        t = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return t.hour, t.minute
    except Exception:
        try:
            hhmm = dt_str.split("T")[1].split("+")[0]
            hh, mm = hhmm.split(":")[:2]
            return int(hh), int(mm)
        except Exception:
            return None

def iso_to_datetime(dt_str: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None

def is_target_type(tt: Optional[str], type_keywords: Optional[tuple]) -> bool:
    if not type_keywords:  # ← 追加
        return True
    if not tt: return False
    return any(k in tt for k in type_keywords)

def extract_candidates(payload: dict, *, type_keywords: tuple) -> List[Dict[str, Any]]:
    """
    timetables[*].operations[*].minutes[*] から候補を抽出。
    minutes[*] の形（例）:
      {
        "time":"2025-08-18T20:41:00+09:00",
        "id":"80020259",
        "train_no":"0021A",
        "type":"特急",
        "destinations":[{"name":"京王八王子", ...}],
        "platform":"３",
        ...
      }
    """
    out: List[Dict[str, Any]] = []
    tbs = payload.get("timetables")
    if not isinstance(tbs, list): return out

    for tbl in tbs:
        ops = tbl.get("operations")
        if not isinstance(ops, list): continue
        for op in ops:
            if not isinstance(op, dict): continue
            minutes = op.get("minutes")
            if not isinstance(minutes, list): continue
            hour_hint = op.get("hour")
            for m in minutes:
                if not isinstance(m, dict): continue
                op_id = m.get("id")
                ttype = m.get("type")  # ← ここに「特急」等が入っている
                time_iso = m.get("time")
                dests = [d.get("name") for d in (m.get("destinations") or []) if isinstance(d, dict)]
                plat = m.get("platform")
                if not op_id or not time_iso:
                    continue
                if not is_target_type(ttype, type_keywords):
                    continue  # 種別でいったん絞る

                hhmm = parse_iso_hhmm(time_iso)
                if hhmm:
                    hour, minute = hhmm
                else:
                    # hour_hint がある時は minutes 側の分だけで復元
                    hour = hour_hint
                    minute = None
                if hour is None or minute is None:
                    # 出発時刻が取れないと逆算で使いにくいのでスキップ
                    continue

                out.append({
                    "hour": hour,
                    "minute": minute,
                    "departure_dt": f"{hour:02d}:{minute:02d}",
                    "operation_id": str(op_id),
                    "train_type": ttype or "",
                    "destination": " / ".join([d for d in dests if d]) if dests else "",
                    "platform": str(plat or ""),
                    "time_iso": time_iso,  # 後で stops の dt に使う
                })
    # ユニーク化（同時刻同op_idの重複を排除）
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for r in sorted(out, key=lambda x: (x["hour"], x["minute"], x["operation_id"])):
        key = (r["hour"], r["minute"], r["operation_id"])
        if key in seen: continue
        seen.add(key)
        uniq.append(r)
    return uniq

def save_csv(rows: List[Dict[str, Any]], filename: str):
    if not rows:
        print("保存するデータがありません。"); return
    here = os.path.dirname(os.path.abspath(__file__))
    outdir = os.path.join(here, "..", "py_data", "keio")
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, filename)
    # ← 列を追加
    fields = [
        "hour","minute","operation_id","train_type","destination","platform",
        "departure_dt","time_iso","stop_stations"
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            rec = dict(r)
            rec["stop_stations"] = json.dumps(rec.get("stop_stations", []), ensure_ascii=False)
            w.writerow(rec)
    print("CSV saved ->", path)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Keio timetable collector (multi-route)")
    parser.add_argument("--routes", type=str, default="shinjuku_to_takao_direct,shinjuku_to_keiohachioji,kitano_to_takao,takao_to_up,kitano_to_shinjuku",
                        help="comma-separated route keys. Available: " + ",".join(ROUTES.keys()))
    parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DDTHH:MM (local, +09:00 assumed)")
    parser.add_argument("--targets", type=str, default="weekday,holiday",
                        help="comma-separated day types: weekday,holiday")
    args = parser.parse_args()
    target_stations = ["高尾", "高尾山口", "京王八王子", "北野", "新宿"]

    # 日付``
    target_dt = TARGET_DT
    if args.date:
        try:
            # 秒省略可
            if len(args.date) == 16:
                args_date = args.date + ":00"
            else:
                args_date = args.date
            target_dt = datetime.fromisoformat(args_date)
        except Exception:
            print(f"[warn] invalid --date: {args.date}; using default {TARGET_DT.isoformat()}")
            target_dt = TARGET_DT

    day_types = [t.strip() for t in args.targets.split(",") if t.strip()]

    selected = [k.strip() for k in args.routes.split(",") if k.strip()]
    for key in selected:
        if key not in ROUTES:
            print(f"[skip] unknown route: {key}")
            continue
        conf = ROUTES[key]
        station = conf["station"]; line = conf["line"]; direction = conf["direction"]
        type_keywords = tuple(conf["type_keywords"])
        dest_final = conf.get("dest_final")
        outfile = conf["outfile"]

        for day_type in day_types:
            print(f"\n=== Route: {key} ({station}/{line}/{direction}) [{day_type}] @ {target_dt.isoformat()} ===")
            data = fetch_timetable(target_dt, station=station, line=line, direction=direction, day_type=day_type)

            cands = extract_candidates(data, type_keywords=type_keywords)
            print("minutesからの候補本数:", len(cands))
            if not cands:
                print("0本でした。種別や時間帯を見直してください。")
                continue

            rows: List[Dict[str, Any]] = []
            for idx, r in enumerate(cands, 1):
                dt_for_op = iso_to_datetime(r["time_iso"]) or datetime(
                    target_dt.year, target_dt.month, target_dt.day, r["hour"], r["minute"]
                )
                try:
                    stops = fetch_stops(r["operation_id"], dt_for_op, station=station, line=line, direction=direction, day_type=day_type)
                except requests.exceptions.ReadTimeout:
                    print(f"[warn] stops timeout: op_id={r['operation_id']} at {r['time_iso']}")
                    continue
                except requests.exceptions.RequestException as e:
                    print(f"[warn] stops error: op_id={r['operation_id']} {type(e).__name__}: {e}")
                    continue

                if not stops:
                    continue
                last = stops[-1] if isinstance(stops[-1], dict) else {}
                last_name = (last.get("name") or last.get("station"))
                if dest_final and last_name != dest_final:
                    continue

                r["stop_stations"] = [
                    {"station": s.get("name") or s.get("station"),
                    "time": s.get("departure_time") or s.get("arrive_time")}
                    for s in stops 
                    if isinstance(s, dict) and (s.get("name") or s.get("station")) in target_stations
                ]
                # day_typeと実際の日付の休日判定が一致する場合のみappend
                dt_temp = r.get("time_iso")
                if dt_temp:
                    actual_is_holiday = is_holiday(dt_temp)
                    if (day_type == "holiday" and actual_is_holiday) or \
                       (day_type == "weekday" and not actual_is_holiday):
                        rows.append(r)
                else:
                    # time_isoがない場合はとりあえずappend
                    rows.append(r)

                if idx % 25 == 0:
                    print(f" progress: {idx}/{len(cands)} candidates, kept {len(rows)}")

            print(f"{key} [{day_type}] 本数:", len(rows))
            OUTNAME = f"{target_dt.strftime('%Y%m%d')}_{day_type}_{outfile}"
            save_csv(rows, OUTNAME)