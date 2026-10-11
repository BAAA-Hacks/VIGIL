#!/usr/bin/env bash
# Demo without hardware: replay a recorded session through the real detector into the website.
# Start ./web.sh first. Loops until Ctrl+C. Nothing is recorded.
#
#   ./replay.sh                      the airborne flight (session 20261011_013730, frames 1120-1400:
#                                    tracked with dropouts, then ~2.5 s undetected so the pin sticks)
#   ./replay.sh full                 that whole session, ground handling included
#   ./replay.sh <session> [start end] any session in AI/recordings, optionally a frame range
#
# Recordings are already stored upright, so the detector runs with --flip none.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-$(command -v python || command -v python3 || true)}"
[ -n "$PYTHON" ] && [ -x "$PYTHON" ] || { echo "[replay.sh] no python found; set PYTHON=/path/to/python" >&2; exit 1; }
PORT="${FAKE_CAMERA_PORT:-8090}"

session=session_20261011_013730 start=1120 end=1400
case "${1:-}" in
  "") ;;
  full) start=0 end="" ;;
  *) session="$1" start="${2:-0}" end="${3:-}" ;;
esac
raw="$ROOT/AI/recordings/${session#AI/recordings/}/raw.lep"
[ -f "$raw" ] || { echo "[replay.sh] no recording at $raw" >&2; exit 1; }

cd "$ROOT"
export YOLO_OFFLINE=1 PYTHONUNBUFFERED=1
"$PYTHON" -m AI.scripts.fake_lepton "$raw" --port "$PORT" --start "$start" ${end:+--end "$end"} \
  > >(sed -u 's/^/[camera] /') 2>&1 &
camera=$!
trap 'kill "$camera" 2>/dev/null; wait "$camera" 2>/dev/null' EXIT
echo "[replay.sh] replaying $session frames ${start}-${end:-end} (looping); Ctrl+C stops"
sleep 2
THERMAL_RELAY_PORT="${THERMAL_RELAY_PORT:-5000}" "$ROOT/drone.sh" \
  --camera-url "http://127.0.0.1:$PORT" --flip none --no-record
