#!/usr/bin/env bash
set -euo pipefail

export TZ=Asia/Tokyo

# パスはあなたの環境に合わせて
BASE_DIR="/home/masuday/projects/takao35"
PY="/home/masuday/projects/pyenv/py309/bin/python"   # pyenvの絶対パスを使用
LOG_DIR="$BASE_DIR/logs"
OUT_DIR="$BASE_DIR/py_data/keio"
mkdir -p "$LOG_DIR" "$OUT_DIR"

# その日の 09:00 をターゲット（％はcronの特殊文字なのでここでは使わない）
DATE_STR="$(/usr/bin/date +%F)T09:00"
ROUTES="shinjuku_to_takao_direct,shinjuku_to_keiohachioji,kitano_to_takao,takao_to_up,kitano_to_shinjuku"
TARGETS="weekday,holiday"

cd "$BASE_DIR/py_code"

# 取得
LOG_FILE="$LOG_DIR/keio_$(/usr/bin/date +%F).log"
echo "=== $(/usr/bin/date '+%F %T') start ===" | tee -a "$LOG_FILE"
"$PY" keio_base.py --date "$DATE_STR" --routes "$ROUTES" --targets "$TARGETS" 2>&1 | tee -a "$LOG_FILE"

# 加工（CSV → まとめJSON）
"$PY" postprocess_to_json.py --date "$(/usr/bin/date +%F)" 2>&1 | tee -a "$LOG_FILE"

# 時刻表JSON
"$PY" make_timetable.py 2>&1 | tee -a "$LOG_FILE"

# 時刻表のhtml化
"$PY" render_timetable_html.py 2>&1 | tee -a "$LOG_FILE"

# （任意）CoreServerにアップ
"$BASE_DIR/upload_coreserver.sh" 2>&1 | tee -a "$LOG_FILE"

echo "=== $(/usr/bin/date '+%F %T') done ===" | tee -a "$LOG_FILE"