#!/usr/bin/env bash
# Start the whole live pipeline in one terminal: thermal relay, website and Lepton detector.
# Output is prefixed [relay] / [web] / [ai]. Ctrl+C (or any part exiting) stops everything.
#
#   ./start.sh                     camera on the drone (image rotated 180 degrees)
#   ./start.sh --flip none         camera upright, e.g. on the desk
#   ./start.sh --no-record         any other lepton_live options are passed through
#
# PYTHON selects the interpreter (default: python on PATH). THERMAL_RELAY_PORT moves the relay
# (default 5000); START_WEB=0 skips the website, e.g. when it is already running.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-$(command -v python || command -v python3)}"
RELAY_URL="http://127.0.0.1:${THERMAL_RELAY_PORT:-5000}"
pids=()

start() {  # start <label> <dir> <command...>: own process group, so stop() can end its children too
  local label=$1 dir=$2
  shift 2
  (cd "$dir" && exec setsid "$@") > >(sed -u "s/^/[$label] /") 2>&1 &
  pids+=($!)
}

stop() {
  trap - INT TERM EXIT
  echo "[start] stopping..."
  for pid in "${pids[@]}"; do kill -TERM -- "-$pid" 2>/dev/null; done
  sleep 2
  for pid in "${pids[@]}"; do kill -KILL -- "-$pid" 2>/dev/null; done
  wait 2>/dev/null
  exit 0
}
trap stop INT TERM EXIT

[ -x "$PYTHON" ] || { echo "[start] no python found; set PYTHON=/path/to/python" >&2; exit 1; }

export THERMAL_RELAY_PORT="${THERMAL_RELAY_PORT:-5000}"
start relay "$ROOT/ground-station" npm run --silent thermal:relay
[ "${START_WEB:-1}" = 0 ] || start web "$ROOT/ground-station" npm run --silent dev

# The detector retries the relay on its own, but waiting keeps the first lines clean.
for _ in $(seq 30); do
  curl -s -o /dev/null "$RELAY_URL/health" && break
  sleep 0.5
done

start ai "$ROOT" env PYTHONUNBUFFERED=1 "$PYTHON" -m AI.scripts.lepton_live --socket-url "$RELAY_URL" "$@"
[ "${START_WEB:-1}" = 0 ] || echo "[start] website: http://127.0.0.1:5173"
echo "[start] running; Ctrl+C stops everything"

wait -n "${pids[@]}"
echo "[start] a process exited"
