#!/usr/bin/env python3
"""Validate a YOLO dataset and quantify targets at effective Lepton resolution."""

from __future__ import annotations

import argparse
import hashlib
import random
from collections import Counter, defaultdict
from pathlib import Path

import cv2

try:
    from AI.scripts.dataset_utils import (
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
        box_is_normalized,
        find_data_yaml,
        label_path_for_image,
        load_dataset_config,
        read_yolo_labels,
        source_frame_id,
        split_images,
        write_json,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Dataset root or data.yaml")
    parser.add_argument("--output", type=Path, default=Path("dataset_inspection"))
    parser.add_argument("--target-width", type=int, default=160)
    parser.add_argument("--target-height", type=int, default=120)
    parser.add_argument("--examples-per-split", type=int, default=8)
    parser.add_argument("--tiny-threshold", type=float, default=4.0, help="Tiny side threshold in pixels")
    parser.add_argument("--seed", type=int, default=26)
    return parser.parse_args()


def draw_example(image_path: Path, boxes: list, names: dict[int, str], output: Path) -> None:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        return
    height, width = image.shape[:2]
    for box in boxes:
        left = round((box.x_center - box.width / 2) * width)
        top = round((box.y_center - box.height / 2) * height)
        right = round((box.x_center + box.width / 2) * width)
        bottom = round((box.y_center + box.height / 2) * height)
        color = (0, 255, 255)
        cv2.rectangle(image, (left, top), (right, bottom), color, max(1, width // 500))
        label = names.get(box.class_id, str(box.class_id))
        cv2.putText(
            image,
            label,
            (max(0, left), max(12, top - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            max(0.35, width / 1800),
            color,
            max(1, width // 700),
            cv2.LINE_AA,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output), image)


def decoded_image_fingerprint(image) -> str:
    """Hash decoded pixels so renamed byte-identical images can be detected."""
    digest = hashlib.sha256()
    digest.update(str(image.shape).encode("ascii"))
    digest.update(str(image.dtype).encode("ascii"))
    digest.update(image.tobytes(order="C"))
    return digest.hexdigest()


def duplicate_content_report(content_groups: dict[str, list[tuple[str, Path]]]) -> dict:
    duplicates = {
        digest: entries for digest, entries in content_groups.items() if len(entries) > 1
    }
    cross_split = {
        digest: entries
        for digest, entries in duplicates.items()
        if len({split for split, _ in entries}) > 1
    }
    pairwise: Counter = Counter()
    for entries in cross_split.values():
        splits = sorted({split for split, _ in entries})
        for left_index, left in enumerate(splits):
            for right in splits[left_index + 1 :]:
                pairwise[f"{left}_{right}"] += 1

    def examples(groups: dict[str, list[tuple[str, Path]]]) -> list[dict]:
        return [
            {
                "sha256_decoded_pixels": digest,
                "files": [
                    {"split": split, "path": str(path)} for split, path in entries
                ],
            }
            for digest, entries in sorted(groups.items())[:100]
        ]

    return {
        "method": "SHA-256 over decoded shape, dtype, and exact pixel values",
        "duplicate_groups": len(duplicates),
        "images_in_duplicate_groups": sum(len(entries) for entries in duplicates.values()),
        "cross_split_duplicate_groups": len(cross_split),
        "cross_split_group_counts": dict(sorted(pairwise.items())),
        "examples_limited_to": 100,
        "duplicate_examples": examples(duplicates),
        "cross_split_examples": examples(cross_split),
    }


def sequence_overlap(split_paths: dict[str, list[Path]]) -> dict:
    sequences: dict[str, dict[str, set[int]]] = {}
    parser_audit: dict[str, dict] = {}
    for split, images in split_paths.items():
        split_sequences: dict[str, set[int]] = {}
        frame_occurrences: Counter = Counter()
        original_frame_occurrences: Counter = Counter()
        frames_without_number = 0
        derived_negative_images = 0
        for image in images:
            sequence, frame = source_frame_id(image)
            derived_negative = "_negative" in image.stem.casefold()
            derived_negative_images += derived_negative
            if frame is not None:
                split_sequences.setdefault(sequence, set()).add(frame)
                frame_occurrences[(sequence, frame)] += 1
                if not derived_negative:
                    original_frame_occurrences[(sequence, frame)] += 1
            else:
                split_sequences.setdefault(sequence, set())
                frames_without_number += 1
        sequences[split] = split_sequences
        sizes = Counter(source_frame_id(image)[0] for image in images)
        parser_audit[split] = {
            "images": len(images),
            "sequences": len(sizes),
            "frames_without_parsed_number": frames_without_number,
            "frames_without_parsed_number_fraction": (
                round(frames_without_number / len(images), 6) if images else None
            ),
            "derived_negative_images": derived_negative_images,
            "singleton_sequences": sum(size == 1 for size in sizes.values()),
            "duplicate_sequence_frame_ids": sum(
                count - 1 for count in frame_occurrences.values() if count > 1
            ),
            "duplicate_original_sequence_frame_ids": sum(
                count - 1 for count in original_frame_occurrences.values() if count > 1
            ),
            "largest_sequences": [
                {"sequence": sequence, "images": size}
                for sequence, size in sizes.most_common(20)
            ],
        }

    report: dict[str, object] = {
        "sequence_counts": {split: len(items) for split, items in sequences.items()},
        "parser_audit": parser_audit,
        "pairwise": {},
    }
    for left, right in (("train", "val"), ("train", "test"), ("val", "test")):
        if left not in sequences or right not in sequences:
            continue
        shared = sorted(set(sequences[left]) & set(sequences[right]))
        exact_frames = sum(
            len(sequences[left][sequence] & sequences[right][sequence]) for sequence in shared
        )
        report["pairwise"][f"{left}_{right}"] = {
            "shared_sequence_count": len(shared),
            "shared_sequences": shared,
            "exact_frame_id_overlap": exact_frames,
        }
    return report


def summarize_split(
    split: str,
    images: list[Path],
    output: Path,
    names: dict[int, str],
    target_width: int,
    target_height: int,
    tiny_threshold: float,
    example_count: int,
    rng: random.Random,
    content_groups: dict[str, list[tuple[str, Path]]],
) -> dict:
    counts: Counter = Counter(images=len(images))
    class_counts: Counter = Counter()
    widths: list[float] = []
    heights: list[float] = []
    issues: list[str] = []
    valid_examples: list[tuple[Path, list]] = []

    for image_path in images:
        image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        if image is None:
            counts["unreadable_images"] += 1
            issues.append(f"Unreadable image: {image_path}")
            continue
        content_groups[decoded_image_fingerprint(image)].append(
            (split, image_path.resolve())
        )
        source_height, source_width = image.shape[:2]
        counts[f"dimensions_{source_width}x{source_height}"] += 1
        counts[f"channels_{1 if image.ndim == 2 else image.shape[2]}"] += 1
        counts[f"dtype_{image.dtype}"] += 1
        scale = min(target_width / source_width, target_height / source_height)

        label_path = label_path_for_image(image_path)
        boxes, errors = read_yolo_labels(label_path)
        if not label_path.exists():
            counts["missing_labels"] += 1
        elif not boxes and not errors:
            counts["empty_labels"] += 1
        if errors:
            counts["invalid_label_lines"] += len(errors)
            issues.extend(errors)

        valid_boxes = []
        for box in boxes:
            class_counts[box.class_id] += 1
            if box.class_id not in names:
                counts["unknown_class_boxes"] += 1
                issues.append(f"Unknown class ID {box.class_id} in {label_path}")
                continue
            if not box_is_normalized(box):
                counts["invalid_boxes"] += 1
                issues.append(f"Out-of-range box in {label_path}: {box}")
                continue
            counts["annotations"] += 1
            effective_width = box.width * source_width * scale
            effective_height = box.height * source_height * scale
            widths.append(effective_width)
            heights.append(effective_height)
            if effective_width < tiny_threshold or effective_height < tiny_threshold:
                counts["tiny_annotations"] += 1
            valid_boxes.append(box)
        valid_examples.append((image_path, valid_boxes))

    rng.shuffle(valid_examples)
    for index, (image_path, boxes) in enumerate(valid_examples[:example_count], 1):
        draw_example(
            image_path,
            boxes,
            names,
            output / "examples" / split / f"{index:02d}_{image_path.stem}.jpg",
        )

    def distribution(values: list[float]) -> dict:
        if not values:
            return {}
        ordered = sorted(values)
        percentile = lambda fraction: ordered[round((len(ordered) - 1) * fraction)]
        return {
            "min": round(ordered[0], 3),
            "p10": round(percentile(0.10), 3),
            "median": round(percentile(0.50), 3),
            "p90": round(percentile(0.90), 3),
            "max": round(ordered[-1], 3),
        }

    for key in (
        "annotations",
        "tiny_annotations",
        "missing_labels",
        "empty_labels",
        "invalid_label_lines",
        "invalid_boxes",
        "unknown_class_boxes",
        "unreadable_images",
    ):
        counts.setdefault(key, 0)

    return {
        "counts": dict(counts),
        "tiny_annotation_fraction": (
            round(counts["tiny_annotations"] / counts["annotations"], 6)
            if counts["annotations"]
            else None
        ),
        "class_annotations": {str(key): value for key, value in sorted(class_counts.items())},
        "effective_box_width_px": distribution(widths),
        "effective_box_height_px": distribution(heights),
        "issues": issues,
    }


def main() -> None:
    args = parse_args()
    if args.target_width <= 0 or args.target_height <= 0:
        raise SystemExit("Target dimensions must be positive")
    if args.examples_per_split < 0:
        raise SystemExit("--examples-per-split cannot be negative")

    yaml_path = find_data_yaml(args.dataset)
    config = load_dataset_config(yaml_path)
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    report = {
        "dataset_yaml": str(yaml_path),
        "class_names": {str(key): value for key, value in config.names.items()},
        "effective_resolution": [args.target_width, args.target_height],
        "tiny_side_threshold_px": args.tiny_threshold,
        "splits": {},
    }
    split_paths = {
        split: split_images(config, split) for split in ("train", "val", "test")
    }
    content_groups: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    for split, images in split_paths.items():
        if not images:
            continue
        report["splits"][split] = summarize_split(
            split,
            images,
            output,
            config.names,
            args.target_width,
            args.target_height,
            args.tiny_threshold,
            args.examples_per_split,
            rng,
            content_groups,
        )
    report["source_sequence_overlap"] = sequence_overlap(
        {split: paths for split, paths in split_paths.items() if paths}
    )
    report["exact_content_duplicates"] = duplicate_content_report(content_groups)

    write_json(output / "inspection_report.json", report)
    print(f"Inspection report: {output / 'inspection_report.json'}")
    for split, summary in report["splits"].items():
        counts = summary["counts"]
        print(
            f"  {split}: {counts.get('images', 0)} images, "
            f"{counts.get('annotations', 0)} valid boxes, "
            f"{counts.get('tiny_annotations', 0)} tiny boxes, "
            f"{len(summary['issues'])} issues"
        )
    duplicates = report["exact_content_duplicates"]
    print(
        f"  exact duplicate groups: {duplicates['duplicate_groups']}; "
        f"cross-split: {duplicates['cross_split_duplicate_groups']}"
    )


if __name__ == "__main__":
    main()
