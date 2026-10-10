# VIGIL thermal benchmark protocol

## Protocol

1. **Locked test stays locked.** `AI/config/wisard_full_ir_locked_test.txt` (Karen_IR_6, 451 positive
   frames; FHL_IR_0408, 1035 frames labelled negative) is never trained on or used for model selection.
   It holds one positive event, so it is only a final sanity check, not a ranking metric.
2. **Primary metric = 5-fold cross-validation.** The 39 non-test WiSARD sequences are split
   9/9/8/6/7 into the fold val sets of `AI/datasets/thermal_mega_5fold_lepton_medium_range/fold_{0..4}`,
   grouped by sequence. Each val sequence appears in exactly one fold. A recipe is trained once per fold
   and reported as **mean ± std over the five fold val sets**, plus a **pooled** column (counts summed over
   all folds, i.e. every non-test sequence scored once by a model that never saw it).
3. **Leakage guard before every evaluation.** `check_leakage.py` maps every naming generation onto one
   sequence key and follows checkpoint lineage (`args.yaml` `model: *.pt`, `vigil_lineage.json`).
   `benchmark.py` drops any leaking fold unless `--allow-leakage` is passed.
4. **Flagged sequences.** Sequences with known label defects (default `DJI_0585`, see audit) appear in
   a second "flagged excluded" column. They stay in the primary column, so nothing is dropped silently.
   mAP cannot be recomputed per sequence, so it reads `n/a` in that column.
5. All metrics use `evaluate.py` defaults with `--presence-conf 0.40` (iou_or_center at IoU 0.25,
   temporal window 3 / 2 hits). False alerts are also normalized per 1000 negative frames, since the
   fold val sets differ in size.

## Commands

All paths are relative to the repository root. On another machine, set `VIGIL_ROOT` or pass `--root`.
Absolute paths in the fold lists and data.yaml files are rebased automatically into
`AI/models/runs/portable_yamls/` when the recorded prefix does not exist.

```bash
cd /path/to/VIGIL            # or: export VIGIL_ROOT=/path/to/VIGIL
PY=/home/agnco/PyTorch/bin/python

# Show the commands without training
$PY -m AI.scripts.train_folds --dry-run

# Train the P2 recipe on all five folds (base stage + P2 stage per fold, about 10 trainings).
# Folds that already have weights/best.pt are skipped.
$PY -m AI.scripts.train_folds

# Reuse the existing fold-0 run and train only folds 1-4
$PY -m AI.scripts.train_folds --folds 1 2 3 4

# Another architecture: arguments after -- are appended to train.py and override the recipe
$PY -m AI.scripts.train_folds --model yolo26m.pt --init none --name medium_range_yolo26m_fold{fold} -- --batch 0.8

# Benchmark: leakage guard, evaluation on each fold's val and on the locked test, aggregate table
$PY -m AI.scripts.benchmark --runs thermal_medium_range_yolo26s_p2_fold{fold}

# The same, with the existing fold-0 run standing in for fold 0
$PY -m AI.scripts.benchmark --runs thermal_medium_range_yolo26s_p2_fold{fold} \
    --fold-run 0=thermal_medium_range_yolo26s_p2 --label thermal_medium_range_yolo26s_p2

# Standalone leakage check (exit 1 on leakage; --strict also fails on unverifiable ancestors)
$PY -m AI.scripts.check_leakage --train AI/models/runs/*/args.yaml \
    --eval AI/datasets/thermal_mega_5fold_lepton_medium_range/fold_0/data.yaml
```

Reports go to `AI/reports/benchmark/<label>/`: `fold{k}_{val,test}.json` (+ `.log`; existing reports
are reused), `summary.json`, and `summary.md` (aggregate table plus per-sequence table sorted by recall).

### Recovered P2 recipe

`train_folds.py` defaults reproduce `thermal_medium_range_yolo26s_p2`. `args.yaml` does not record
the options below, so they were inferred from the run's other files:

| stage | settings | evidence |
|---|---|---|
| base | `yolo26s.pt` on `thermal_mega_5fold_lepton_medium_crops/fold_k`, AdamW, lr0 0.001, scale 0.25, epochs 50, patience 50, seed 26, `--epoch-fraction 0.20`, mAP selection | `AI/checkpoints/thermal_mega_medium_crop_fold0_best.pt` train_args; the epoch-1 warmup LR (0.000332) implies 247 batches of 36 = 0.20 × 44371 |
| P2 | `yolo26s-p2.yaml` + `--pretrained-weights <base best.pt>` on `medium_range/fold_k`, AdamW, lr0 0.001, batch 0.85, scale 0.25, epochs 50, patience 25, seed 26, `--epoch-fraction 0.20`, `--selection-metric presence_f1 --presence-conf 0.40` | fitness equals presence F1 (0.8133) and presence columns appear in results.csv; warmup LR implies 538 batches of 21 = 0.20 × 56468; P2 best.pt weights are closest to the medium-crop checkpoint (relative L2 0.44, against 0.80 for yolo26s.pt) |

