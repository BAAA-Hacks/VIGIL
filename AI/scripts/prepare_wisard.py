#!/usr/bin/env python3
"""Create a non-destructive 160x120 spatial-detail simulation of WiSARD_IR."""

from __future__ import annotations

import argparse
import shutil
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import yaml

try:
    from AI.scripts.dataset_utils import (
        YoloBox,
        box_is_normalized,
        common_image_root,
        find_data_yaml,
        format_yolo_box,
        label_path_for_image,
        load_dataset_config,
        read_yolo_labels,
        split_images,
        write_json,
    )
except ModuleNotFoundError:  # Allows `python scripts/prepare_wisard.py`.
    from AI.scripts.dataset_utils import (  # type: ignore
        YoloBox,
        box_is_normalized,
        common_image_root,
        find_data_yaml,
        format_yolo_box,
        label_path_for_image,
        load_dataset_config,
        read_yolo_labels,
        split_images,
        write_json,
    )


SPLIT_DIRECTORIES = {"train": "train", "val": "valid", "test": "test"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Source dataset root or data.yaml")
    parser.add_argument("destination", type=Path, help="New output dataset directory")
    parser.add_argument("--width", type=int, default=160, help="Simulated sensor width")
    parser.add_argument("--height", type=int, default=120, help="Simulated sensor height")
    parser.add_argument(
        "--upscale-to-original",
        action="store_true",
        help="Upscale the 160x120 result back to each source image's dimensions",
    )
    parser.add_argument(
        "--padding-value",
        type=int,
        default=114,
        choices=range(256),
        metavar="0-255",
        help="Grayscale letterbox padding value",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow writing into an existing empty destination (never deletes files)",
    )
    return parser.parse_args()


def letterbox_grayscale(
    image: np.ndarray, width: int, height: int, padding_value: int
) -> tuple[np.ndarray, float, float, int, int]:
    if image.ndim == 3:
        if image.shape[2] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        else:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    elif image.ndim != 2:
        raise ValueError(f"Unsupported image shape: {image.shape}")

    source_height, source_width = image.shape[:2]
    scale = min(width / source_width, height / source_height)
    resized_width = max(1, min(width, round(source_width * scale)))
    resized_height = max(1, min(height, round(source_height * scale)))
    resized = cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_AREA)
    pad_left = (width - resized_width) // 2
    pad_top = (height - resized_height) // 2
    canvas = np.full((height, width), padding_value, dtype=resized.dtype)
    canvas[pad_top : pad_top + resized_height, pad_left : pad_left + resized_width] = resized
    scale_x = resized_width / source_width
    scale_y = resized_height / source_height
    return canvas, scale_x, scale_y, pad_left, pad_top


def transform_box(
    box: YoloBox,
    source_width: int,
    source_height: int,
    target_width: int,
    target_height: int,
    scale_x: float,
    scale_y: float,
    pad_left: int,
    pad_top: int,
) -> YoloBox:
    return YoloBox(
        class_id=box.class_id,
        x_center=(box.x_center * source_width * scale_x + pad_left) / target_width,
        y_center=(box.y_center * source_height * scale_y + pad_top) / target_height,
        width=box.width * source_width * scale_x / target_width,
        height=box.height * source_height * scale_y / target_height,
    )


