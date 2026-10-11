# VIGIL AI — Current Agent Handoff

Updated: 2026-10-10 (America/New_York)

## Objective

Train a YOLO26s person detector for low-resolution thermal video, targeting FLIR Lepton 3.5
spatial detail (160×120). Operational priorities are high person-presence precision/recall and
stable detection over time, not only strict bounding-box localization. Evaluation must be
video-disjoint and include per-video and temporal metrics.

## Current state (live system)

Everything from "Source dataset discovery" onward is the history of the WiSARD training work
(on the old `thermal-recognition` branch). The live system now runs on `main`:

```text
Lepton 3.5 -> XIAO ESP32-S3 (Wi-Fi AP "Lepton-Camera", flir-lepton/) -> AI/scripts/lepton_live.py
  -> Socket.IO relay (ground-station: npm run thermal:relay) -> website (npm run dev, :5173)
```

- Run everything (relay, website, detector) with `./start.sh` from the repo root; Ctrl+C stops all.
  The detector alone: `python -m AI.scripts.lepton_live --socket-url http://127.0.0.1:5000`.
  Frames are rotated 180° by default (camera mounted upside down on the drone); `--flip none` for an upright camera. Every session is
  recorded to `AI/recordings/session_*` (raw.lep, frames, detections.jsonl, annotated.mp4).
- Models, both in `AI/checkpoints/` and both used by default:
  - near: `thermal_medium_range_yolo26s_p2_closeup_blur_best.pt` (P2 head, fine-tuned on
    OpenThermalPose2 close-ups with Lepton-like blur/noise; `--weights`)
  - far: `thermal_medium_range_yolo26s_p2_best.pt` (`--far-weights none` disables)
  - The two are merged per frame (`MergedDetector`) with NMS and part/group-box suppression.
- Post-processing: ByteTrack (start 0.30 / keep 0.15), 2-frame hold for lost tracks, a track
  is only shown after 3 hits (`--min-hits`), and boxes hotter than 42 °C are dropped (PCB shorts, lamps).
- Offline tuning: `python -m AI.scripts.replay_session AI/recordings/<session> --weights <near>
  --far-weights <far>` replays a recording through the same pipeline; `AI/scripts/fake_lepton.py`
  serves a recording as a fake camera for website demos without hardware.
- Known issues: the `lepton_fold_0*` runs have train/val leakage; pseudo-labels from
  `pseudo_label_session.py` were unreliable and are not used in training. All live tests so far
  were indoors under ~10 m; no in-flight footage yet.
- Website geolocation pairs each frame with the newest telemetry (no camera/telemetry clock
  sync), so the pose can be up to ~2 s old; real-world accuracy has not been measured.
- The Lepton Wi-Fi password is in the gitignored `flir-lepton/include/secrets.h`.

## Environment

- Repository: `/home/agnco/PyTorch/Workspace/VIGIL`
- Virtual environment Python: `/home/agnco/PyTorch/bin/python`
- Python 3.12.3
- Ultralytics 8.4.175
- PyTorch 2.9.1+cu130
- GPU: NVIDIA GeForce RTX 5080 Laptop GPU, 16,303 MiB

Run commands from the repository root. Prefer `python -m AI.scripts.<module>` so imports resolve
consistently.

## Source dataset discovery

The full WiSARD release was already extracted under:

`/home/agnco/PyTorch/Files`

There were no remaining archives to unpack. The directory contains 41 IR video folders, 39 VIS
folders, and the older Roboflow export `WiSARD_IR.v2i.yolo26`. Only IR was imported. The extracted
source files were deliberately left untouched.

Full IR inventory:

- 29,878 images, all 640×512
- 27,544 class-0 person boxes
- 24,084 images originally had label sidecars
- 10,286 of those labels were explicitly empty
- 5,794 images had no sidecar label, all belonging to six complete videos whose `count.txt`
  explicitly declares zero humans
- Those 5,794 frames were accepted as verified real negatives and given explicit empty labels in
  the canonical dataset
- 536 annotations with small boundary-rounding overflow were clipped into normalized image bounds;
  materially invalid overflow is rejected
- 16,080 total empty/negative frames after canonical import

## Canonical import and validation

Canonical manifest:

`AI/datasets/wisard_full_ir_manifest/data.yaml`

Importer:

`AI/scripts/import_wisard_raw.py`

The canonical dataset uses absolute image symlinks and separate normalized labels, so it consumes
little space and does not modify the download. Canonical filenames preserve video/frame identity.

The dataset utilities were changed to preserve logical symlink paths rather than dereferencing
them; dereferencing would pair images with the unnormalized raw labels and discard canonical video
names. There are regression tests for this behavior.

Correct full-dataset preflight results:

