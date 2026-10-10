#!/usr/bin/env python3
"""Build sequence-grouped cross-validation folds and safe background negatives."""

from __future__ import annotations

import argparse
import hashlib
import random
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import yaml

try:
    from AI.scripts.dataset_utils import (
        YoloBox,
        box_is_normalized,
        find_data_yaml,
        label_path_for_image,
        load_dataset_config,
        read_yolo_labels,
        source_frame_id,
        split_images,
        write_json,
    )
except ModuleNotFoundError:
    from AI.scripts.dataset_utils import (  # type: ignore
        YoloBox,
        box_is_normalized,
        find_data_yaml,
        label_path_for_image,
        load_dataset_config,
        read_yolo_labels,
        source_frame_id,
        split_images,
        write_json,
    )


@dataclass
class ImageRecord:
    path: Path
    sequence: str
    width: int
    height: int
    boxes: list[YoloBox]


@dataclass
class SequenceStats:
    name: str
    images: list[ImageRecord] = field(default_factory=list)
    annotations: int = 0
    tiny_annotations: int = 0

    @property
    def image_count(self) -> int:
        return len(self.images)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Source dataset root or data.yaml")
    parser.add_argument("destination", type=Path, help="New fold metadata/negative directory")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument(
        "--negative-fraction",
        type=float,
        default=0.25,
        help="Probability of attempting one negative crop per source image",
    )
    parser.add_argument("--crop-scale-min", type=float, default=0.40)
    parser.add_argument("--crop-scale-max", type=float, default=0.65)
    parser.add_argument("--negative-width", type=int, default=640)
    parser.add_argument("--negative-height", type=int, default=480)
    parser.add_argument("--box-margin", type=int, default=8)
    parser.add_argument("--crop-attempts", type=int, default=50)
    parser.add_argument("--seed", type=int, default=26)
    return parser.parse_args()


def load_records(config, target_width: int = 160, target_height: int = 120) -> dict[str, SequenceStats]:
    unique_images: dict[Path, None] = {}
    for split in ("train", "val", "test"):
        for image in split_images(config, split):
            unique_images[image] = None
    if not unique_images:
        raise SystemExit("No images were found in the source dataset")

    sequences: dict[str, SequenceStats] = {}
    issues: list[str] = []
    for image_path in sorted(unique_images):
        image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        if image is None:
            issues.append(f"Unreadable image: {image_path}")
            continue
        height, width = image.shape[:2]
        label_path = label_path_for_image(image_path)
        boxes, errors = read_yolo_labels(label_path)
        issues.extend(errors)
        if not label_path.exists():
            issues.append(f"Missing label file: {label_path}")
        invalid = [box for box in boxes if not box_is_normalized(box)]
        if invalid:
            issues.append(f"Invalid boxes in {label_path}: {invalid}")
            continue
        unknown = [box for box in boxes if box.class_id not in config.names]
        if unknown:
            issues.append(f"Unknown class IDs in {label_path}: {unknown}")
            continue

        sequence, _ = source_frame_id(image_path)
        stats = sequences.setdefault(sequence, SequenceStats(sequence))
        stats.images.append(ImageRecord(image_path, sequence, width, height, boxes))
        stats.annotations += len(boxes)
        scale = min(target_width / width, target_height / height)
        stats.tiny_annotations += sum(
            box.width * width * scale < 4.0 or box.height * height * scale < 4.0
            for box in boxes
        )

    if issues:
        preview = "\n".join(issues[:20])
        raise SystemExit(
            f"Refusing to build folds because {len(issues)} source issues were found:\n{preview}"
        )
    return sequences


def assign_folds(sequences: dict[str, SequenceStats], fold_count: int, seed: int) -> dict[str, int]:
    if len(sequences) < fold_count:
        raise SystemExit(f"Need at least {fold_count} source sequences; found {len(sequences)}")
    rng = random.Random(seed)
    ordered = list(sequences.values())
    rng.shuffle(ordered)
    ordered.sort(key=lambda item: (item.image_count, item.annotations), reverse=True)

    totals = {
        "images": sum(item.image_count for item in ordered),
        "annotations": sum(item.annotations for item in ordered),
        "tiny": sum(item.tiny_annotations for item in ordered),
        "sequences": len(ordered),
    }
    targets = {key: max(value / fold_count, 1.0) for key, value in totals.items()}
    fold_totals = [defaultdict(float) for _ in range(fold_count)]
    assignments: dict[str, int] = {}

    def projected_score(candidate: int, item: SequenceStats) -> float:
        score = 0.0
        for fold_index, current in enumerate(fold_totals):
            additions = {
                "images": item.image_count,
                "annotations": item.annotations,
                "tiny": item.tiny_annotations,
                "sequences": 1,
            } if fold_index == candidate else {}
            weights = {"images": 1.0, "annotations": 0.45, "tiny": 0.65, "sequences": 0.05}
            for metric, target in targets.items():
                value = current[metric] + additions.get(metric, 0)
                score += weights[metric] * ((value - target) / target) ** 2
        return score

    for item in ordered:
        choices = [(projected_score(index, item), fold_totals[index]["images"], index) for index in range(fold_count)]
        _, _, selected = min(choices)
        assignments[item.name] = selected
        fold_totals[selected]["images"] += item.image_count
        fold_totals[selected]["annotations"] += item.annotations
        fold_totals[selected]["tiny"] += item.tiny_annotations
        fold_totals[selected]["sequences"] += 1
    return assignments


