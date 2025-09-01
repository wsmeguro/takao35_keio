#!/usr/bin/env bash
set -euo pipefail
source ~/.secrets_coreserver

# === 認証情報 ===
: "${FTP_HOST:?set FTP_HOST}"
: "${FTP_USER:?set FTP_USER}"
: "${FTP_PASS:?set FTP_PASS}"

BASE_DIR="/home/masuday/projects/takao35"
PUB_DIR="$BASE_DIR/py_data/keio/publish"
REMOTE_DIR="/train"     # CoreServer 側の配置先

# === アップ対象（3点） ===
# 1) JSON: 新宿→高尾山口（直通＋北野乗換を内包した集約）
PATTERN_S2T="*_shinjuku_to_takao3.json"
LATEST_ALIAS_S2T="latest_keio_shinjuku_takao3.json"

# 2) JSON: 高尾山口→新宿
PATTERN_T2S="*_takao3_to_shinjuku.json"
LATEST_ALIAS_T2S="latest_keio_takao3_to_shinjuku.json"

# 3) HTML: 一枚物の時刻表
HTML_FILE="$PUB_DIR/timetables.html"   # 生成先に合わせて必要なら変更

# === 保持期間（日数） ===
LOCAL_RETENTION_DAYS=30
REMOTE_RETENTION_DAYS=100
LOCAL_CUTOFF="$(/usr/bin/date -d "-${LOCAL_RETENTION_DAYS} days" +%Y%m%d)"
REMOTE_CUTOFF="$(/usr/bin/date -d "-${REMOTE_RETENTION_DAYS} days" +%Y%m%d)"
echo "Local cutoff:  ${LOCAL_CUTOFF}  (keep last ${LOCAL_RETENTION_DAYS} days)"
echo "Remote cutoff: ${REMOTE_CUTOFF} (keep last ${REMOTE_RETENTION_DAYS} days)"

# === 最新ファイルの特定 ===
latest_of() {
  # 引数: グロブパターン
  local pattern="$1"
  # shellcheck disable=SC2086
  ls -1t ${PUB_DIR}/${pattern} 2>/dev/null | head -n1 || true
}

LATEST_S2T="$(latest_of "$PATTERN_S2T")"
LATEST_T2S="$(latest_of "$PATTERN_T2S")"

echo "Latest S2T: ${LATEST_S2T:-'(none)'}"
echo "Latest T2S: ${LATEST_T2S:-'(none)'}"
echo "HTML path : ${HTML_FILE}"

# === 一時ディレクトリで latest エイリアス名を作る（シンボリックリンク） ===
TMPDIR="$(/usr/bin/mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

need_upload=false
if [[ -n "${LATEST_S2T:-}" && -f "$LATEST_S2T" ]]; then
  ln -s "$LATEST_S2T" "$TMPDIR/$LATEST_ALIAS_S2T"
  need_upload=true
else
  echo "[warn] S2T JSON が見つかりません（スキップ）"
fi

if [[ -n "${LATEST_T2S:-}" && -f "$LATEST_T2S" ]]; then
  ln -s "$LATEST_T2S" "$TMPDIR/$LATEST_ALIAS_T2S"
  need_upload=true
else
  echo "[warn] T2S JSON が見つかりません（スキップ）"
fi

if [[ ! -f "$HTML_FILE" ]]; then
  echo "[warn] HTML が見つかりません（スキップ）"
else
  need_upload=true
fi

if [[ "$need_upload" != true ]]; then
  echo "アップロード対象が無いので終了します。"
  exit 0
fi

# === アップロード ===
lftp -e "
set ftp:ssl-force true
set ftp:ssl-protect-data true
set ssl:verify-certificate no
open -u ${FTP_USER},${FTP_PASS} ${FTP_HOST}
mkdir -p ${REMOTE_DIR}
cd ${REMOTE_DIR}

# --- 1) JSON dated ファイル（そのままのファイル名でアップ。存在すればアップ）
$( [[ -n "${LATEST_S2T:-}" && -f "$LATEST_S2T" ]] && printf 'put -O %q %q\n' "$REMOTE_DIR" "$LATEST_S2T" )
$( [[ -n "${LATEST_T2S:-}" && -f "$LATEST_T2S" ]] && printf 'put -O %q %q\n' "$REMOTE_DIR" "$LATEST_T2S" )

# --- 2) JSON latest エイリアス（毎回上書き）
lcd ${TMPDIR}
$( [[ -e "$TMPDIR/$LATEST_ALIAS_S2T" ]] && printf 'put -O %q %q\n' "$REMOTE_DIR" "$LATEST_ALIAS_S2T" )
$( [[ -e "$TMPDIR/$LATEST_ALIAS_T2S" ]] && printf 'put -O %q %q\n' "$REMOTE_DIR" "$LATEST_ALIAS_T2S" )

# --- 3) HTML（毎回上書き）
$( [[ -f "$HTML_FILE" ]] && printf 'put -O %q %q\n' "$REMOTE_DIR" "$HTML_FILE" )

bye
"
echo "Uploaded (finished)."

# === ローカル古い JSON の削除（保持期間超え） ===
cleanup_local_by_pattern() {
  local pattern="$1"
  # shellcheck disable=SC2086
  for f in ${PUB_DIR}/${pattern}; do
    [[ -e "$f" ]] || continue
    bn="$(basename "$f")"
    # 先頭側に yyyymmdd_ がある想定を抽出（例: 20250831_weekday_shinjuku_to_takao3.json）
    d="${bn%%_*}"
    if [[ "$d" =~ ^[0-9]{8}$ ]] && [[ "$d" -lt "$LOCAL_CUTOFF" ]]; then
      echo "Local delete: $bn"
      rm -f -- "$f"
    fi
  done
}
cleanup_local_by_pattern "$PATTERN_S2T"
cleanup_local_by_pattern "$PATTERN_T2S"

# === リモート古い JSON の削除（保持期間超え） ===
# CoreServer側で日付入りファイル名のみ削除対象（latest_*.json と HTML は残す）
remote_delete_old() {
  local list_pattern="$1"   # 例: *_shinjuku_to_takao3.json
  lftp -u "${FTP_USER}","${FTP_PASS}" "${FTP_HOST}" -e "
    set ftp:ssl-force true
    set ftp:ssl-protect-data true
    set ssl:verify-certificate no
    cd ${REMOTE_DIR}
    cls -1 ${list_pattern}
    bye
  " 2>/dev/null | while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    bn="$(basename "$line")"
    d="${bn%%_*}"
    if [[ "$d" =~ ^[0-9]{8}$ ]] && [[ "$d" -lt "$REMOTE_CUTOFF" ]]; then
      echo "Remote delete: $bn"
      lftp -u "${FTP_USER}","${FTP_PASS}" "${FTP_HOST}" -e "
        set ftp:ssl-force true
        set ftp:ssl-protect-data true
        set ssl:verify-certificate no
        cd ${REMOTE_DIR}
        rm ${bn}
        bye
      " >/dev/null 2>&1 || echo "[warn] failed to delete ${bn}"
    fi
  done
}
remote_delete_old "$PATTERN_S2T"
remote_delete_old "$PATTERN_T2S"