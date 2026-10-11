#!/usr/bin/env bash
# Ground station: thermal relay + website, in one terminal. Start the camera side with ./drone.sh.
# Output is prefixed [relay] / [web]. Ctrl+C (or either part exiting) stops both.
#
#   ./web.sh
#
# THERMAL_RELAY_PORT moves the relay (default 5000); START_WEB=0 runs only the relay.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pids=()

start() {  # start <label> <dir> <command...>: own process group, so stop() can end its children too
  local label=$1 dir=$2
  shift 2
  (cd "$dir" && exec setsid "$@") > >(sed -u "s/^/[$label] /") 2>&1 &
  pids+=($!)
}

stop() {
  trap - INT TERM EXIT
  echo "[web.sh] stopping..."
  for pid in "${pids[@]}"; do kill -TERM -- "-$pid" 2>/dev/null; done
  sleep 2
  for pid in "${pids[@]}"; do kill -KILL -- "-$pid" 2>/dev/null; done
  wait 2>/dev/null
  exit 0
}
trap stop INT TERM EXIT

export NEXT_TELEMETRY_DISABLED=1  # no internet calls from Next.js
export THERMAL_RELAY_PORT="${THERMAL_RELAY_PORT:-5000}"
start relay "$ROOT/ground-station" npm run --silent thermal:relay
[ "${START_WEB:-1}" = 0 ] || start web "$ROOT/ground-station" npm run --silent dev

[ "${START_WEB:-1}" = 0 ] || echo "[web.sh] website: http://127.0.0.1:5173   then run ./drone.sh in another terminal"
echo "[web.sh] running; Ctrl+C stops it"

wait -n "${pids[@]}"
echo "[web.sh] a process exited"
