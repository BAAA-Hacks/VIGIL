#!/usr/bin/env python3
"""Build a 3-frame temporal copy of a VIGIL fold root ([t-2k, t-k, t] in B, G, R).

Every image keeps its filename, label, and fold membership, so evaluate.py, sequence
grouping, and the fold lists work unchanged. Neighbour frames get exactly the same
geometry as frame t:
  - WiSARD full frames: neighbours come from the same letterboxed full-frame directory.
  - WiSARD medium crops: neighbours are re-cropped from the original-resolution source
    with frame t's crop window (crop windows follow the target, so stacking neighbouring
    crop files directly would invent motion).
  - POP and external still datasets are symlinked unchanged (Ultralytics replicates
    grayscale to three identical channels: a "no motion" example).
Frames with no neighbour within --max-gap are replicated, which also teaches the model
to fall back to appearance alone.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import yaml

try:
    from AI.scripts.dataset_utils import (
        absolute_path,
        label_path_for_image,
        load_dataset_config,
        read_yolo_labels,
        source_frame_id,
        split_images,
        write_json,
    )
    from AI.scripts.prepare_medium_crops import centered_crop_bounds, medium_crop_bounds
    from AI.scripts.prepare_wisard import letterbox_grayscale
    from AI.scripts.temporal_utils import ALIGN_MODES, stack_frames
except ModuleNotFoundError:
    from AI.scripts.dataset_utils import (  # type: ignore
        absolute_path,
        label_path_for_image,
        load_dataset_config,
        read_yolo_labels,
        source_frame_id,
        split_images,
        write_json,
    )
    from AI.scripts.prepare_medium_crops import centered_crop_bounds, medium_crop_bounds  # type: ignore
    from AI.scripts.prepare_wisard import letterbox_grayscale  # type: ignore
    from AI.scripts.temporal_utils import ALIGN_MODES, stack_frames  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_folds", type=Path, help="Existing fold root, e.g. thermal_mega_5fold_lepton_medium_range")
    parser.add_argument("destination", type=Path, help="New temporal fold root (must be empty)")
    parser.add_argument(
        "--manifest-images",
        type=Path,
        default=Path("AI/datasets/wisard_full_ir_manifest/images"),
        help="Original-resolution WiSARD frames that the medium crops were cut from",
    )
    parser.add_argument("--frame-step", type=int, default=1, help="k in [t-2k, t-k, t], in source frame numbers")
    parser.add_argument(
        "--max-gap",
        type=int,
        default=None,
        help="Furthest earlier frame accepted as a neighbour (default: 2 x frame-step)",
    )
    parser.add_argument("--align", choices=ALIGN_MODES, default="none")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    return parser.parse_args()


def sequence_index(paths: list[Path]) -> dict[str, dict[int, Path]]:
    index: dict[str, dict[int, Path]] = defaultdict(dict)
    for path in paths:
        sequence, frame = source_frame_id(path)
        if frame is not None:
            index[sequence][frame] = path
    return index


def neighbour(frames: dict[int, Path], frame: int, offset: int, max_gap: int) -> Path | None:
    """Nearest available frame at or before frame - offset, no further back than max_gap."""
    for candidate in range(frame - offset, frame - max_gap - 1, -1):
        if candidate in frames and candidate < frame:
            return frames[candidate]
    return None


def classify(path: Path, source_root: Path) -> str:
    text = str(path)
    if "/external/" in text:
        return "external_stills"
    if "/medium_crops/wisard/" in text:
        return "wisard_crops"
    if "/medium_crops/pop/" in text:
        return "pop_crops"
    if "/pop/" in text:
        return "pop_full"
    if "wisard" in text:
        return "wisard_full"
    raise SystemExit(f"Cannot classify image source: {path}")


def read_gray(path: Path):
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise SystemExit(f"Could not decode image: {path}")
    return image


def crop_view(source: Path, bounds: tuple[int, int, int, int], shape: tuple[int, int], width: int, height: int, padding: int):
    image = read_gray(source)
    if image.shape != shape:
        return None
    left, top, right, bottom = bounds
    view, *_ = letterbox_grayscale(image[top:bottom, left:right], width, height, padding)
    return view


def build_one(job: dict) -> tuple[str, int]:
    """Write one temporal image; returns (output path, number of real neighbours used)."""
    output = Path(job["output"])
    if job["kind"] == "wisard_full":
        current = read_gray(Path(job["image"]))
        views = [read_gray(Path(p)) if p else None for p in job["neighbours"]]
        views = [view if view is not None and view.shape == current.shape else None for view in views]
    else:
        source = Path(job["source"])
        reference = read_gray(source)
        shape = reference.shape
        crop = job["crop"]
        bounds = (
            medium_crop_bounds(shape[1], shape[0], crop["boxes"], crop["scale"], crop["aspect"], crop["margin"])
            if crop["boxes"]
            else centered_crop_bounds(shape[1], shape[0], crop["scale"], crop["aspect"])
        )
        args = (bounds, shape, crop["width"], crop["height"], crop["padding"])
        current = crop_view(source, *args)
        views = [crop_view(Path(p), *args) if p else None for p in job["neighbours"]]
        # The crop file on disk is the ground truth for frame t; recomputation must match it.
        existing = read_gray(Path(job["image"]))
        if existing.shape != current.shape or abs(int(existing.astype(int).sum()) - int(current.astype(int).sum())) > existing.size:
            raise SystemExit(f"Recomputed crop does not match {job['image']}; crop settings differ")
    used = sum(view is not None for view in views)
    frames = [view if view is not None else current for view in views] + [current]
    stacked = stack_frames(frames, job["align"])
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), stacked):
        raise SystemExit(f"Could not write {output}")
    return str(output), used


def link(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.symlink_to(source)


def main() -> None:
    args = parse_args()
    if args.frame_step <= 0:
        raise SystemExit("--frame-step must be positive")
    max_gap = args.max_gap if args.max_gap is not None else 2 * args.frame_step
    if max_gap < 2 * args.frame_step:
        raise SystemExit("--max-gap must be at least 2 x --frame-step")
    source_root = args.source_folds.expanduser().resolve()
    destination = args.destination.expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"Destination must be empty: {destination}")
    report_path = source_root / "preparation_report.json"
    crop_settings = yaml.safe_load(report_path.read_text(encoding="utf-8"))["medium_crop"]
    fold_yamls = sorted(source_root.glob("fold_*/data.yaml"))
    if not fold_yamls:
        raise SystemExit(f"No fold_*/data.yaml under {source_root}")

    split_lists: dict[tuple[str, str], list[Path]] = {}
    unique: set[Path] = set()
    for fold_yaml in fold_yamls:
        config = load_dataset_config(fold_yaml)
        for split in ("train", "val", "test"):
            paths = [absolute_path(path) for path in split_images(config, split)]
            split_lists[(fold_yaml.parent.name, split)] = paths
            unique.update(paths)

    by_kind: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(unique):
        by_kind[classify(path, source_root)].append(path)
    print({kind: len(paths) for kind, paths in by_kind.items()})

    full_index = sequence_index(by_kind["wisard_full"])
    manifest_paths = sorted(
        absolute_path(path) for path in args.manifest_images.expanduser().iterdir() if path.is_file()
    )
    manifest_index = sequence_index(manifest_paths)
    crop_to_source = {
        f"{hashlib.sha1(str(path).encode('utf-8')).hexdigest()[:16]}_{path.stem}": path for path in manifest_paths
    }

    def mirrored(path: Path, kind: str) -> Path:
        return destination / kind / "images" / path.name

    jobs: list[dict] = []
    for path in by_kind["wisard_full"]:
        sequence, frame = source_frame_id(path)
        frames = full_index.get(sequence, {})
        neighbours = (
            [neighbour(frames, frame, 2 * args.frame_step, max_gap), neighbour(frames, frame, args.frame_step, max_gap)]
            if frame is not None
            else [None, None]
        )
        jobs.append(
            {"kind": "wisard_full", "image": str(path), "neighbours": [str(n) if n else None for n in neighbours],
             "output": str(mirrored(path, "wisard_full")), "align": args.align}
        )
    for path in by_kind["wisard_crops"]:
        source = crop_to_source.get(path.stem)
        if source is None:
            raise SystemExit(f"No manifest source frame for crop {path.name}")
        boxes, errors = read_yolo_labels(label_path_for_image(source))
        if errors:
            raise SystemExit("\n".join(errors))
        sequence, frame = source_frame_id(source)
        frames = manifest_index.get(sequence, {})
        neighbours = (
            [neighbour(frames, frame, 2 * args.frame_step, max_gap), neighbour(frames, frame, args.frame_step, max_gap)]
            if frame is not None
            else [None, None]
        )
        jobs.append(
            {
                "kind": "wisard_crops",
                "image": str(path),
                "source": str(source),
                "neighbours": [str(n) if n else None for n in neighbours],
                "crop": {
                    "boxes": boxes,
                    "scale": crop_settings["crop_scale"],
                    "aspect": crop_settings["target_size"][0] / crop_settings["target_size"][1],
                    "margin": crop_settings["box_margin"],
                    "width": crop_settings["target_size"][0],
                    "height": crop_settings["target_size"][1],
                    "padding": 114,
                },
                "output": str(mirrored(path, "wisard_crops")),
                "align": args.align,
            }
        )

    neighbour_counts: Counter[int] = Counter()
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for done, (_, used) in enumerate(pool.map(build_one, jobs, chunksize=64), start=1):
            neighbour_counts[used] += 1
            if done % 5000 == 0:
                print(f"  {done}/{len(jobs)} temporal images")

    for kind in ("wisard_full", "wisard_crops", "pop_full", "pop_crops", "external_stills"):
        for path in by_kind[kind]:
            target = mirrored(path, kind)
            if kind.startswith("pop") or kind == "external_stills":
                link(path, target)
            label = label_path_for_image(path)
            target_label = label_path_for_image(target)
            target_label.parent.mkdir(parents=True, exist_ok=True)
            if label.is_file():
                shutil.copyfile(label, target_label)
            else:
                target_label.write_text("", encoding="utf-8")

    temporal_block = {
        "channels": "B=t-2k, G=t-k, R=t (grayscale each)",
        "frame_step": args.frame_step,
        "max_gap": max_gap,
        "align": args.align,
        "stills_replicated": ["pop_full", "pop_crops", "external_stills"],
        "source_folds": str(source_root),
    }
    fold_reports = []
    for fold_yaml in fold_yamls:
        fold = fold_yaml.parent.name
        fold_dir = destination / fold
        fold_dir.mkdir(parents=True, exist_ok=True)
        output_yaml = yaml.safe_load(fold_yaml.read_text(encoding="utf-8"))
        output_yaml["path"] = str(fold_dir)
        counts = {}
        for split in ("train", "val", "test"):
            paths = [mirrored(path, classify(path, source_root)) for path in split_lists[(fold, split)]]
            (fold_dir / f"{split}.txt").write_text("\n".join(map(str, paths)) + "\n", encoding="utf-8")
            output_yaml[split] = str(fold_dir / f"{split}.txt")
            counts[split] = len(paths)
        output_yaml["vigil_temporal"] = temporal_block
        (fold_dir / "data.yaml").write_text(yaml.safe_dump(output_yaml, sort_keys=False), encoding="utf-8")
        fold_reports.append({"fold": fold, **counts})

    report = {
        "destination": str(destination),
        **temporal_block,
        "images": {kind: len(paths) for kind, paths in by_kind.items()},
        "real_neighbours_per_temporal_image": {str(k): v for k, v in sorted(neighbour_counts.items())},
        "folds": fold_reports,
    }
    write_json(destination / "preparation_report.json", report)
    print(f"Temporal folds: {destination}")
    print(f"Real neighbours per stacked image (0 = fully replicated): {report['real_neighbours_per_temporal_image']}")


if __name__ == "__main__":
    main()
