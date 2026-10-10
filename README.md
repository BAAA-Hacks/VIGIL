# VIGIL

VIGIL's initial AI pipeline fine-tunes and evaluates a **YOLO26s person detector** on
WiSARD_IR thermal imagery. It also creates a controlled spatial-detail approximation of a
FLIR Lepton 3.5 frame (160 x 120) and emits frame detections in a UI-friendly JSON format.

The Lepton preprocessing models spatial detail only. It does **not** reproduce the sensor's
thermal response, noise, optics/FOV, radiometric mapping, or bit depth.

## Environment setup (Linux)

Python 3.10 or newer is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Install the CUDA-enabled PyTorch build recommended for your machine by the
[PyTorch selector](https://pytorch.org/get-started/locally/), then install this project's
packages:

```bash
python -m pip install -r requirements.txt
```

Verify CUDA and Ultralytics:

```bash
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
python -c "import ultralytics; print(ultralytics.__version__)"
yolo checks
```

The scripts require `yolo26s.pt`. If the installed Ultralytics package cannot load it, the
training script exits with an upgrade/download error and never substitutes another model.

## Dataset placement

Download the Roboflow WiSARD_IR v2 export in YOLO26 Detection format, then extract it
without modifying it:

```text
datasets/wisard_original/
  data.yaml
  train/
  valid/
  test/
```

The expected Roboflow split is 8,093 training, 489 validation, and 689 test images. The
scripts read the actual paths from `data.yaml`, so the extraction may use a slightly
different folder layout.

## 1. Inspect the original dataset

```bash
python scripts/inspect_dataset.py datasets/wisard_original \
  --output reports/wisard_original
```

This validates image/label pairing, YOLO coordinates, class IDs, empty frames, image
channels and data types. It reports bounding-box dimensions after an effective 160 x 120
reduction, flags boxes with a side smaller than four pixels, and saves annotated examples.

Review `reports/wisard_original/inspection_report.json` before training.

The v2 export has no empty-background frames. Its original test set is also drawn from a
video that occurs in training, so the preferred experiment is grouped cross-validation.

## 2. Build five sequence-grouped folds and negatives

```bash
python scripts/build_folds.py \
  /path/to/WiSARD_IR.v2i.yolo26/data.yaml \
  datasets/wisard_5fold \
  --folds 5 \
  --negative-fraction 0.25 \
  --seed 26
```

The builder combines the supplied splits but keeps every source video wholly inside one
held-out fold. It creates one candidate background crop for approximately 25% of frames,
rejecting any crop that intersects a known person box plus an eight-pixel safety margin.
Each negative stays grouped with its parent video.

Derived negatives are resized to 640 x 480 and receive explicit empty label files. Review
`datasets/wisard_5fold/negatives/images` before training: crop exclusion can protect known
boxes, but it cannot detect a person omitted from the source annotations. Crop coordinates,
parents, and held-out assignments are recorded in `negative_manifest.json`.

Fold YAMLs and image lists are under `fold_0` through `fold_4`. Original images are referenced
by absolute path rather than copied or modified.

## 3. Generate the shared Lepton spatial-detail dataset

```bash
python scripts/prepare_cv_lepton.py \
  datasets/wisard_5fold \
  datasets/wisard_5fold_lepton
```

Each unique original or negative is converted once. The script:

- converts it to grayscale when necessary;
- downsamples it with area interpolation while preserving aspect ratio;
- pads it to 160 x 120 rather than stretching it;
- transforms labels for the scale and padding;
- preserves empty negative labels; and
- emits lightweight train/validation lists for all five folds.

Inspect at least one fold before training:

```bash
python scripts/inspect_dataset.py datasets/wisard_5fold_lepton/fold_0/data.yaml \
  --output reports/wisard_5fold_lepton/fold_0
```

`prepare_wisard.py` remains available for a simple fixed-split experiment, but that experiment
must be labeled as sequence-leaked when reporting results.

## 4. Train YOLO26s across five folds

The primary cross-validation run trains all layers and disables mosaic/mixup by default
because many targets are already tiny:

```bash
for fold in 0 1 2 3 4; do
  python scripts/train.py \
    --data datasets/wisard_5fold_lepton/fold_${fold}/data.yaml \
    --model yolo26s.pt \
    --epochs 50 \
    --imgsz 640 \
    --batch -1 \
    --device 0 \
    --freeze 0 \
    --name lepton_fold_${fold}
done
```

Optional two-stage run (5 frozen-backbone epochs, then 45 fully trainable epochs):

```bash
python scripts/train.py \
  --data datasets/wisard_5fold_lepton/fold_0/data.yaml \
  --epochs 5 \
  --freeze 10 \
  --name lepton_fold_0_warmup

python scripts/train.py \
  --data datasets/wisard_5fold_lepton/fold_0/data.yaml \
  --model models/runs/lepton_fold_0_warmup/weights/last.pt \
  --epochs 45 \
  --freeze 0 \
  --optimizer AdamW \
  --lr0 0.001 \
  --name lepton_fold_0_unfrozen
```

Test the two-stage recipe on one fold before multiplying it across all five. For a fair
original-resolution baseline, use the corresponding `datasets/wisard_5fold/fold_N/data.yaml`
with otherwise identical settings.

## 5. Evaluate held-out folds

Each fold's `val` split is sequence-disjoint from that fold's training data:

```bash
for fold in 0 1 2 3 4; do
  python scripts/evaluate.py \
    --weights models/runs/lepton_fold_${fold}/weights/best.pt \
    --data datasets/wisard_5fold_lepton/fold_${fold}/data.yaml \
    --split val \
    --output reports/lepton_fold_${fold}_val.json
done
```

The report includes person precision, recall, mAP50, mAP50-95, Ultralytics timing, and
false-positive detections/frame rate on empty images at the configured confidence threshold.
Report the mean and standard deviation across all five folds. Original-resolution and
simulated-resolution numbers remain separate experimental conditions.

After all five reports exist:

```bash
python scripts/summarize_cv.py reports/lepton_fold_*_val.json \
  --output reports/lepton_cv_summary.json
```

## 6. Run inference

```bash
python scripts/infer.py \
  --weights models/runs/lepton_fold_0/weights/best.pt \
  --source path/to/images \
  --output reports/detections.json \
  --save-previews reports/inference_previews
```

A single input produces one object; a directory produces an array:

```json
{
  "frame_id": "frame_0001.png",
  "detections": [
    {
      "class": "person",
      "confidence": 0.91,
      "bbox_xyxy_norm": [0.12, 0.18, 0.25, 0.72]
    }
  ],
  "processing_ms": 8.4
}
```

Coordinates are normalized top-left `xyxy` values in `[0, 1]`. Frames without a detection
contain `"detections": []`.

## Experimental cautions

- Never randomly distribute individual frames across folds; group by source sequence.
- Automatically generated negatives require visual review for missed source annotations.
- The original Roboflow test split shares a source video with training and is not an
  independent flight-level test.
- `imgsz=640` changes model input size but cannot restore detail removed at 160 x 120.
- Do not invent metrics. Preserve generated run directories and evaluation JSON files.
