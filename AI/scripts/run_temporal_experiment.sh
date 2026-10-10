#!/usr/bin/env bash
# Train and evaluate the YOLO26s-P2 recipe on 3-frame temporal stacks.
#
#   AI/scripts/run_temporal_experiment.sh [none|phase] [frame-step] [fold] [device]
#
# none  = raw [t-2, t-1, t] stacks
# phase = neighbours phase-correlation aligned to frame t (compensates drone drift)
# frame-step k stacks [t-2k, t-k, t]; raise it if the training video is faster than the
# Lepton's ~9 fps so the motion between channels matches what the drone sees.
#
# Builds the temporal dataset if it is missing, trains, then writes val/test reports to
# AI/reports/sweep_conf040/ next to the single-frame models so they compare directly.
# Fold lists hold absolute paths: keep the repo at the same path on every machine, or
# rebuild the source fold roots there first.
set -euo pipefail

ALIGN=${1:-none}
STEP=${2:-1}
FOLD=${3:-0}
DEVICE=${4:-0}
ROOT=${VIGIL_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}
PYTHON=${PYTHON:-python}
cd "$ROOT"

case "$ALIGN" in
  none) SUFFIX=temporal ;;
  phase) SUFFIX=temporal_align ;;
  *) echo "align must be none or phase" >&2; exit 2 ;;
esac
[ "$STEP" -gt 1 ] && SUFFIX=${SUFFIX}_step${STEP}

SOURCE=AI/datasets/thermal_mega_5fold_lepton_medium_range
DATASET=${SOURCE}_${SUFFIX}
NAME=thermal_medium_range_yolo26s_p2_${SUFFIX}_fold${FOLD#fold_}
DATA=$DATASET/fold_${FOLD#fold_}/data.yaml
REPORTS=AI/reports/sweep_conf040

if [ ! -f "$DATASET/preparation_report.json" ]; then
  echo "Building $DATASET"
  "$PYTHON" -m AI.scripts.prepare_temporal "$SOURCE" "$DATASET" --align "$ALIGN" --frame-step "$STEP"
fi

WEIGHTS=AI/models/runs/$NAME/weights/best.pt
# P2 was fine-tuned from this fold-0 base checkpoint; reusing it on other folds would leak
# fold 0's training sequences into their val sets (see AI/BENCHMARK.md).
INIT=${INIT:-AI/checkpoints/thermal_mega_medium_crop_fold0_best.pt}
if [ "${FOLD#fold_}" != 0 ] && [ -z "${INIT_OVERRIDE:-}" ]; then
  echo "Fold ${FOLD#fold_} needs its own base checkpoint: set INIT=... and INIT_OVERRIDE=1" >&2
  exit 2
fi
if [ ! -f "$WEIGHTS" ]; then
  # Same recipe as thermal_medium_range_yolo26s_p2, except hue/saturation jitter is off:
  # the channels are frames in time, and colour jitter would mix them.
  "$PYTHON" -m AI.scripts.train \
    --data "$DATA" \
    --model yolo26s-p2.yaml \
    --pretrained-weights "$INIT" \
    --name "$NAME" \
    --project AI/models/runs \
    --device "$DEVICE" \
    --epochs 50 --patience 25 --batch 0.85 \
    --optimizer AdamW --lr0 0.001 \
    --scale 0.25 --mosaic 0 --mixup 0 \
    --hsv-h 0 --hsv-s 0 --hsv-v 0.4 \
    --epoch-fraction 0.20 \
    --selection-metric presence_f1 --presence-conf 0.40 \
    --seed 26
fi

mkdir -p "$REPORTS"
for SPLIT in val test; do
  OUT=$REPORTS/${SPLIT}_${NAME}_best.json
  [ -s "$OUT" ] && continue
  "$PYTHON" -m AI.scripts.evaluate --weights "$WEIGHTS" --data "$DATA" --split "$SPLIT" \
    --presence-conf 0.40 --device "$DEVICE" --output "$OUT"
done

echo "Done. Live use: python -m AI.scripts.lepton_live --weights $WEIGHTS --temporal-step 1 --temporal-align $ALIGN (dataset frame-step $STEP)"
