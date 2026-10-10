#!/usr/bin/env python3
"""Detect evaluation sequences that also appear in training, across dataset naming generations."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

try:
    from AI.scripts.dataset_utils import load_dataset_config, source_frame_id, split_images
    from AI.scripts.portable_paths import default_root, rebase_repo_path
except ModuleNotFoundError:
    from AI.scripts.dataset_utils import load_dataset_config, source_frame_id, split_images  # type: ignore
    from AI.scripts.portable_paths import default_root, rebase_repo_path  # type: ignore


HASH_PREFIX = re.compile(r"^[0-9a-f]{12,16}_", re.IGNORECASE)
ROBOFLOW_SUFFIX = re.compile(r"\.rf\.[0-9a-f]+.*$", re.IGNORECASE)
# WiSARD directory prefix, e.g. "210924_FHL_Enterprise_IR_0404__" before the original video name.
WISARD_PREFIX = re.compile(r"^\d{6}_[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*?_(?:IR|VIS)_[A-Za-z0-9]+__(.+)$")
VIDEO_EXTENSION = re.compile(r"[\s._-]*(?:mp4|avi|mov|mkv)$", re.IGNORECASE)
# "(1-6-2022 8-27-56 AM)" or the Roboflow slug "-1-6-2022-8-27-56-AM".
EXPORT_TIMESTAMP = re.compile(
    r"[\s_-]*\(?\d{1,2}-\d{1,2}-\d{4}[\s_-]+\d{1,2}-\d{2}-\d{2}[\s_-]*[ap]m\)?", re.IGNORECASE
)
LINEAGE_FILE = "vigil_lineage.json"


def sequence_key(sequence: str) -> str:
    """Normalize a sequence name so every dataset generation maps to one key."""
    name = Path(str(sequence).strip()).name
    name = ROBOFLOW_SUFFIX.sub("", name)
    while HASH_PREFIX.match(name):
        name = HASH_PREFIX.sub("", name, count=1)
    match = WISARD_PREFIX.match(name)
    if match:
        name = match.group(1)
    name = VIDEO_EXTENSION.sub("", name)
    name = EXPORT_TIMESTAMP.sub("", name)
    name = VIDEO_EXTENSION.sub("", name)
    return re.sub(r"[^0-9a-z]+", "_", name.casefold()).strip("_")


def image_sequence_key(image_path: str | Path) -> tuple[str, int | None]:
    sequence, frame = source_frame_id(image_path)
    return sequence_key(sequence), frame


@dataclass
class TrainingSource:
    label: str
    data_yaml: Path | None
    note: str = ""


@dataclass
class LeakageReport:
    training: str
    evaluation: str
    sources: list[TrainingSource] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    leaks: dict[str, list[dict]] = field(default_factory=dict)
    eval_sequences: dict[str, int] = field(default_factory=dict)

    @property
    def leaked(self) -> bool:
        return any(self.leaks.values())

    def to_dict(self) -> dict:
        return {
            "training": self.training,
            "evaluation": self.evaluation,
            "training_sources": [
                {"label": item.label, "data": str(item.data_yaml) if item.data_yaml else None, "note": item.note}
                for item in self.sources
            ],
            "unresolved_ancestors": self.unresolved,
            "eval_sequences_per_split": self.eval_sequences,
            "leaks": self.leaks,
            "leaked": self.leaked,
        }


def _checkpoint_train_args(weights: Path) -> dict:
    import torch

    checkpoint = torch.load(weights, map_location="cpu", weights_only=False)
    return dict(checkpoint.get("train_args") or {})


def _lineage_weights(run_dir: Path) -> list[str]:
    lineage = run_dir / LINEAGE_FILE
    if not lineage.is_file():
        return []
    payload = json.loads(lineage.read_text(encoding="utf-8"))
    value = payload.get("pretrained_weights")
    return [value] if value else []


def training_sources(
    path: Path, root: Path, follow_ancestors: bool = True, extra_ancestors: list[Path] | None = None
) -> tuple[list[TrainingSource], list[str]]:
    """Resolve a data.yaml, run args.yaml, or checkpoint into every dataset it was trained on."""
    sources: list[TrainingSource] = []
    unresolved: list[str] = []
    pending: list[tuple[str, Path]] = [("input", path)] + [("ancestor", item) for item in extra_ancestors or []]
    seen: set[str] = set()
    while pending:
        role, item = pending.pop(0)
        item = rebase_repo_path(item, root)
        if str(item) in seen:
            continue
        seen.add(str(item))
        if not item.exists():
            unresolved.append(f"{role}: {item} (missing)")
            continue
        if item.suffix == ".pt":
            args = _checkpoint_train_args(item)
            data, model = args.get("data"), args.get("model")
            run_dir = item.parent.parent
        elif item.suffix in {".yaml", ".yml"}:
            raw = yaml.safe_load(item.read_text(encoding="utf-8")) or {}
            if "train" in raw:
                sources.append(TrainingSource(f"{role}:{item.name}", item))
                continue
            data, model = raw.get("data"), raw.get("model")
            run_dir = item.parent
        else:
            unresolved.append(f"{role}: {item} (unsupported file type)")
            continue
        if data:
            data_path = rebase_repo_path(data, root)
            if data_path.is_dir():
                data_path = data_path / "data.yaml"
            if data_path.is_file():
                sources.append(TrainingSource(f"{role}:{item.name}", data_path))
            else:
                unresolved.append(f"{role}: {item} trained on {data} (dataset YAML not found)")
        if not follow_ancestors:
            continue
        if model and str(model).endswith(".pt") and not Path(str(model)).name.startswith("yolo"):
            pending.append(("ancestor", Path(str(model))))
        for weights in _lineage_weights(run_dir):
            pending.append(("ancestor", Path(weights)))
    return sources, unresolved


def sequence_frames(images: list[Path]) -> dict[str, set]:
    frames: dict[str, set] = defaultdict(set)
    for image in images:
        key, frame = image_sequence_key(image)
        frames[key].add(frame if frame is not None else image.stem)
    return frames


def find_leaks(
    training: Path,
    evaluation: Path,
    splits: tuple[str, ...] = ("val", "test"),
    root: Path | None = None,
    follow_ancestors: bool = True,
    extra_ancestors: list[Path] | None = None,
) -> LeakageReport:
    root = root or default_root()
    report = LeakageReport(str(training), str(evaluation))
    report.sources, report.unresolved = training_sources(training, root, follow_ancestors, extra_ancestors)
    train_counts: dict[str, Counter] = defaultdict(Counter)
    train_frames: dict[str, set] = defaultdict(set)
    for source in report.sources:
        images = split_images(load_dataset_config(source.data_yaml), "train")
        for image in images:
            key, frame = image_sequence_key(image)
            train_counts[key][source.label] += 1
            train_frames[key].add(frame if frame is not None else image.stem)
    eval_config = load_dataset_config(rebase_repo_path(evaluation, root))
    for split in splits:
        eval_images = split_images(eval_config, split)
        if not eval_images:
            continue
        eval_counts = Counter(image_sequence_key(image)[0] for image in eval_images)
        eval_frames = sequence_frames(eval_images)
        report.eval_sequences[split] = len(eval_counts)
        report.leaks[split] = [
            {
                "sequence_key": key,
                "eval_frames": eval_counts[key],
                "train_frames": sum(train_counts[key].values()),
                "train_frames_by_source": dict(train_counts[key]),
                "shared_frame_ids": len(eval_frames[key] & train_frames[key]),
            }
            for key in sorted(eval_counts)
            if key in train_counts
        ]
    return report


def format_report(report: LeakageReport) -> str:
    lines = [f"Training: {report.training}", f"Evaluation: {report.evaluation}"]
    for source in report.sources:
        lines.append(f"  trained on [{source.label}] {source.data_yaml}")
    for item in report.unresolved:
        lines.append(f"  WARNING unverified {item}")
    for split, leaks in report.leaks.items():
        if not leaks:
            lines.append(f"  {split}: clean ({report.eval_sequences.get(split, 0)} sequences)")
            continue
        lines.append(f"  {split}: LEAKAGE in {len(leaks)}/{report.eval_sequences.get(split, 0)} sequences")
        for leak in leaks:
            lines.append(
                f"    {leak['sequence_key']}: eval={leak['eval_frames']} train={leak['train_frames']} "
                f"shared_frame_ids={leak['shared_frame_ids']}"
            )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--train",
        required=True,
        nargs="+",
        type=Path,
        help="training data.yaml, run args.yaml, or checkpoint; several are checked independently",
    )
    parser.add_argument("--eval", required=True, type=Path, help="evaluation data.yaml")
    parser.add_argument("--splits", nargs="+", default=["val", "test"], choices=("train", "val", "test"))
    parser.add_argument("--root", type=Path, default=None, help="repository root (default: $VIGIL_ROOT or this checkout)")
    parser.add_argument("--ancestor", nargs="*", type=Path, default=[], help="extra initialization checkpoints")
    parser.add_argument("--no-ancestors", action="store_true", help="ignore checkpoint lineage")
    parser.add_argument("--strict", action="store_true", help="fail when an ancestor's training data cannot be verified")
    parser.add_argument("--json", type=Path, help="write all reports to this JSON file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = (args.root or default_root()).expanduser().resolve()
    reports = [
        find_leaks(item, args.eval, tuple(args.splits), root, not args.no_ancestors, args.ancestor)
        for item in args.train
    ]
    for report in reports:
        print(format_report(report))
    if len(reports) > 1:
        print("\nSummary")
        for report in reports:
            leaked = sum(len(items) for items in report.leaks.values())
            status = "LEAK" if report.leaked else ("UNVERIFIED" if report.unresolved else "clean")
            print(f"  {status:10s} {leaked:2d} leaked sequence(s)  {report.training}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps([item.to_dict() for item in reports], indent=2) + "\n", encoding="utf-8")
    if any(report.leaked for report in reports):
        sys.exit(1)
    if args.strict and any(report.unresolved for report in reports):
        sys.exit(2)


if __name__ == "__main__":
    main()