def prepare_split(
    split: str,
    images: list[Path],
    destination: Path,
    target_width: int,
    target_height: int,
    padding_value: int,
    upscale_to_original: bool,
) -> dict:
    split_dir = SPLIT_DIRECTORIES[split]
    image_root = common_image_root(images)
    stats: Counter = Counter()
    errors: list[str] = []

    for image_path in images:
        relative = image_path.relative_to(image_root)
        output_image = destination / split_dir / "images" / relative.with_suffix(".png")
        output_label = destination / split_dir / "labels" / relative.with_suffix(".txt")
        output_image.parent.mkdir(parents=True, exist_ok=True)
        output_label.parent.mkdir(parents=True, exist_ok=True)

        image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        if image is None:
            errors.append(f"Could not decode image: {image_path}")
            stats["decode_errors"] += 1
            continue
        source_height, source_width = image.shape[:2]
        simulated, scale_x, scale_y, pad_left, pad_top = letterbox_grayscale(
            image, target_width, target_height, padding_value
        )
        if upscale_to_original:
            simulated = cv2.resize(
                simulated, (source_width, source_height), interpolation=cv2.INTER_LINEAR
            )

        label_path = label_path_for_image(image_path)
        boxes, label_errors = read_yolo_labels(label_path)
        if not label_path.exists():
            stats["missing_labels"] += 1
        elif not boxes and not label_errors:
            stats["empty_labels"] += 1
        if label_errors:
            errors.extend(label_errors)
            stats["invalid_label_lines"] += len(label_errors)

        transformed: list[YoloBox] = []
        for box in boxes:
            if not box_is_normalized(box):
                errors.append(f"Invalid normalized box in {label_path}: {box}")
                stats["invalid_boxes"] += 1
                continue
            transformed_box = transform_box(
                box,
                source_width,
                source_height,
                target_width,
                target_height,
                scale_x,
                scale_y,
                pad_left,
                pad_top,
            )
            if not box_is_normalized(transformed_box):
                errors.append(f"Transformed box fell outside the output image: {label_path}")
                stats["invalid_transformed_boxes"] += 1
                continue
            transformed.append(transformed_box)

        if not cv2.imwrite(str(output_image), simulated):
            errors.append(f"Could not write image: {output_image}")
            stats["write_errors"] += 1
            continue
        label_text = "\n".join(format_yolo_box(box) for box in transformed)
        output_label.write_text(label_text + ("\n" if label_text else ""), encoding="utf-8")
        stats["images"] += 1
        stats["annotations"] += len(transformed)

    return {"counts": dict(stats), "errors": errors}


def main() -> None:
    args = parse_args()
    if args.width <= 0 or args.height <= 0:
        raise SystemExit("--width and --height must be positive")

    yaml_path = find_data_yaml(args.source)
    source_config = load_dataset_config(yaml_path)
    destination = args.destination.expanduser().resolve()
    source_tree = yaml_path.parent.resolve()
    if destination == source_tree or source_tree in destination.parents:
        raise SystemExit("Destination must not be the source directory or inside it")
    if destination.exists() and any(destination.iterdir()) and not args.overwrite:
        raise SystemExit(
            f"Destination is not empty: {destination}. Choose a new path or pass --overwrite."
        )
    destination.mkdir(parents=True, exist_ok=True)

    split_results: dict[str, dict] = {}
    output_yaml = dict(source_config.raw)
    output_yaml.pop("download", None)
    output_yaml["path"] = "."
    for split, directory in SPLIT_DIRECTORIES.items():
        images = split_images(source_config, split)
        if not images:
            if split == "train":
                raise SystemExit("Training split is missing or empty")
            output_yaml.pop(split, None)
            continue
        split_results[split] = prepare_split(
            split,
            images,
            destination,
            args.width,
            args.height,
            args.padding_value,
            args.upscale_to_original,
        )
        output_yaml[split] = f"{directory}/images"

    output_yaml["vigil_preprocessing"] = {
        "source_yaml": str(yaml_path),
        "spatial_detail": [args.width, args.height],
        "grayscale": True,
        "aspect_ratio": "letterbox",
        "padding_value": args.padding_value,
        "upscaled_to_original_dimensions": args.upscale_to_original,
        "limitations": (
            "Spatial-detail approximation only; does not model Lepton thermal response, "
            "noise, optics, radiometry, or bit depth."
        ),
    }
    (destination / "data.yaml").write_text(
        yaml.safe_dump(output_yaml, sort_keys=False), encoding="utf-8"
    )
    shutil.copy2(yaml_path, destination / "source_data.yaml")

    report = {
        "source": str(source_config.root.resolve()),
        "destination": str(destination),
        "target_size": [args.width, args.height],
        "upscaled_to_original": args.upscale_to_original,
        "splits": split_results,
    }
    write_json(destination / "preparation_report.json", report)
    total_errors = sum(len(result["errors"]) for result in split_results.values())
    print(f"Prepared dataset: {destination}")
    for split, result in split_results.items():
        print(f"  {split}: {result['counts']}")
    if total_errors:
        print(f"WARNING: {total_errors} issues were recorded in preparation_report.json")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
