#!/usr/bin/env python3
"""Convert a grouped-fold dataset to Lepton spatial detail without duplicating images."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import cv2
import yaml

try:
    from AI.scripts.dataset_utils import (
        absolute_path,
        box_is_normalized,
        format_yolo_box,
        label_path_for_image,
        load_dataset_config,
        read_yolo_labels,
        split_images,
        write_json,
    )
    from AI.scripts.prepare_wisard import letterbox_grayscale, transform_box
except ModuleNotFoundError:
    from AI.scripts.dataset_utils import (  # type: ignore
        absolute_path,
        box_is_normalized,
        format_yolo_box,
        label_path_for_image,
        load_dataset_config,
        read_yolo_labels,
        split_images,
        write_json,
    )
    from AI.scripts.prepare_wisard import letterbox_grayscale, transform_box  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fold_root", type=Path, help="Root created by build_folds.py")
    parser.add_argument("destination", type=Path, help="New Lepton-fold dataset root")
    parser.add_argument("--width", type=int, default=160)
    parser.add_argument("--height", type=int, default=120)
    parser.add_argument("--padding-value", type=int, default=114, choices=range(256), metavar="0-255")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.width <= 0 or args.height <= 0:
        raise SystemExit("Output dimensions must be positive")
    fold_root = args.fold_root.expanduser().resolve()
    destination = args.destination.expanduser().resolve()
    if not fold_root.is_dir():
        raise SystemExit(f"Fold root does not exist: {fold_root}")
    if destination == fold_root or fold_root in destination.parents:
        raise SystemExit("Destination cannot be inside the source fold directory")
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"Destination must be empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    fold_yamls = sorted(fold_root.glob("fold_*/data.yaml"))
    if not fold_yamls:
        raise SystemExit(f"No fold_*/data.yaml files found in {fold_root}")
    fold_configs = [load_dataset_config(path) for path in fold_yamls]
    unique_images: dict[Path, None] = {}
    for config in fold_configs:
        for split in ("train", "val", "test"):
            for image in split_images(config, split):
                unique_images[absolute_path(image)] = None

    image_root = destination / "images"
    label_root = destination / "labels"
    image_root.mkdir(parents=True, exist_ok=True)
    label_root.mkdir(parents=True, exist_ok=True)
    mapping: dict[Path, Path] = {}
    total_boxes = 0
    empty_images = 0

    for source_image in sorted(unique_images):
        image = cv2.imread(str(source_image), cv2.IMREAD_UNCHANGED)
        if image is None:
            raise SystemExit(f"Could not decode image: {source_image}")
        source_height, source_width = image.shape[:2]
        simulated, scale_x, scale_y, pad_left, pad_top = letterbox_grayscale(
            image, args.width, args.height, args.padding_value
        )
        label_path = label_path_for_image(source_image)
        boxes, errors = read_yolo_labels(label_path)
        if not label_path.exists():
            raise SystemExit(f"Missing label file: {label_path}")
        if errors:
            raise SystemExit("\n".join(errors))
        if not boxes:
            empty_images += 1

        transformed = []
        for box in boxes:
            if not box_is_normalized(box):
                raise SystemExit(f"Invalid normalized box in {label_path}: {box}")
            converted = transform_box(
                box,
                source_width,
                source_height,
                args.width,
                args.height,
                scale_x,
                scale_y,
                pad_left,
                pad_top,
            )
            if not box_is_normalized(converted):
                raise SystemExit(f"Transformed box is invalid for {source_image}: {converted}")
            transformed.append(converted)

        digest = hashlib.sha1(str(source_image).encode("utf-8")).hexdigest()[:16]
        output_image = image_root / f"{digest}_{source_image.stem}.png"
        output_label = label_root / output_image.with_suffix(".txt").name
        if not cv2.imwrite(str(output_image), simulated):
            raise SystemExit(f"Could not write image: {output_image}")
        label_text = "\n".join(format_yolo_box(box) for box in transformed)
        output_label.write_text(label_text + ("\n" if label_text else ""), encoding="utf-8")
        mapping[source_image] = output_image.resolve()
        total_boxes += len(transformed)

    fold_summaries = []
    for source_yaml, config in zip(fold_yamls, fold_configs, strict=True):
        fold_name = source_yaml.parent.name
        fold_dir = destination / fold_name
        fold_dir.mkdir(parents=True, exist_ok=True)
        split_counts = {}
        for split in ("train", "val", "test"):
            source_paths = split_images(config, split)
            if not source_paths:
                continue
            converted_paths = [mapping[absolute_path(path)] for path in source_paths]
            list_path = fold_dir / f"{split}.txt"
            list_path.write_text("\n".join(map(str, converted_paths)) + "\n", encoding="utf-8")
            split_counts[split] = len(converted_paths)
        output_yaml = {
            "path": str(fold_dir.resolve()),
            "train": str((fold_dir / "train.txt").resolve()),
            "val": str((fold_dir / "val.txt").resolve()),
            "nc": len(config.names),
            "names": config.names,
            "vigil_cross_validation": config.raw.get("vigil_cross_validation", {}),
            "vigil_preprocessing": {
                "spatial_detail": [args.width, args.height],
                "grayscale": True,
                "aspect_ratio": "letterbox",
                "padding_value": args.padding_value,
                "limitations": (
                    "Spatial-detail approximation only; does not model Lepton thermal response, "
                    "noise, optics, radiometry, or bit depth."
                ),
            },
        }
        if "test" in split_counts:
            output_yaml["test"] = str((fold_dir / "test.txt").resolve())
        (fold_dir / "data.yaml").write_text(
            yaml.safe_dump(output_yaml, sort_keys=False), encoding="utf-8"
        )
        fold_summaries.append({"fold": fold_name, **split_counts})

    report = {
        "source_fold_root": str(fold_root),
        "destination": str(destination),
        "unique_images": len(unique_images),
        "empty_negative_images": empty_images,
        "annotations": total_boxes,
        "target_size": [args.width, args.height],
        "folds": fold_summaries,
    }
    write_json(destination / "preparation_report.json", report)
    print(f"Prepared grouped Lepton dataset: {destination}")
    print(f"  unique images: {len(unique_images)}")
    print(f"  empty negatives: {empty_images}")
    print(f"  annotations: {total_boxes}")


if __name__ == "__main__":
    main()
