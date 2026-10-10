#!/usr/bin/env bash
# Sweep WBF ensemble settings on val, then score the same grid on the locked test.
#
#   AI/scripts/run_ensemble.sh [member.pt ...]
#
# Defaults to YOLO26s-P2 + YOLO26m. Pick the setting on val (val_summary.txt) and only
# read test_summary.txt for that setting; choosing on test overfits two sequences.
set -euo pipefail

ROOT=${VIGIL_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}
PYTHON=${PYTHON:-python}
DEVICE=${DEVICE:-0}
DATA=${DATA:-AI/datasets/thermal_mega_5fold_lepton_medium_range/fold_0/data.yaml}
OUTPUT=${OUTPUT:-AI/reports/ensemble}
cd "$ROOT"

if [ "$#" -ge 2 ]; then
  MEMBERS=("$@")
else
  MEMBERS=(
    AI/models/runs/thermal_medium_range_yolo26s_p2/weights/best.pt
    AI/checkpoints/thermal_medium_range_yolo26m_best.pt
  )
fi

for SPLIT in val test; do
  "$PYTHON" -m AI.scripts.evaluate_ensemble --weights "${MEMBERS[@]}" --data "$DATA" \
    --split "$SPLIT" --grid --device "$DEVICE" --output "$OUTPUT"
done
echo "Summaries: $OUTPUT/val_summary.txt and $OUTPUT/test_summary.txt"
