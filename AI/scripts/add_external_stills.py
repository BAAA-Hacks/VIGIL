#!/usr/bin/env python3
"""Add an external YOLO-format still-image person dataset to an existing fold root.

Built for OpenThermalPose2 (close-range thermal people, MIT): its train split is added to
every fold's train list, and its val/test splits become a separate close-range evaluation
set, so the medium-range val/test benchmark stays unchanged.

Images are letterboxed to the Lepton's 160x120 grayscale like the rest of the dataset.
Pose keypoints are dropped; only the first five label columns (class + box) are kept.
Images are named `<name>-g<k>_<index>` so the epoch sampler sees `--groups` sources
instead of thousands of one-image "sequences", which would take over each epoch's
positive quota. More groups give the external data a larger share of each epoch.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import cv2
import yaml

try:
    from AI.scripts.dataset_utils import (
        YoloBox,
        absolute_path,
        box_is_normalized,
        format_yolo_box,
        load_dataset_config,
        split_images,
        write_json,
    )
    from AI.scripts.prepare_wisard import letterbox_grayscale, transform_box
except ModuleNotFoundError:
    from AI.scripts.dataset_utils import (  # type: ignore
        YoloBox,
        absolute_path,
        box_is_normalized,
        format_yolo_box,
        load_dataset_config,
        split_images,
        write_json,
    )
    from AI.scripts.prepare_wisard import letterbox_grayscale, transform_box  # type: ignore


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_folds", type=Path, help="Existing fold root, e.g. thermal_mega_5fold_lepton_medium_range")
    parser.add_argument("external_root", type=Path, help="Dataset root with {train,val,test}/{images,labels}")
    parser.add_argument("destination", type=Path, help="New fold root (must be empty)")
    parser.add_argument("--name", default="otp2", help="Short source name used in filenames")
    parser.add_argument("--train-images", type=int, default=2000, help="External train images to add (0 = all)")
    parser.add_argument("--eval-images", type=int, default=0, help="Cap per close-range eval split (0 = all)")
    parser.add_argument("--groups", type=int, default=5, help="Sampler source groups for the external images")
    parser.add_argument("--min-box-height", type=float, default=0.0, help="Keep only images with a box at least this tall")
    parser.add_argument("--keep-empty", action="store_true", help="Keep images with empty labels as negatives")
    parser.add_argument("--width", type=int, default=160)
    parser.add_argument("--height", type=int, default=120)
    parser.add_argument("--padding-value", type=int, default=114)
    parser.add_argument("--seed", type=int, default=26)
    return parser.parse_args()


def read_boxes(label: Path) -> list[YoloBox]:
    boxes: list[YoloBox] = []
    for line in label.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        # Pose rows carry keypoints after the box; only class 0 (person) exists here.
        box = YoloBox(0, *(float(value) for value in parts[1:5]))
        if box.width > 0 and box.height > 0:
            boxes.append(box)
    return boxes


def external_split(root: Path, split: str, keep_empty: bool = False) -> list[tuple[Path, list[YoloBox]]]:
    images = sorted(p for p in (root / split / "images").iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    pairs = []
    for image in images:
        label = root / split / "labels" / f"{image.stem}.txt"
        boxes = read_boxes(label) if label.is_file() else []
        if boxes or (keep_empty and label.is_file()):
            pairs.append((image, boxes))
    return pairs


def write_still(source: Path, boxes: list[YoloBox], image_out: Path, label_out: Path, args: argparse.Namespace) -> int:
    image = cv2.imread(str(source), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise SystemExit(f"Could not decode image: {source}")
    height, width = image.shape[:2]
    letterboxed, scale_x, scale_y, pad_left, pad_top = letterbox_grayscale(
        image, args.width, args.height, args.padding_value
    )
    transformed = [
        transform_box(box, width, height, args.width, args.height, scale_x, scale_y, pad_left, pad_top)
        for box in boxes
    ]
    transformed = [box for box in transformed if box_is_normalized(box)]
    image_out.parent.mkdir(parents=True, exist_ok=True)
    label_out.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(image_out), letterboxed):
        raise SystemExit(f"Could not write {image_out}")
    text = "\n".join(format_yolo_box(box) for box in transformed)
    label_out.write_text(text + ("\n" if text else ""), encoding="utf-8")
    return len(transformed)


def convert(
    pairs: list[tuple[Path, list[YoloBox]]], folder: Path, prefix: str, groups: int, args: argparse.Namespace
) -> tuple[list[Path], int]:
    outputs: list[Path] = []
    annotations = 0
    for index, (source, boxes) in enumerate(pairs):
        stem = f"{prefix}-g{index % groups}_{index:06d}"
        image_out = folder / "images" / f"{stem}.png"
        annotations += write_still(source, boxes, image_out, folder / "labels" / f"{stem}.txt", args)
        outputs.append(image_out.resolve())
    return outputs, annotations


def main() -> None:
    args = parse_args()
    if args.groups <= 0 or args.train_images < 0 or args.eval_images < 0:
        raise SystemExit("--groups must be positive; image counts cannot be negative")
    source_root = args.source_folds.expanduser().resolve()
    external_root = args.external_root.expanduser().resolve()
    destination = args.destination.expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"Destination must be empty: {destination}")
    fold_yamls = sorted(source_root.glob("fold_*/data.yaml"))
    if not fold_yamls:
        raise SystemExit(f"No fold_*/data.yaml under {source_root}")
    rng = random.Random(args.seed)

    def select(split: str, limit: int) -> list[tuple[Path, list[YoloBox]]]:
        split_dir = external_root / split / "images"
        if not split_dir.is_dir():
            return []
        pairs = [
            pair for pair in external_split(external_root, split, args.keep_empty)
            if not pair[1] or max(box.height for box in pair[1]) >= args.min_box_height
        ]
        rng.shuffle(pairs)
        return pairs[:limit] if limit else pairs

    external_dir = destination / "external" / args.name
    train_images, train_boxes = convert(select("train", args.train_images), external_dir / "train", args.name, args.groups, args)
    evaluation: dict[str, list[Path]] = {}
    for split in ("val", "test"):
        # Eval stills get their own prefix so they never share a source group with train.
        evaluation[split], _ = convert(
            select(split, args.eval_images), external_dir / split, f"{args.name}{split}", args.groups, args
        )

    fold_reports = []
    for fold_yaml in fold_yamls:
        config = load_dataset_config(fold_yaml)
        fold_dir = destination / fold_yaml.parent.name
        fold_dir.mkdir(parents=True)
        output_yaml = yaml.safe_load(fold_yaml.read_text(encoding="utf-8"))
        output_yaml["path"] = str(fold_dir)
        counts = {}
        for split in ("train", "val", "test"):
            paths = [absolute_path(path) for path in split_images(config, split)]
            if split == "train":
                paths += train_images
            (fold_dir / f"{split}.txt").write_text("\n".join(map(str, paths)) + "\n", encoding="utf-8")
            output_yaml[split] = str(fold_dir / f"{split}.txt")
            counts[split] = len(paths)
        output_yaml.setdefault("vigil_external_stills", []).append(
            {"name": args.name, "source": str(external_root), "train_images": len(train_images), "groups": args.groups}
        )
        (fold_dir / "data.yaml").write_text(yaml.safe_dump(output_yaml, sort_keys=False), encoding="utf-8")
        fold_reports.append({"fold": fold_dir.name, **counts})

    eval_dir = destination / f"{args.name}_closeup_eval"
    eval_dir.mkdir()
    eval_yaml = {"path": str(eval_dir), "train": None, "nc": 1, "names": {0: "person"}}
    for split, paths in evaluation.items():
        (eval_dir / f"{split}.txt").write_text("\n".join(map(str, paths)) + "\n", encoding="utf-8")
        eval_yaml[split] = str(eval_dir / f"{split}.txt")
    eval_yaml["train"] = eval_yaml["val"]
    (eval_dir / "data.yaml").write_text(yaml.safe_dump(eval_yaml, sort_keys=False), encoding="utf-8")

    report = {
        "destination": str(destination),
        "source_folds": str(source_root),
        "external": {
            "name": args.name,
            "root": str(external_root),
            "train_images": len(train_images),
            "train_annotations": train_boxes,
            "closeup_eval": {split: len(paths) for split, paths in evaluation.items()},
            "groups": args.groups,
            "min_box_height": args.min_box_height,
        },
        "folds": fold_reports,
    }
    # Downstream builders (prepare_temporal) read the medium-crop settings from here.
    source_report = yaml.safe_load((source_root / "preparation_report.json").read_text(encoding="utf-8"))
    report["medium_crop"] = source_report["medium_crop"]
    write_json(destination / "preparation_report.json", report)
    print(f"Added {len(train_images)} {args.name} train stills to {len(fold_reports)} folds: {destination}")
    print(f"Close-range eval set: {eval_dir / 'data.yaml'} {report['external']['closeup_eval']}")


if __name__ == "__main__":
    main()
