#!/usr/bin/env bash
# Camera side: read the Lepton, detect and track people, publish to the relay started by ./web.sh.
# Every session is recorded under AI/recordings/. Ctrl+C stops it.
#
#   ./drone.sh                     camera on the drone (image rotated 180 degrees)
#   ./drone.sh --flip none         camera upright, e.g. on the desk
#   ./drone.sh --no-record         any other lepton_live options are passed through
#
# PYTHON selects the interpreter (default: python on PATH).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-$(command -v python || command -v python3 || true)}"
RELAY_URL="http://127.0.0.1:${THERMAL_RELAY_PORT:-5000}"

[ -n "$PYTHON" ] && [ -x "$PYTHON" ] || { echo "[drone.sh] no python found; set PYTHON=/path/to/python" >&2; exit 1; }
curl -s -o /dev/null "$RELAY_URL/health" ||
  echo "[drone.sh] relay not running at $RELAY_URL; start ./web.sh (detections are still recorded)" >&2

cd "$ROOT"
exec env PYTHONUNBUFFERED=1 "$PYTHON" -m AI.scripts.lepton_live --socket-url "$RELAY_URL" "$@"