The fold-0 base was trained on a second machine with `batch 36` (base batch here defaults to 0.8) and
its dataset YAML (`..._fraction50.yaml`) no longer exists, so its lineage cannot be checked
automatically. For a clean variance estimate, retrain all five folds on one machine.

## Audit findings (2026-10-10)

### Leakage: worse than previously known

Run against medium_range fold 0 (`AI/reports/benchmark_audit/leakage_all_runs_vs_medium_range_fold0.json`):

| run | result |
|---|---|
| lepton_fold_0, lepton_fold_0_balanced_cap350, lepton_fold_0_balanced_cap350_allneg_scale025 | **LEAK: 6/9 val sequences and 1/2 locked-test sequences** (Baker_IR_1, Carnation_IR_1/2, Karen_IR_1/4, MtErie_0008, plus test Karen_IR_6 with 418–536 train frames) |
| thermal_medium_range_yolo26s_p2, all thermal_mega_fold_0_*, wisard_full_lepton_fold_0 | clean |
| AI/checkpoints/*.pt | no leak in resolvable data; the ancestor dataset is unverifiable (trained on another machine) |

The old `wisard_5fold_lepton` folds used a different sequence assignment, so the `lepton_fold_0*`
models trained on most of the new fold-0 val set and on the locked test positive video. Their
benchmark numbers, test included (Karen_IR_6 recall 1.00 against 0.73 for P2), are invalid.

### DJI_0585: missing labels, not clutter

`220109_Baker_Enterprise_IR_2__DJI_0585` has 609 frames, and every label file is empty. WiSARD's own
`count.txt` declares "Number of humans: 0". The frames show **a clearly visible person** (human
silhouette with legs, followed by the drone) in almost the whole video. The P2 model fires on 559/609
eval frames at conf ≥ 0.40 (median top confidence 0.79). It is silent only for frames 0–7 (empty
forest before the person enters) and 300–360 (person outside the centre crop, e.g. frame 347).
Renders: `AI/reports/benchmark_audit/dji_0585/frame_*.jpg` (left: 640×512 source with the eval
crop in cyan; right: the 160×120 model input ×4 with detections).
Effect on fold-0 val: specificity 0.730 → 0.899 and F1 0.803 → 0.887 when it is excluded.
The sibling video DJI_0583 from the same flight has 5261 labelled people.

**Recommendation:** relabel DJI_0585, or remove it from evaluation *and training*. Folds 1–4 currently
train on its 1218 images (full view + crops) as negatives, which teaches the model that a visible
person is background.

### Other negative stretches where the model fires

From `AI/reports/benchmark_audit/negative_frame_firing_p2_fold0.json` (P2 on every WiSARD
labelled-negative frame in fold 0 train/val/test; renders in `benchmark_audit/negative_firing/`):

| sequence | split | negative frames fired | longest run | verdict from renders |
|---|---|---|---|---|
| DJI_0585 | val | 559/609 (92%) | 292 | unlabelled person |
| FHL_IR_0404 (DJI_0404) | val | 235/1201 (20%) | 28 | partially labelled: people visible on the shoreline in "negative" frames (e.g. 566) |
| **FHL_IR_0408 (DJI_0408), locked test** | test | 125/1035 (12%) | 42 | **unlabelled people** in the "verified zero-human" test video (frame 502: two people on rocks; frame 140: a seated person). Some other hits (frame 781, near a building) are ambiguous |
| Airfield_IR_4 and others | train | ≤ 8% | ≤ 22 | small hot specks, mostly clutter (the model was trained on these, so the rates are low by construction) |

**Consequences:** the locked test specificity and false-alert counts partly penalize correct detections.
DJI_0404 contributes most of the fold-0 val false-alert episodes (23 of 30). Before trusting false-alert
metrics, review DJI_0404, DJI_0408, and the other zero-human videos (DJI_0026/0054/0056/0127/0410).
If DJI_0408 is relabelled, keep the change out of every model-selection decision and record it, so the
test remains "locked".

### Other caveats

- **Eval crops depend on labels.** Medium-range eval positives are crops that follow the annotation,
  and negatives are centre crops (`vigil_medium_crops.evaluation_splits_cropped: true`). Positive inputs
  therefore always hold a magnified person near the centre. This framing does not exist in deployment and
  probably flatters both recall and specificity. Pair the result with a full-FOV evaluation
  (`thermal_mega_5fold_lepton`) before deciding anything for deployment.
- Event recall per fold is near 1.0 because most val sequences hold a single long event. Recall, longest
  miss, and the per-sequence table carry more information.
- `sequence_key` uses the original video name, so `DJI_xxxx` keys rely on DJI numbers being unique across
  WiSARD, which holds for the 41 IR sequences. Re-check this when adding datasets.