def pixel_boxes(record: ImageRecord, margin: int) -> list[tuple[int, int, int, int]]:
    boxes = []
    for box in record.boxes:
        left = int((box.x_center - box.width / 2) * record.width) - margin
        top = int((box.y_center - box.height / 2) * record.height) - margin
        right = int((box.x_center + box.width / 2) * record.width) + margin
        bottom = int((box.y_center + box.height / 2) * record.height) + margin
        boxes.append((max(0, left), max(0, top), min(record.width, right), min(record.height, bottom)))
    return boxes


def crop_intersects(crop: tuple[int, int, int, int], boxes: list[tuple[int, int, int, int]]) -> bool:
    left, top, right, bottom = crop
    return any(
        left < box_right and right > box_left and top < box_bottom and bottom > box_top
        for box_left, box_top, box_right, box_bottom in boxes
    )


def choose_negative_crop(
    record: ImageRecord,
    rng: random.Random,
    scale_min: float,
    scale_max: float,
    output_width: int,
    output_height: int,
    margin: int,
    attempts: int,
) -> tuple[int, int, int, int] | None:
    aspect = output_width / output_height
    boxes = pixel_boxes(record, margin)
    for _ in range(attempts):
        crop_width = round(record.width * rng.uniform(scale_min, scale_max))
        crop_height = round(crop_width / aspect)
        if crop_height > record.height:
            crop_height = round(record.height * scale_max)
            crop_width = round(crop_height * aspect)
        crop_width = min(record.width, max(1, crop_width))
        crop_height = min(record.height, max(1, crop_height))
        left = rng.randint(0, record.width - crop_width)
        top = rng.randint(0, record.height - crop_height)
        crop = (left, top, left + crop_width, top + crop_height)
        if not crop_intersects(crop, boxes):
            return crop
    return None