- 29,878 readable images
- 27,544 valid boxes
- 16,080 empty labels
- zero missing labels
- zero invalid boxes/lines/classes
- all frames parsed into exactly 41 source videos
- zero unparsed frame numbers
- 11 exact decoded-pixel duplicate groups (22 frames), all within their source videos
- no cross-split duplicates at this stage because this manifest is not yet split

Use the newer correct report:

`AI/reports/wisard_full_ir_preflight_new/inspection_report.json`

An older report at `AI/reports/wisard_full_ir_preflight` was produced before the symlink-path fix
and incorrectly inspected raw labels. Do not use that older report.

## Locked test set and five-fold design

The final test set was selected before model evaluation by exhaustive deterministic search that
balanced video, image, annotation, and tiny-target fractions.

Files:

- `AI/config/wisard_full_ir_locked_test.txt`
- `AI/config/wisard_full_ir_locked_test.json`

Locked test videos:

1. `200929_Karen_FLIR_IR_6__20200929_134258_IR`
2. `210924_FHL_Enterprise_IR_0408__DJI_0408.mp4`

Locked test composition:

- 2/41 videos (4.878%)
- 1,486/29,878 images (4.974%)
- 1,291/27,544 annotations (4.687%)
- 631/11,874 tiny annotations (5.314%)
- One test video is all-positive and the other is all-negative; together they provide a demanding
  presence/false-alert test.

Do not use this test set for hyperparameter, optimizer, epoch, threshold, or checkpoint selection.

Grouped fold metadata:

`AI/datasets/wisard_full_ir_5fold`

All 39 development videos validate exactly once across five folds. The two locked videos appear
only in the common test split. There is no video overlap among train/val/test. No synthetic
negative crops were generated because the full release already has 16,080 genuine negative
frames.

## Lepton spatial-detail dataset

Prepared dataset:

`AI/datasets/wisard_full_ir_5fold_lepton`

Preparation applies grayscale conversion and aspect-ratio-preserving letterboxing to 160×120,
then transforms boxes. This simulates spatial detail only; it does not simulate Lepton noise,
thermal response, optics/FOV, radiometry, or bit depth. Training at `imgsz=640` upsamples these
160×120 images for the network but cannot restore lost detail.

Preparation totals:

- 29,878 unique images
- 16,080 empty negatives
- 27,544 annotations
- approximately 464 MiB on disk

Fold-0 preflight:

`AI/reports/wisard_full_ir_5fold_lepton_fold0_preflight/inspection_report.json`

Fold 0:

- Train: 22,686 images, 30 videos, 21,549 boxes
- Train positive/empty frames: 10,589 / 12,097
- Validation: 5,706 images, 9 videos, 4,704 canonical boxes
- Validation positive/empty frames: 2,758 / 2,948
- Test: 1,486 images, 2 videos, 1,291 boxes
- No shared sequences or exact frame IDs across splits
- 12 decoded-pixel duplicate groups after conversion, zero cross-split groups
- Roughly 43% of boxes have at least one side below four pixels at effective 160×120 detail

## Current fold-0 training run

Run directory:

`AI/models/runs/wisard_full_lepton_fold_0`

Checkpoints:

- `AI/models/runs/wisard_full_lepton_fold_0/weights/best.pt`
- `AI/models/runs/wisard_full_lepton_fold_0/weights/last.pt`

Original configuration:

- model: `yolo26s.pt`
- epochs: 50
- image size: 640
- batch: 0.8 AutoBatch target (observed 597 batches for 22,686 frames, effective batch 38)
- device: 0
- freeze: 0 (all layers trainable)
- workers: 8
- optimizer: `auto`
- scale: 0.25
- mosaic/mixup: 0
- patience: 20
- seed: 26

Important optimizer finding: with the larger dataset and 50 epochs, Ultralytics `optimizer=auto`
crossed its 10,000-iteration threshold and selected MuSGD rather than the AdamW used by the smaller
experiments. MuSGD boosts certain fine-tuning/head groups to 3× learning rate. During early warmup,
reported boosted-group LR rose to approximately 0.029 while other groups reached approximately
0.0096. Earlier AdamW experiments peaked around 0.0019. This produced highly oscillatory early
validation metrics, but the run later achieved a new best, so it was not monotonic divergence.

Checkpoint metadata (authoritative even though `results.csv` is currently absent):

### `best.pt`

