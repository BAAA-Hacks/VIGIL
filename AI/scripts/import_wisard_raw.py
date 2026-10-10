#!/usr/bin/env python3
"""Create a canonical YOLO manifest from extracted WiSARD source-video folders."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

try:
    from AI.scripts.dataset_utils import (
        IMAGE_SUFFIXES,
        YoloBox,
        box_is_normalized,
        format_yolo_box,
        read_yolo_labels,
        source_frame_id,
        write_json,
    )
except ModuleNotFoundError:
    from AI.scripts.dataset_utils import (  # type: ignore
        IMAGE_SUFFIXES,
        YoloBox,
        box_is_normalized,
        format_yolo_box,
        read_yolo_labels,
        source_frame_id,
        write_json,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="directory containing extracted WiSARD video folders")
    parser.add_argument("destination", type=Path, help="new canonical YOLO dataset directory")
    parser.add_argument("--modality", choices=("IR", "VIS"), default="IR")
    return parser.parse_args()


def declared_human_count(directory: Path) -> int | None:
    path = directory / "count.txt"
    if not path.is_file():
        return None
    match = re.search(r"number\s+of\s+humans\s*:\s*(\d+)", path.read_text(encoding="utf-8"), re.I)
    if not match:
        raise SystemExit(f"Could not parse human count: {path}")
    return int(match.group(1))


def discover_directories(source: Path, modality: str) -> list[Path]:
    marker = f"_{modality}"
    return sorted(
        path
        for path in source.iterdir()
        if path.is_dir() and marker in path.name and not path.name.startswith("WiSARD_")
    )


def clip_small_boundary_overflow(box: YoloBox, tolerance: float = 0.01) -> tuple[YoloBox, bool]:
    """Clip small annotation-rounding overflow while rejecting materially invalid boxes."""
    left = box.x_center - box.width / 2
    top = box.y_center - box.height / 2
    right = box.x_center + box.width / 2
    bottom = box.y_center + box.height / 2
    overflow = max(0.0, -left, -top, right - 1.0, bottom - 1.0)
    if overflow > tolerance:
        raise ValueError(f"box exceeds the image boundary by {overflow:.6f}: {box}")
    clipped_left = min(1.0, max(0.0, left))
    clipped_top = min(1.0, max(0.0, top))
    clipped_right = min(1.0, max(0.0, right))
    clipped_bottom = min(1.0, max(0.0, bottom))
    if clipped_right <= clipped_left or clipped_bottom <= clipped_top:
        raise ValueError(f"box has no area after boundary clipping: {box}")
    clipped = YoloBox(
        class_id=box.class_id,
        x_center=(clipped_left + clipped_right) / 2,
        y_center=(clipped_top + clipped_bottom) / 2,
        width=clipped_right - clipped_left,
        height=clipped_bottom - clipped_top,
    )
    return clipped, overflow > 0.0


def main() -> None:
    args = parse_args()
    source = args.source.expanduser().resolve()
    destination = args.destination.expanduser().resolve()
    if not source.is_dir():
        raise SystemExit(f"Source directory not found: {source}")
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"Destination must be empty: {destination}")

    directories = discover_directories(source, args.modality)
    if not directories:
        raise SystemExit(f"No {args.modality} source-video directories found in {source}")
    image_root = destination / "images"
    label_root = destination / "labels"
    image_root.mkdir(parents=True, exist_ok=True)
    label_root.mkdir(parents=True, exist_ok=True)

    sequence_reports = []
    total_images = total_boxes = explicit_empty = verified_missing_empty = clipped_boxes = 0
    for directory in directories:
        images = sorted(
            path
            for path in directory.iterdir()
            if path.is_file()
            and path.suffix.lower() in IMAGE_SUFFIXES
            and not path.name.endswith(":Zone.Identifier")
        )
        declared = declared_human_count(directory)
        sequence_boxes = sequence_explicit_empty = sequence_verified_missing = sequence_clipped = 0
        frames_without_number = 0
        for source_image in images:
            source_label = source_image.with_suffix(".txt")
            if source_label.is_file():
                boxes, errors = read_yolo_labels(source_label)
                if errors:
                    raise SystemExit("\n".join(errors))
                if any(box.class_id != 0 for box in boxes):
                    raise SystemExit(f"Non-person annotation in {source_label}")
                normalized_boxes = []
                for box in boxes:
                    try:
                        normalized, was_clipped = clip_small_boundary_overflow(box)
                    except ValueError as exc:
                        raise SystemExit(f"{source_label}: {exc}") from exc
                    if not box_is_normalized(normalized):
                        raise SystemExit(f"Could not normalize annotation in {source_label}: {box}")
                    normalized_boxes.append(normalized)
                    sequence_clipped += was_clipped
                label_text = "\n".join(format_yolo_box(box) for box in normalized_boxes)
                if label_text:
                    label_text += "\n"
                sequence_boxes += len(boxes)
                if not boxes:
                    sequence_explicit_empty += 1
            else:
                if declared != 0:
                    raise SystemExit(
                        f"Missing label is only accepted for a declared zero-human video: {source_image}"
                    )
                label_text = ""
                sequence_verified_missing += 1

            _, frame_number = source_frame_id(source_image)
            frames_without_number += frame_number is None
            canonical_name = f"{directory.name}__{source_image.name}"
            output_image = image_root / canonical_name
            output_label = label_root / Path(canonical_name).with_suffix(".txt").name
            output_image.symlink_to(source_image)
            output_label.write_text(label_text, encoding="utf-8")

        if declared is not None and declared != sequence_boxes:
            raise SystemExit(
                f"count.txt mismatch in {directory}: declared {declared}, parsed {sequence_boxes} boxes"
            )
        sequence_reports.append(
            {
                "sequence_directory": directory.name,
                "images": len(images),
                "annotations": sequence_boxes,
                "explicit_empty_labels": sequence_explicit_empty,
                "verified_zero_human_labels_created": sequence_verified_missing,
                "declared_humans": declared,
                "frames_without_parsed_number": frames_without_number,
                "boundary_clipped_annotations": sequence_clipped,
            }
        )
        total_images += len(images)
        total_boxes += sequence_boxes
        explicit_empty += sequence_explicit_empty
        verified_missing_empty += sequence_verified_missing
        clipped_boxes += sequence_clipped

    data = {
        "path": str(destination),
        "train": str(image_root),
        "nc": 1,
        "names": {0: "person"},
        "vigil_import": {
            "source": str(source),
            "modality": args.modality,
            "image_storage": "absolute symlinks to immutable extracted files",
            "missing_label_policy": (
                "create an empty label only when the source video count.txt explicitly "
                "declares zero humans"
            ),
        },
    }
    (destination / "data.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    report = {
        "source": str(source),
        "destination": str(destination),
        "modality": args.modality,
        "sequences": len(directories),
        "images": total_images,
        "annotations": total_boxes,
        "explicit_empty_labels": explicit_empty,
        "verified_zero_human_labels_created": verified_missing_empty,
        "boundary_clipped_annotations": clipped_boxes,
        "sequence_reports": sequence_reports,
    }
    write_json(destination / "import_report.json", report)
    print(f"Canonical WiSARD {args.modality} dataset: {destination}")
    print(f"  sequences: {len(directories)}")
    print(f"  images: {total_images}")
    print(f"  annotations: {total_boxes}")
    print(f"  verified zero-human labels created: {verified_missing_empty}")
    print(f"  boundary-clipped annotations: {clipped_boxes}")


if __name__ == "__main__":
    main()
