#!/usr/bin/env bash
set -euo pipefail
source ~/.secrets_coreserver

# === 認証情報（環境変数経由にするのが安全）===
: "${FTP_HOST:?set FTP_HOST}"
: "${FTP_USER:?set FTP_USER}"
: "${FTP_PASS:?set FTP_PASS}"

BASE_DIR="/home/masuday/projects/takao35"
PUB_DIR="$BASE_DIR/py_data/keio/publish"
REMOTE_DIR="/train"     # CoreServer側の配置先に合わせて変更

# ★ 最新ファイルの別名を変数で定義
LATEST_ALIAS="latest_keio_shinjuku_takao3.json"

# 保持期間（日数）
LOCAL_RETENTION_DAYS=30     # Rockey 側（ローカル）
REMOTE_RETENTION_DAYS=100   # CoreServer 側（リモート）

# カットオフ日（YYYYMMDD）
LOCAL_CUTOFF="$(/usr/bin/date -d "-${LOCAL_RETENTION_DAYS} days" +%Y%m%d)"
REMOTE_CUTOFF="$(/usr/bin/date -d "-${REMOTE_RETENTION_DAYS} days" +%Y%m%d)"
echo "Local cutoff: ${LOCAL_CUTOFF}  (keep last ${LOCAL_RETENTION_DAYS} days)"
echo "Remote cutoff: ${REMOTE_CUTOFF} (keep last ${REMOTE_RETENTION_DAYS} days)"

 # 最新JSONのみアップ（必要ならrsync的にmirrorしてもOK）
LATEST_FILE="$(ls -1t "$PUB_DIR"/takao35_timetable_*.json | head -n1)"
[ -n "$LATEST_FILE" ] || { echo "no JSON to upload"; exit 0; }

# --- 最新ファイルを latest.json としてもアップするためのローカル別名を作成 ---
TMPDIR="$(/usr/bin/mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
/usr/bin/ln -sf "$LATEST_FILE" "$TMPDIR/$LATEST_ALIAS"

# --- ローカル古いファイルの削除（30日より古い） ---
if compgen -G "${PUB_DIR}/takao35_timetable_*.json" > /dev/null; then
  for f in "${PUB_DIR}"/takao35_timetable_*.json; do
    bn="$(basename "$f")"
    d="${bn#takao35_timetable_}"; d="${d%.json}"
    if [[ "$d" =~ ^[0-9]{8}$ ]] && [[ "$d" -lt "$LOCAL_CUTOFF" ]]; then
      echo "Local delete: $bn"
      rm -f -- "$f"
    fi
  done
fi

lftp -e "
set ftp:ssl-force true
set ftp:ssl-protect-data true
set ssl:verify-certificate no
open -u ${FTP_USER},${FTP_PASS} ${FTP_HOST}
mkdir -p ${REMOTE_DIR}
cd ${REMOTE_DIR}
  # dated file（そのままのファイル名でアップ）
  put -O ${REMOTE_DIR} ${LATEST_FILE}
  # stable pointer（毎回上書きされる最新版の別名）
  lcd ${TMPDIR}
  put -O ${REMOTE_DIR} ${LATEST_ALIAS}
bye
"
echo "Uploaded: ${LATEST_FILE}"

# --- リモート古いファイルの削除（100日より古い） ---
# 1) 一覧取得
REMOTE_LIST="$(
  lftp -u "${FTP_USER}","${FTP_PASS}" "${FTP_HOST}" -e "
    set ftp:ssl-force true
    set ftp:ssl-protect-data true
    set ssl:verify-certificate no
    cd ${REMOTE_DIR}
    cls -1 takao35_timetable_*.json
    bye
  " 2>/dev/null
)"

# 2) 削除対象を抽出
TO_DELETE=()
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  bn="$(basename "$line")"
  d="${bn#takao35_timetable_}"; d="${d%.json}"
  if [[ "$d" =~ ^[0-9]{8}$ ]] && [[ "$d" -lt "$REMOTE_CUTOFF" ]]; then
    TO_DELETE+=("$bn")
  fi
done <<< "$REMOTE_LIST"

# 3) リモート削除実行
if (( ${#TO_DELETE[@]} > 0 )); then
  echo "Remote delete (${#TO_DELETE[@]} files): ${TO_DELETE[*]}"
  lftp -u "${FTP_USER}","${FTP_PASS}" "${FTP_HOST}" -e "
    set ftp:ssl-force true
    set ftp:ssl-protect-data true
    set ssl:verify-certificate no
    cd ${REMOTE_DIR}
$(for f in "${TO_DELETE[@]}"; do printf '      rm %q\n' "$f"; done)
    bye
  "
else
  echo "Remote delete: no old files."
fi