- Displayed epoch: 21 (checkpoint's zero-based `epoch` field is 20)
- best fitness / mAP50-95: 0.18368
- precision: 0.6274
- recall: 0.6317
- mAP50: 0.4717
- validation box loss: 2.23941
- validation classification loss: 2.02062
- validation L1 loss: 0.00632
- boosted/base LR: 0.01812 / 0.00604

### `last.pt`

- Latest stored displayed result: epoch 26 (checkpoint `epoch` field is 25)
- best fitness retained: 0.18368
- current precision: 0.60277
- current recall: 0.58489
- current mAP50: 0.43772
- current mAP50-95: 0.15599
- validation box loss: 2.32804
- validation classification loss: 2.12457
- validation L1 loss: 0.00667
- boosted/base LR: 0.01515 / 0.00505

The run's `results.csv` disappeared during/after the interruption, but checkpoint-embedded
`train_results` and `train_metrics` preserve the values above. The handoff intentionally omits
crash-resume procedures per the user's request.

## Interpretation so far

The early sequence was very noisy: mAP50-95 fell from 0.135 at epoch 1 to 0.111 at epoch 3,
rebounded to 0.158 at epoch 4, and oscillated around 0.13–0.16 through epoch 8. It eventually
reached 0.18368 at epoch 21. Training losses continued to improve while validation oscillated.

Likely contributors:

1. MuSGD's aggressive auto-selected learning rate caused early instability.
2. The new validation set is honestly video-disjoint, unlike the original small Roboflow split,
   so it exposes real cross-video/domain generalization difficulty.
3. More than half of both train and validation frames are true negatives.
4. Many targets are extremely small after 160×120 reduction, making strict localization and
   mAP50-95 particularly difficult.
5. Different videos vary substantially in sensor/location/altitude/background composition.

Do not conclude that the full dataset is worse merely by comparing it with the old validation
score. The old small experiment reported approximately P=0.902, R=0.670, mAP50=0.742, and
mAP50-95=0.361 on 2,475 images/4,882 instances, but that split was much easier and not a clean
source-video generalization test.

## Evaluation tooling

Standard training metrics should remain available, but the product-relevant analysis is in:

- `AI/scripts/evaluate.py`
- `AI/scripts/temporal_metrics.py`
- `AI/scripts/summarize_cv.py`

The evaluator reports:

- normal precision, recall, mAP50, and mAP50-95
- frame-presence precision/recall/F1/specificity and a confidence-threshold curve
- relaxed one-to-one matching using IoU ≥ 0.25 or predicted-center-inside-label
- per-video results
- temporal coverage and event recall
- longest miss streak and time to first detection
- raw and 2-of-3 smoothed alert behavior
- false-positive frame/detection rates on empty frames

Evaluate the current best checkpoint on validation only:

```bash
python -m AI.scripts.evaluate \
  --weights AI/models/runs/wisard_full_lepton_fold_0/weights/best.pt \
  --data AI/datasets/wisard_full_ir_5fold_lepton/fold_0/data.yaml \
  --split val \
  --presence-conf 0.25 \
  --match-iou 0.25 \
  --match-mode iou_or_center \
  --temporal-window 3 \
  --temporal-min-hits 2 \
  --output AI/reports/wisard_full_lepton_fold_0_best_val.json
```

Do not run the evaluator on `split=test` until the complete modeling recipe and operating threshold
have been selected without reference to the locked test videos.

## Recommended next work

1. Run per-video and temporal validation metrics on the current `best.pt`. Determine whether the
   mediocre aggregate score is broad or caused by one/two difficult validation videos.
2. Preserve the current MuSGD result as a baseline.
3. Run one controlled fold-0 comparison from the original `yolo26s.pt` using explicit
   `--optimizer AdamW --lr0 0.001`; do not initialize that comparison from MuSGD `last.pt`.
4. Keep every other setting and the fold identical. Compare best validation checkpoints using the
   custom per-video/temporal metrics, not only mAP.
5. Decide the optimizer/checkpoint rule on fold 0, then run folds 1–4. Avoid repeatedly tuning on
   fold 0 indefinitely.
6. Pool all five out-of-fold validation reports with `AI/scripts/summarize_cv.py`, select one global
   presence-confidence threshold, and only then evaluate the locked test split once.
7. Mix in external thermal datasets only after establishing this full-WiSARD baseline. External
   data may help occlusion/domain diversity but introduces label-policy and sensor-domain issues.

Controlled AdamW command for a future comparison:

```bash
python -m AI.scripts.train \
  --data AI/datasets/wisard_full_ir_5fold_lepton/fold_0/data.yaml \
  --model yolo26s.pt \
  --epochs 50 \
  --imgsz 640 \
  --batch 0.8 \
  --device 0 \
  --freeze 0 \
  --workers 8 \
  --optimizer AdamW \
  --lr0 0.001 \
  --scale 0.25 \
  --patience 12 \
  --project AI/models/runs \
  --name wisard_full_lepton_fold_0_adamw
```

## Tests

Last complete test run (2026-10-10) passed 37 tests:

```bash
/home/agnco/PyTorch/bin/python -m unittest discover -s AI/tests -v
```

Tests cover dataset preflight behavior, symlink/label pairing, video/frame parsing, locked-test
isolation, duplicate reporting, deterministic holdout selection, sequence balancing, frame
matching, temporal smoothing, and pooled cross-validation threshold selection.

