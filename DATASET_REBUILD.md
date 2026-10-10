# Rebuild the combined thermal dataset

Requirements: clone this repository, install its Python dependencies, extract all WiSARD source-video folders under one directory, and extract POP so that `train/JPEGImages` and `train/Annotations/train.json` exist. Do not add People Thermal images as negatives unless a genuinely person-free subset has been verified.

From the repository root, replace `/data/wisard` and `/data/POP/train` below:

```bash
python -m AI.scripts.import_wisard_raw /data/wisard AI/datasets/wisard_full_ir_manifest --modality IR

python -m AI.scripts.build_folds \
  AI/datasets/wisard_full_ir_manifest/data.yaml \
  AI/datasets/wisard_full_ir_5fold \
  --folds 5 --negative-fraction 0 --seed 26 \
  --holdout-sequences-file AI/config/wisard_full_ir_locked_test.txt

python -m AI.scripts.prepare_cv_lepton \
  AI/datasets/wisard_full_ir_5fold \
  AI/datasets/wisard_full_ir_5fold_lepton

python -m AI.scripts.combine_thermal_datasets \
  AI/datasets/wisard_full_ir_5fold_lepton \
  /data/POP/train \
  AI/datasets/thermal_mega_5fold_lepton
```

Expected fold-0 counts are 28,234 train, 5,706 validation, and 1,486 locked-test images. Confirm them with:

```bash
python -m AI.scripts.inspect_dataset \
  AI/datasets/thermal_mega_5fold_lepton/fold_0/data.yaml \
  --output AI/datasets/thermal_mega_5fold_lepton/fold_0/inspection
```

The epoch sampler is applied dynamically by `train.py --epoch-fraction 0.20`; it is not baked into the dataset.
