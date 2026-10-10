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

For the full source-video release, the importer can consume the extracted `*_IR_*` folders
directly. Run these commands from the repository root:

```bash
python -m AI.scripts.import_wisard_raw \
  /home/agnco/PyTorch/Files \
  AI/datasets/wisard_full_ir_manifest

python -m AI.scripts.inspect_dataset \
  AI/datasets/wisard_full_ir_manifest/data.yaml \
  --output AI/reports/wisard_full_ir_preflight
```

The canonical manifest references source images with symlinks, writes normalized labels into
the workspace, and leaves the extracted download unchanged. A missing source label is accepted
as an empty frame only when that video's `count.txt` explicitly declares zero humans.

## 1. Inspect the original dataset

```bash
python scripts/inspect_dataset.py datasets/wisard_original \
  --output reports/wisard_original
```

This validates image/label pairing, YOLO coordinates, class IDs, empty frames, image
channels and data types. It reports bounding-box dimensions after an effective 160 x 120
reduction, flags boxes with a side smaller than four pixels, and saves annotated examples.

Review `reports/wisard_original/inspection_report.json` before training.

Before building folds from a new/full export, inspect `source_sequence_overlap.parser_audit`
and `exact_content_duplicates`. A high singleton/unparsed-frame count indicates that filename
grouping needs adjustment; cross-split pixel duplicates must be resolved before evaluation.

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

For a final experiment, choose untouched source videos before looking at model results, put one
exact sequence name per line in `config/wisard_locked_test_sequences.txt`, and add:

```bash
  --holdout-sequences-file config/wisard_locked_test_sequences.txt
```

Those videos are excluded from every cross-validation train/validation fold and exposed through
each fold YAML's common `test` split.

The sequence list can be selected deterministically, without looking at model performance, while
balancing image, annotation, and tiny-target counts:

```bash
python scripts/select_holdout_sequences.py \
  /path/to/full_wisard/data.yaml \
  config/wisard_locked_test_sequences.txt \
  --fraction 0.05 \
  --seed 26
```

Review and preserve both the generated text file and its adjacent JSON selection report before
building folds.

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

For video-correlated or combined datasets, sample a fresh, source-balanced subset every epoch
while still validating on the complete validation split:

```bash
python scripts/train.py \
  --data datasets/wisard_5fold_lepton/fold_0/data.yaml \
  --model yolo26s.pt \
  --epochs 50 \
  --batch 0.8 \
  --optimizer AdamW \
  --lr0 0.001 \
  --epoch-fraction 0.20 \
  --name lepton_fold_0_resampled
```

The sampler preserves the training pool's image-level positive/negative ratio, balances source
sequences within each presence class, samples without replacement inside an epoch, and changes the
sample deterministically each epoch. This is different from Ultralytics `fraction`, which selects
a fixed subset.

For hard-negative fine-tuning, mine labeled-negative training frames and request an explicit
positive/hard-negative/ordinary-negative epoch mix:

```bash
python -m AI.scripts.mine_hard_negatives \
  --weights AI/models/runs/thermal_mega_fold_0_resampled-2/weights/best.pt \
  --data AI/datasets/thermal_mega_5fold_lepton/fold_0/data.yaml \
  --confidence 0.20 \
  --output AI/datasets/thermal_mega_5fold_lepton/fold_0/hard_negatives_conf020.json

python -m AI.scripts.train \
  --data AI/datasets/thermal_mega_5fold_lepton/fold_0/data.yaml \
  --model AI/models/runs/thermal_mega_fold_0_resampled-2/weights/best.pt \
  --epoch-fraction 0.10 \
  --hard-negative-manifest AI/datasets/thermal_mega_5fold_lepton/fold_0/hard_negatives_conf020.json \
  --positive-fraction 0.50 \
  --hard-negative-fraction 0.25 \
  --selection-metric presence_f1 \
  --presence-conf 0.40
```

The remaining 25% is ordinary labeled-negative frames. Mining is restricted to `split=train`;
validation and locked-test frames are never eligible.

With `--selection-metric presence_f1`, validation logs frame-presence precision, recall, F1,
specificity, and false-positive-frame rate at the requested confidence. `best.pt` and early
stopping use presence F1 instead of Ultralytics box-mAP fitness. Full ordered-video temporal
metrics remain a post-training evaluation.

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

### Sequence-balanced comparison

Long videos can dominate frame-level training even when folds are correctly grouped by video.
Build deterministic training lists that retain at most 350 temporally distributed positive
frames per source sequence, retain every generated negative/hard-negative crop, and leave every
validation list unchanged:

```bash
python scripts/balance_training_sequences.py \
  datasets/wisard_5fold_lepton \
  datasets/wisard_5fold_lepton_balanced_all_negatives \
  --max-originals-per-sequence 350 \
  --negative-policy all
```

Run fold 0 with the same hyperparameters as the unbalanced baseline so balancing is the only
experimental variable:

```bash
python scripts/train.py \
  --data datasets/wisard_5fold_lepton_balanced_all_negatives/fold_0/data.yaml \
  --model ../yolo26s.pt \
  --epochs 50 \
  --imgsz 640 \
  --batch 0.8 \
  --device 0 \
  --freeze 0 \
  --scale 0.25 \
  --name lepton_fold_0_balanced_cap350_allneg_scale025
```

Keep the normal per-epoch losses, precision, recall, mAP50, and mAP50-95 for direct comparison.
Run the per-video and temporal evaluator on `best.pt` and `last.pt` after training rather than
adding the expensive prediction pass to every epoch.

## 5. Evaluate held-out folds

Each fold's `val` split is sequence-disjoint from that fold's training data:

```bash
for fold in 0 1 2 3 4; do
  python scripts/evaluate.py \
    --weights models/runs/lepton_fold_${fold}/weights/best.pt \
    --data datasets/wisard_5fold_lepton/fold_${fold}/data.yaml \
    --split val \
    --presence-conf 0.25 \
    --match-iou 0.25 \
    --match-mode iou_or_center \
    --temporal-window 3 \
    --temporal-min-hits 2 \
    --output reports/lepton_fold_${fold}_val.json
done
```

Each report includes:

- standard person precision, recall, mAP50, and mAP50-95;
- frame-presence precision, recall, F1, specificity, and a confidence-threshold curve;
- relaxed one-to-one person matching using IoU >= 0.25 or a predicted center inside the label;
- per-video frame metrics so long videos cannot hide failures on short videos;
- event recall, temporal coverage, longest miss streak, and time to first detection;
- raw and 2-of-3 temporally smoothed alert behavior; and
- false-positive frame and detection rates on empty images.

Synthetic negative crops count toward frame-level false positives but are excluded from temporal
ordering because they are crops, not subsequent camera frames. Temporal durations are reported in
observed frames rather than seconds unless source FPS metadata becomes available.

Report the mean and standard deviation across all five folds. Original-resolution and
simulated-resolution numbers remain separate experimental conditions. The cross-validation
summary pools confusion counts at every evaluated confidence threshold to select one global
out-of-fold operating threshold.

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
