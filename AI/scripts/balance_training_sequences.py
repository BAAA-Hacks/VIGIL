#!/usr/bin/env python3
"""Build fold YAMLs with temporally subsampled, sequence-balanced training lists."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import yaml

try:
    from AI.scripts.dataset_utils import (
        find_data_yaml,
        load_dataset_config,
        source_frame_id,
        split_images,
        write_json,
    )
except ModuleNotFoundError:
    from AI.scripts.dataset_utils import (  # type: ignore
        find_data_yaml,
        load_dataset_config,
        source_frame_id,
        split_images,
        write_json,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fold_root", type=Path, help="root containing fold_*/data.yaml")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--max-originals-per-sequence", type=int, default=350)
    parser.add_argument("--exist-ok", action="store_true")
    return parser.parse_args()


def temporal_key(path: Path) -> tuple[bool, int, str]:
    _, frame_number = source_frame_id(path)
    return (frame_number is None, frame_number if frame_number is not None else 0, path.name)


def evenly_spaced(items: list[Path], limit: int) -> list[Path]:
    """Select deterministic, temporally distributed items without replacement."""
    ordered = sorted(items, key=temporal_key)
    if len(ordered) <= limit:
        return ordered
    if limit == 1:
        return [ordered[len(ordered) // 2]]
    indexes = [round(index * (len(ordered) - 1) / (limit - 1)) for index in range(limit)]
    return [ordered[index] for index in indexes]


def is_derived_negative(path: Path) -> bool:
    return "_negative" in path.stem.casefold()


def balance_fold(yaml_path: Path, fold_dir: Path, limit: int) -> dict:
    config = load_dataset_config(yaml_path)
    train_images = split_images(config, "train")
    validation_images = split_images(config, "val")
    validation_entry = Path(str(config.raw["val"])).expanduser()
    if not validation_entry.is_absolute():
        validation_entry = (config.root / validation_entry).resolve()
    validation_text = (
        validation_entry.read_text(encoding="utf-8")
        if validation_entry.is_file() and validation_entry.suffix.lower() == ".txt"
        else "\n".join(map(str, validation_images)) + "\n"
    )

    originals: dict[str, list[Path]] = defaultdict(list)
    negatives: dict[tuple[str, int | None], list[Path]] = defaultdict(list)
    for image in train_images:
        sequence, frame_number = source_frame_id(image)
        if is_derived_negative(image):
            negatives[(sequence, frame_number)].append(image)
        else:
            originals[sequence].append(image)

    selected_originals: list[Path] = []
    selected_negatives: list[Path] = []
    sequence_report = {}
    for sequence, sequence_images in sorted(originals.items()):
        selected = evenly_spaced(sequence_images, limit)
        selected_keys = {(sequence, source_frame_id(image)[1]) for image in selected}
        kept_negatives = sorted(
            (
                negative
                for key in selected_keys
                for negative in negatives.get(key, [])
            ),
            key=temporal_key,
        )
        selected_originals.extend(selected)
        selected_negatives.extend(kept_negatives)
        sequence_report[sequence] = {
            "available_originals": len(sequence_images),
            "selected_originals": len(selected),
            "available_negatives": sum(
                len(negatives.get((sequence, source_frame_id(image)[1]), []))
                for image in sequence_images
            ),
            "selected_negatives": len(kept_negatives),
        }

    selected_train = sorted([*selected_originals, *selected_negatives])
    fold_dir.mkdir(parents=True, exist_ok=True)
    train_list = fold_dir / "train.txt"
    validation_list = fold_dir / "val.txt"
    train_list.write_text("\n".join(map(str, selected_train)) + "\n", encoding="utf-8")
    validation_list.write_text(validation_text, encoding="utf-8")

    output_yaml = dict(config.raw)
    output_yaml["path"] = str(fold_dir.resolve())
    output_yaml["train"] = str(train_list.resolve())
    output_yaml["val"] = str(validation_list.resolve())
    output_yaml["vigil_balancing"] = {
        "strategy": "even_temporal_subsample",
        "max_originals_per_sequence": limit,
        "short_sequences_oversampled": False,
        "validation_unchanged": True,
        "negative_policy": "retain generated crop only when its parent frame is selected",
    }
    (fold_dir / "data.yaml").write_text(
        yaml.safe_dump(output_yaml, sort_keys=False), encoding="utf-8"
    )
    return {
        "source_yaml": str(yaml_path.resolve()),
        "output_yaml": str((fold_dir / "data.yaml").resolve()),
        "original_train_images": len(train_images),
        "balanced_train_images": len(selected_train),
        "original_train_originals": sum(len(images) for images in originals.values()),
        "balanced_train_originals": len(selected_originals),
        "balanced_train_negatives": len(selected_negatives),
        "validation_images": len(validation_images),
        "sequences": sequence_report,
    }


def main() -> None:
    args = parse_args()
    if args.max_originals_per_sequence <= 0:
        raise SystemExit("--max-originals-per-sequence must be positive")
    fold_root = args.fold_root.expanduser().resolve()
    destination = args.destination.expanduser().resolve()
    fold_yamls = sorted(fold_root.glob("fold_*/data.yaml"))
    if not fold_yamls:
        try:
            fold_yamls = [find_data_yaml(fold_root)]
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc
    if destination.exists() and any(destination.iterdir()) and not args.exist_ok:
        raise SystemExit(f"Destination is not empty: {destination}")

    reports = []
    for yaml_path in fold_yamls:
        reports.append(
            balance_fold(
                yaml_path,
                destination / yaml_path.parent.name,
                args.max_originals_per_sequence,
            )
        )
    report = {
        "source_fold_root": str(fold_root),
        "destination": str(destination),
        "max_originals_per_sequence": args.max_originals_per_sequence,
        "folds": reports,
    }
    write_json(destination / "balancing_report.json", report)
    print(f"Balanced fold definitions: {destination}")
    for index, fold in enumerate(reports):
        print(
            f"  fold_{index}: {fold['original_train_images']} -> "
            f"{fold['balanced_train_images']} train images; "
            f"validation unchanged at {fold['validation_images']}"
        )


if __name__ == "__main__":
    main()
