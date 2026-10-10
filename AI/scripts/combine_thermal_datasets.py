#!/usr/bin/env python3
"""Build grouped WiSARD+POP folds while keeping evaluation WiSARD-only."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wisard_folds", type=Path, help="Existing Lepton-format fold root")
    parser.add_argument("pop_train", type=Path, help="POP train directory")
    parser.add_argument("destination", type=Path, help="New combined fold root")
    parser.add_argument("--width", type=int, default=160)
    parser.add_argument("--height", type=int, default=120)
    parser.add_argument("--padding-value", type=int, default=114, choices=range(256), metavar="0-255")
    return parser.parse_args()


def coco_box(annotation: dict, width: int, height: int) -> YoloBox | None:
    x, y, box_width, box_height = map(float, annotation["bbox"])
    left = max(0.0, min(float(width), x))
    top = max(0.0, min(float(height), y))
    right = max(0.0, min(float(width), x + box_width))
    bottom = max(0.0, min(float(height), y + box_height))
    if right <= left or bottom <= top:
        return None
    return YoloBox(
        0,
        (left + right) / (2 * width),
        (top + bottom) / (2 * height),
        (right - left) / width,
        (bottom - top) / height,
    )


def prepare_pop(args: argparse.Namespace, destination: Path) -> tuple[list[Path], dict]:
    pop_root = args.pop_train.expanduser().resolve()
    image_root = pop_root / "JPEGImages"
    annotation_path = pop_root / "Annotations" / "train.json"
    if not image_root.is_dir() or not annotation_path.is_file():
        raise SystemExit(f"Expected POP JPEGImages and Annotations/train.json below {pop_root}")
    coco = json.loads(annotation_path.read_text(encoding="utf-8"))
    categories = {int(item["id"]): item["name"] for item in coco.get("categories", [])}
    if categories != {1: "person"}:
        raise SystemExit(f"Unexpected POP categories: {categories}")

    annotations: dict[int, list[dict]] = defaultdict(list)
    for annotation in coco["annotations"]:
        if int(annotation["category_id"]) != 1:
            raise SystemExit(f"Unexpected category in annotation {annotation.get('id')}")
        annotations[int(annotation["image_id"])].append(annotation)

    output_images = destination / "pop" / "images"
    output_labels = destination / "pop" / "labels"
    output_images.mkdir(parents=True)
    output_labels.mkdir(parents=True)
    prepared: list[Path] = []
    box_count = 0
    duplicate_boxes = 0
    invalid_boxes = 0
    scenes: set[str] = set()

    for record in sorted(coco["images"], key=lambda item: int(item["id"])):
        image_id = int(record["id"])
        source = image_root / record["file_name"]
        image = cv2.imread(str(source), cv2.IMREAD_UNCHANGED)
        if image is None:
            raise SystemExit(f"Could not decode POP image: {source}")
        source_height, source_width = image.shape[:2]
        if (source_width, source_height) != (int(record["width"]), int(record["height"])):
            raise SystemExit(f"COCO dimensions disagree with image: {source}")
        scene = source.stem.split("_", 1)[0]
        scenes.add(scene)
        simulated, scale_x, scale_y, pad_left, pad_top = letterbox_grayscale(
            image, args.width, args.height, args.padding_value
        )

        converted: list[YoloBox] = []
        seen: set[tuple[float, float, float, float]] = set()
        for annotation in annotations.get(image_id, []):
            box = coco_box(annotation, source_width, source_height)
            if box is None:
                invalid_boxes += 1
                continue
            key = (box.x_center, box.y_center, box.width, box.height)
            if key in seen:
                duplicate_boxes += 1
                continue
            seen.add(key)
            box = transform_box(
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
            if not box_is_normalized(box):
                raise SystemExit(f"Invalid transformed POP box: {source}")
            converted.append(box)
        if not converted:
            raise SystemExit(
                f"POP train image has no valid person annotation; refusing to treat it as positive: {source}"
            )

        name = f"pop_{scene}_{image_id:08d}"
        output_image = output_images / f"{name}.png"
        output_label = output_labels / f"{name}.txt"
        if not cv2.imwrite(str(output_image), simulated):
            raise SystemExit(f"Could not write image: {output_image}")
        output_label.write_text(
            "\n".join(format_yolo_box(box) for box in converted) + "\n", encoding="utf-8"
        )
        prepared.append(output_image.resolve())
        box_count += len(converted)

    return prepared, {
        "images": len(prepared),
        "positive_images": len(prepared),
        "negative_images": 0,
        "annotations": box_count,
        "scenes": sorted(scenes),
        "exact_duplicate_annotations_removed": duplicate_boxes,
        "invalid_annotations_removed": invalid_boxes,
    }


def main() -> None:
    args = parse_args()
    if args.width <= 0 or args.height <= 0:
        raise SystemExit("Output dimensions must be positive")
    wisard_root = args.wisard_folds.expanduser().resolve()
    destination = args.destination.expanduser().resolve()
    if not wisard_root.is_dir():
        raise SystemExit(f"WiSARD fold root does not exist: {wisard_root}")
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"Destination must be empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    fold_yamls = sorted(wisard_root.glob("fold_*/data.yaml"))
    if not fold_yamls:
        raise SystemExit(f"No fold_*/data.yaml files found in {wisard_root}")
    pop_images, pop_stats = prepare_pop(args, destination)
    fold_reports = []

    for source_yaml in fold_yamls:
        config = load_dataset_config(source_yaml)
        fold_dir = destination / source_yaml.parent.name
        fold_dir.mkdir()
        split_counts = {}
        for split in ("train", "val", "test"):
            paths = [absolute_path(path) for path in split_images(config, split)]
            wisard_count = len(paths)
            if split == "train":
                paths.extend(pop_images)
            list_path = fold_dir / f"{split}.txt"
            list_path.write_text("\n".join(map(str, paths)) + "\n", encoding="utf-8")
            split_counts[split] = {"total": len(paths), "wisard": wisard_count, "pop": len(paths) - wisard_count}

        output_yaml = {
            "path": str(fold_dir.resolve()),
            "train": str((fold_dir / "train.txt").resolve()),
            "val": str((fold_dir / "val.txt").resolve()),
            "test": str((fold_dir / "test.txt").resolve()),
            "nc": 1,
            "names": {0: "person"},
            "vigil_cross_validation": config.raw.get("vigil_cross_validation", {}),
            "vigil_preprocessing": config.raw.get("vigil_preprocessing", {}),
            "vigil_combination": {
                "training_sources": ["WiSARD", "POP/train"],
                "evaluation_source": "WiSARD only",
                "excluded": [
                    "POP/val",
                    "POP/test",
                    "People Thermal Images (unverified negatives; sampled folders contain people)",
                ],
            },
        }
        (fold_dir / "data.yaml").write_text(yaml.safe_dump(output_yaml, sort_keys=False), encoding="utf-8")
        fold_reports.append({"fold": source_yaml.parent.name, **split_counts})

    report = {
        "destination": str(destination),
        "wisard_fold_root": str(wisard_root),
        "pop_train_root": str(args.pop_train.expanduser().resolve()),
        "target_size": [args.width, args.height],
        "pop": pop_stats,
        "folds": fold_reports,
        "people_thermal_images_included": 0,
        "people_thermal_exclusion_reason": (
            "Only positives were found in the transferred folder sample; no files were assigned empty labels."
        ),
    }
    write_json(destination / "preparation_report.json", report)
    print(f"Prepared combined dataset: {destination}")
    print(f"POP: {pop_stats['images']} positive images, {pop_stats['annotations']} boxes, {len(pop_stats['scenes'])} scenes")
    for fold in fold_reports:
        print(
            f"{fold['fold']}: train={fold['train']['total']} "
            f"(WiSARD {fold['train']['wisard']} + POP {fold['train']['pop']}), "
            f"val={fold['val']['total']}, test={fold['test']['total']}"
        )


if __name__ == "__main__":
    main()
