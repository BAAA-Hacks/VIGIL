#!/usr/bin/env python3
"""Add training-only medium-FOV crops from original WiSARD and POP images."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import cv2
import yaml

try:
    from AI.scripts.combine_thermal_datasets import coco_box
    from AI.scripts.dataset_utils import (
        YoloBox,
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
    from AI.scripts.combine_thermal_datasets import coco_box  # type: ignore
    from AI.scripts.dataset_utils import (  # type: ignore
        YoloBox,
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
    parser.add_argument("combined_folds", type=Path, help="Existing combined Lepton fold root")
    parser.add_argument("wisard_source_folds", type=Path, help="Original-resolution WiSARD fold root")
    parser.add_argument("pop_train", type=Path, help="POP train directory")
    parser.add_argument("destination", type=Path, help="New fold root with training-only crops")
    parser.add_argument("--crop-scale", type=float, default=0.5, help="Base crop fraction of the source FOV")
    parser.add_argument("--box-margin", type=float, default=0.15, help="Fractional margin around the union of labels")
    parser.add_argument("--min-visibility", type=float, default=0.5)
    parser.add_argument("--width", type=int, default=160)
    parser.add_argument("--height", type=int, default=120)
    parser.add_argument("--padding-value", type=int, default=114, choices=range(256), metavar="0-255")
    return parser.parse_args()


def medium_crop_bounds(
    source_width: int,
    source_height: int,
    boxes: list[YoloBox],
    crop_scale: float,
    target_aspect: float,
    box_margin: float,
) -> tuple[int, int, int, int]:
    """Return a deterministic target-aspect crop containing every supplied box."""
    if source_width <= 0 or source_height <= 0 or not boxes:
        raise ValueError("A positive-size image and at least one box are required")
    if not 0.0 < crop_scale <= 1.0 or target_aspect <= 0.0 or box_margin < 0.0:
        raise ValueError("Invalid crop geometry settings")

    left = min((box.x_center - box.width / 2) * source_width for box in boxes)
    top = min((box.y_center - box.height / 2) * source_height for box in boxes)
    right = max((box.x_center + box.width / 2) * source_width for box in boxes)
    bottom = max((box.y_center + box.height / 2) * source_height for box in boxes)
    union_width = right - left
    union_height = bottom - top

    crop_width = source_width * crop_scale
    crop_height = source_height * crop_scale
    if crop_width / crop_height < target_aspect:
        crop_width = crop_height * target_aspect
    else:
        crop_height = crop_width / target_aspect

    required_width = union_width * (1.0 + 2.0 * box_margin)
    required_height = union_height * (1.0 + 2.0 * box_margin)
    crop_width = max(crop_width, required_width, required_height * target_aspect)
    crop_height = crop_width / target_aspect
    if crop_height > source_height:
        crop_height = float(source_height)
        crop_width = crop_height * target_aspect
    if crop_width > source_width:
        crop_width = float(source_width)
        crop_height = crop_width / target_aspect

    center_x = (left + right) / 2.0
    center_y = (top + bottom) / 2.0
    crop_left = min(max(0.0, center_x - crop_width / 2.0), source_width - crop_width)
    crop_top = min(max(0.0, center_y - crop_height / 2.0), source_height - crop_height)
    crop_right = crop_left + crop_width
    crop_bottom = crop_top + crop_height

    integer_left = max(0, int(round(crop_left)))
    integer_top = max(0, int(round(crop_top)))
    integer_right = min(source_width, max(integer_left + 1, int(round(crop_right))))
    integer_bottom = min(source_height, max(integer_top + 1, int(round(crop_bottom))))
    return integer_left, integer_top, integer_right, integer_bottom


def crop_boxes(
    boxes: list[YoloBox],
    source_width: int,
    source_height: int,
    bounds: tuple[int, int, int, int],
    min_visibility: float,
) -> list[YoloBox]:
    """Clip normalized source boxes into crop-relative normalized coordinates."""
    if not 0.0 <= min_visibility <= 1.0:
        raise ValueError("min_visibility must be between zero and one")
    crop_left, crop_top, crop_right, crop_bottom = bounds
    crop_width = crop_right - crop_left
    crop_height = crop_bottom - crop_top
    converted: list[YoloBox] = []
    for box in boxes:
        left = (box.x_center - box.width / 2) * source_width
        top = (box.y_center - box.height / 2) * source_height
        right = (box.x_center + box.width / 2) * source_width
        bottom = (box.y_center + box.height / 2) * source_height
        original_area = max(0.0, right - left) * max(0.0, bottom - top)
        clipped_left = max(float(crop_left), left)
        clipped_top = max(float(crop_top), top)
        clipped_right = min(float(crop_right), right)
        clipped_bottom = min(float(crop_bottom), bottom)
        visible_area = max(0.0, clipped_right - clipped_left) * max(0.0, clipped_bottom - clipped_top)
        if not original_area or visible_area / original_area < min_visibility:
            continue
        converted.append(
            YoloBox(
                box.class_id,
                ((clipped_left + clipped_right) / 2.0 - crop_left) / crop_width,
                ((clipped_top + clipped_bottom) / 2.0 - crop_top) / crop_height,
                (clipped_right - clipped_left) / crop_width,
                (clipped_bottom - clipped_top) / crop_height,
            )
        )
    return converted


def write_medium_crop(
    source: Path,
    boxes: list[YoloBox],
    output_image: Path,
    output_label: Path,
    args: argparse.Namespace,
) -> int:
    image = cv2.imread(str(source), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise SystemExit(f"Could not decode image: {source}")
    source_height, source_width = image.shape[:2]
    bounds = medium_crop_bounds(
        source_width,
        source_height,
        boxes,
        args.crop_scale,
        args.width / args.height,
        args.box_margin,
    )
    cropped_boxes = crop_boxes(boxes, source_width, source_height, bounds, args.min_visibility)
    if not cropped_boxes:
        raise SystemExit(f"Medium crop lost every annotation: {source}")
    left, top, right, bottom = bounds
    cropped = image[top:bottom, left:right]
    simulated, scale_x, scale_y, pad_left, pad_top = letterbox_grayscale(
        cropped, args.width, args.height, args.padding_value
    )
    crop_height, crop_width = cropped.shape[:2]
    transformed = [
        transform_box(
            box,
            crop_width,
            crop_height,
            args.width,
            args.height,
            scale_x,
            scale_y,
            pad_left,
            pad_top,
        )
        for box in cropped_boxes
    ]
    if not all(box_is_normalized(box) for box in transformed):
        raise SystemExit(f"Invalid transformed medium-crop box: {source}")
    output_image.parent.mkdir(parents=True, exist_ok=True)
    output_label.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_image), simulated):
        raise SystemExit(f"Could not write image: {output_image}")
    output_label.write_text(
        "\n".join(format_yolo_box(box) for box in transformed) + "\n", encoding="utf-8"
    )
    return len(transformed)


def prepare_wisard_crops(
    source_fold_yamls: list[Path], destination: Path, args: argparse.Namespace
) -> tuple[dict[Path, Path], dict]:
    unique_images: dict[Path, list[YoloBox]] = {}
    for yaml_path in source_fold_yamls:
        config = load_dataset_config(yaml_path)
        for image in split_images(config, "train"):
            image = absolute_path(image)
            if image in unique_images:
                continue
            boxes, errors = read_yolo_labels(label_path_for_image(image))
            if errors:
                raise SystemExit("\n".join(errors))
            if boxes:
                unique_images[image] = boxes

    mapping: dict[Path, Path] = {}
    annotations = 0
    for source, boxes in sorted(unique_images.items()):
        digest = hashlib.sha1(str(source).encode("utf-8")).hexdigest()[:16]
        # Keep the digest at the beginning so source_frame_id() strips it and
        # assigns the crop to the same video group as its parent frame.
        name = f"{digest}_{source.stem}"
        output_image = destination / "medium_crops" / "wisard" / "images" / f"{name}.png"
        output_label = destination / "medium_crops" / "wisard" / "labels" / f"{name}.txt"
        annotations += write_medium_crop(source, boxes, output_image, output_label, args)
        mapping[source] = output_image.resolve()
    return mapping, {"images": len(mapping), "annotations": annotations}


def prepare_pop_crops(pop_train: Path, destination: Path, args: argparse.Namespace) -> tuple[list[Path], dict]:
    pop_root = pop_train.expanduser().resolve()
    image_root = pop_root / "JPEGImages"
    annotation_path = pop_root / "Annotations" / "train.json"
    if not image_root.is_dir() or not annotation_path.is_file():
        raise SystemExit(f"Expected POP JPEGImages and Annotations/train.json below {pop_root}")
    coco = json.loads(annotation_path.read_text(encoding="utf-8"))
    annotations_by_image: dict[int, list[dict]] = defaultdict(list)
    for annotation in coco["annotations"]:
        if int(annotation["category_id"]) != 1:
            raise SystemExit(f"Unexpected POP category in annotation {annotation.get('id')}")
        annotations_by_image[int(annotation["image_id"])].append(annotation)

    prepared: list[Path] = []
    box_count = 0
    for record in sorted(coco["images"], key=lambda item: int(item["id"])):
        image_id = int(record["id"])
        source = image_root / record["file_name"]
        seen: set[tuple[float, float, float, float]] = set()
        boxes: list[YoloBox] = []
        for annotation in annotations_by_image.get(image_id, []):
            box = coco_box(annotation, int(record["width"]), int(record["height"]))
            if box is None:
                continue
            key = (box.x_center, box.y_center, box.width, box.height)
            if key not in seen:
                seen.add(key)
                boxes.append(box)
        if not boxes:
            raise SystemExit(f"POP training image has no valid person annotation: {source}")
        scene = source.stem.split("_", 1)[0]
        # Match the source grouping used by the full-frame POP preparation.
        name = f"pop_{scene}_{image_id:08d}"
        output_image = destination / "medium_crops" / "pop" / "images" / f"{name}.png"
        output_label = destination / "medium_crops" / "pop" / "labels" / f"{name}.txt"
        box_count += write_medium_crop(source, boxes, output_image, output_label, args)
        prepared.append(output_image.resolve())
    return prepared, {"images": len(prepared), "annotations": box_count}


def main() -> None:
    args = parse_args()
    if args.width <= 0 or args.height <= 0:
        raise SystemExit("--width and --height must be positive")
    if not 0.0 < args.crop_scale <= 1.0:
        raise SystemExit("--crop-scale must be in (0, 1]")
    if args.box_margin < 0.0 or not 0.0 <= args.min_visibility <= 1.0:
        raise SystemExit("Invalid box margin or visibility threshold")

    combined_root = args.combined_folds.expanduser().resolve()
    source_root = args.wisard_source_folds.expanduser().resolve()
    destination = args.destination.expanduser().resolve()
    combined_yamls = sorted(combined_root.glob("fold_*/data.yaml"))
    source_yamls = sorted(source_root.glob("fold_*/data.yaml"))
    if not combined_yamls or [path.parent.name for path in combined_yamls] != [
        path.parent.name for path in source_yamls
    ]:
        raise SystemExit("Combined and original WiSARD fold roots must contain matching folds")
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"Destination must be empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    wisard_mapping, wisard_stats = prepare_wisard_crops(source_yamls, destination, args)
    pop_crops, pop_stats = prepare_pop_crops(args.pop_train, destination, args)
    fold_reports = []
    for combined_yaml, source_yaml in zip(combined_yamls, source_yamls, strict=True):
        combined_config = load_dataset_config(combined_yaml)
        source_config = load_dataset_config(source_yaml)
        fold_dir = destination / combined_yaml.parent.name
        fold_dir.mkdir()
        base_train = [absolute_path(path) for path in split_images(combined_config, "train")]
        wisard_crops = [
            wisard_mapping[absolute_path(path)]
            for path in split_images(source_config, "train")
            if absolute_path(path) in wisard_mapping
        ]
        train = base_train + wisard_crops + pop_crops
        splits = {
            "train": train,
            "val": [absolute_path(path) for path in split_images(combined_config, "val")],
            "test": [absolute_path(path) for path in split_images(combined_config, "test")],
        }
        for split, paths in splits.items():
            (fold_dir / f"{split}.txt").write_text(
                "\n".join(map(str, paths)) + "\n", encoding="utf-8"
            )
        output_yaml = dict(combined_config.raw)
        output_yaml["path"] = str(fold_dir.resolve())
        for split in splits:
            output_yaml[split] = str((fold_dir / f"{split}.txt").resolve())
        output_yaml["vigil_medium_crops"] = {
            "training_only": True,
            "source_resolution": True,
            "crop_scale": args.crop_scale,
            "box_margin": args.box_margin,
            "minimum_visibility": args.min_visibility,
            "target_size": [args.width, args.height],
        }
        (fold_dir / "data.yaml").write_text(
            yaml.safe_dump(output_yaml, sort_keys=False), encoding="utf-8"
        )
        fold_reports.append(
            {
                "fold": fold_dir.name,
                "train": len(train),
                "base_train": len(base_train),
                "wisard_medium_crops": len(wisard_crops),
                "pop_medium_crops": len(pop_crops),
                "val": len(splits["val"]),
                "test": len(splits["test"]),
            }
        )

    report = {
        "destination": str(destination),
        "combined_fold_root": str(combined_root),
        "wisard_source_fold_root": str(source_root),
        "pop_train_root": str(args.pop_train.expanduser().resolve()),
        "medium_crop": {
            "training_only": True,
            "crop_scale": args.crop_scale,
            "box_margin": args.box_margin,
            "minimum_visibility": args.min_visibility,
            "target_size": [args.width, args.height],
        },
        "unique_crops": {"wisard": wisard_stats, "pop": pop_stats},
        "folds": fold_reports,
    }
    write_json(destination / "preparation_report.json", report)
    print(f"Prepared medium-crop dataset: {destination}")
    print(f"Unique crops: WiSARD {wisard_stats['images']}, POP {pop_stats['images']}")
    for fold in fold_reports:
        print(
            f"{fold['fold']}: train={fold['train']} "
            f"(base {fold['base_train']} + WiSARD crops {fold['wisard_medium_crops']} "
            f"+ POP crops {fold['pop_medium_crops']}), val={fold['val']}, test={fold['test']}"
        )


if __name__ == "__main__":
    main()