def generate_negatives(
    sequences: dict[str, SequenceStats],
    assignments: dict[str, int],
    destination: Path,
    args: argparse.Namespace,
) -> tuple[list[dict], dict[str, list[Path]]]:
    rng = random.Random(args.seed + 1)
    manifest: list[dict] = []
    outputs: dict[str, list[Path]] = defaultdict(list)
    image_root = destination / "negatives" / "images"
    label_root = destination / "negatives" / "labels"
    image_root.mkdir(parents=True, exist_ok=True)
    label_root.mkdir(parents=True, exist_ok=True)

    for sequence in sorted(sequences):
        for record in sorted(sequences[sequence].images, key=lambda item: str(item.path)):
            if rng.random() >= args.negative_fraction:
                continue
            crop = choose_negative_crop(
                record,
                rng,
                args.crop_scale_min,
                args.crop_scale_max,
                args.negative_width,
                args.negative_height,
                args.box_margin,
                args.crop_attempts,
            )
            if crop is None:
                continue
            image = cv2.imread(str(record.path), cv2.IMREAD_COLOR)
            if image is None:
                continue
            left, top, right, bottom = crop
            negative = image[top:bottom, left:right]
            negative = cv2.resize(
                negative,
                (args.negative_width, args.negative_height),
                interpolation=cv2.INTER_AREA,
            )
            digest = hashlib.sha1(str(record.path).encode("utf-8")).hexdigest()[:12]
            output_image = image_root / f"{digest}_{record.path.stem}_negative.jpg"
            output_label = label_root / output_image.with_suffix(".txt").name
            if not cv2.imwrite(str(output_image), negative, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                raise RuntimeError(f"Could not write negative crop: {output_image}")
            output_label.write_text("", encoding="utf-8")
            outputs[sequence].append(output_image.resolve())
            manifest.append(
                {
                    "image": str(output_image.resolve()),
                    "parent": str(record.path),
                    "sequence": sequence,
                    "heldout_fold": assignments[sequence],
                    "crop_xyxy": list(crop),
                    "source_size": [record.width, record.height],
                    "output_size": [args.negative_width, args.negative_height],
                }
            )
    return manifest, outputs


def write_folds(
    config,
    sequences: dict[str, SequenceStats],
    assignments: dict[str, int],
    negatives: dict[str, list[Path]],
    destination: Path,
    fold_count: int,
    seed: int,
) -> list[dict]:
    summaries: list[dict] = []
    for fold_index in range(fold_count):
        fold_dir = destination / f"fold_{fold_index}"
        fold_dir.mkdir(parents=True, exist_ok=True)
        validation_sequences = {name for name, assigned in assignments.items() if assigned == fold_index}
        train_images: list[Path] = []
        validation_images: list[Path] = []
        train_originals = validation_originals = train_negatives = validation_negatives = 0
        for sequence, stats in sequences.items():
            original_paths = [record.path.resolve() for record in stats.images]
            negative_paths = negatives.get(sequence, [])
            if sequence in validation_sequences:
                validation_images.extend(original_paths)
                validation_images.extend(negative_paths)
                validation_originals += len(original_paths)
                validation_negatives += len(negative_paths)
            else:
                train_images.extend(original_paths)
                train_images.extend(negative_paths)
                train_originals += len(original_paths)
                train_negatives += len(negative_paths)

        train_images.sort()
        validation_images.sort()
        train_list = fold_dir / "train.txt"
        validation_list = fold_dir / "val.txt"
        train_list.write_text("\n".join(map(str, train_images)) + "\n", encoding="utf-8")
        validation_list.write_text("\n".join(map(str, validation_images)) + "\n", encoding="utf-8")
        fold_yaml = {
            "path": str(fold_dir.resolve()),
            "train": str(train_list.resolve()),
            "val": str(validation_list.resolve()),
            "nc": len(config.names),
            "names": config.names,
            "vigil_cross_validation": {
                "fold": fold_index,
                "folds": fold_count,
                "seed": seed,
                "grouped_by_source_sequence": True,
                "heldout_sequences": sorted(validation_sequences),
            },
        }
        (fold_dir / "data.yaml").write_text(
            yaml.safe_dump(fold_yaml, sort_keys=False), encoding="utf-8"
        )
        summaries.append(
            {
                "fold": fold_index,
                "heldout_sequences": sorted(validation_sequences),
                "train_originals": train_originals,
                "train_negatives": train_negatives,
                "validation_originals": validation_originals,
                "validation_negatives": validation_negatives,
            }
        )
    return summaries


def main() -> None:
    args = parse_args()
    if args.folds < 2:
        raise SystemExit("--folds must be at least 2")
    if not 0.0 <= args.negative_fraction <= 1.0:
        raise SystemExit("--negative-fraction must be between 0 and 1")
    if not 0.0 < args.crop_scale_min <= args.crop_scale_max <= 1.0:
        raise SystemExit("Crop scales must satisfy 0 < min <= max <= 1")
    if min(args.negative_width, args.negative_height, args.crop_attempts) <= 0:
        raise SystemExit("Negative dimensions and crop attempts must be positive")
    if args.box_margin < 0:
        raise SystemExit("--box-margin cannot be negative")

    yaml_path = find_data_yaml(args.dataset)
    config = load_dataset_config(yaml_path)
    destination = args.destination.expanduser().resolve()
    source_tree = yaml_path.parent.resolve()
    if destination == source_tree or source_tree in destination.parents:
        raise SystemExit("Destination must not be the source directory or inside it")
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"Destination must be empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    sequences = load_records(config)
    assignments = assign_folds(sequences, args.folds, args.seed)
    manifest, negatives = generate_negatives(sequences, assignments, destination, args)
    fold_summaries = write_folds(
        config,
        sequences,
        assignments,
        negatives,
        destination,
        args.folds,
        args.seed,
    )
    report = {
        "source_yaml": str(yaml_path),
        "folds": args.folds,
        "seed": args.seed,
        "source_images": sum(item.image_count for item in sequences.values()),
        "source_sequences": len(sequences),
        "generated_negatives": len(manifest),
        "negative_generation": {
            "selection_fraction": args.negative_fraction,
            "crop_scale": [args.crop_scale_min, args.crop_scale_max],
            "output_size": [args.negative_width, args.negative_height],
            "box_margin_px": args.box_margin,
            "warning": "Crops avoid known annotations only; manually review for missed people.",
        },
        "sequence_assignments": assignments,
        "fold_summaries": fold_summaries,
    }
    write_json(destination / "negative_manifest.json", manifest)
    write_json(destination / "fold_report.json", report)
    print(f"Built {args.folds} grouped folds in {destination}")
    print(f"  source images: {report['source_images']}")
    print(f"  source sequences: {report['source_sequences']}")
    print(f"  generated negatives: {report['generated_negatives']}")
    for summary in fold_summaries:
        print(
            f"  fold {summary['fold']}: val={summary['validation_originals']} originals + "
            f"{summary['validation_negatives']} negatives; "
            f"held-out sequences={len(summary['heldout_sequences'])}"
        )


if __name__ == "__main__":
    main()
