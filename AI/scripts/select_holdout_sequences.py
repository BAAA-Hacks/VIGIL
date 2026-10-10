#!/usr/bin/env python3
"""Select a deterministic, sequence-grouped locked test set for a YOLO dataset."""

from __future__ import annotations

import argparse
import itertools
import math
import random
from pathlib import Path

try:
    from AI.scripts.build_folds import SequenceStats, load_records
    from AI.scripts.dataset_utils import find_data_yaml, load_dataset_config, write_json
except ModuleNotFoundError:
    from AI.scripts.build_folds import SequenceStats, load_records  # type: ignore
    from AI.scripts.dataset_utils import (  # type: ignore
        find_data_yaml,
        load_dataset_config,
        write_json,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="source dataset root or data.yaml")
    parser.add_argument("output", type=Path, help="output sequence-name text file")
    parser.add_argument(
        "--fraction",
        type=float,
        default=0.10,
        help="approximate fraction reserved for the locked test set",
    )
    parser.add_argument("--seed", type=int, default=26)
    parser.add_argument("--report", type=Path, help="optional JSON selection report path")
    parser.add_argument("--exist-ok", action="store_true")
    return parser.parse_args()


def totals(items: list[SequenceStats]) -> dict[str, int]:
    return {
        "sequences": len(items),
        "images": sum(item.image_count for item in items),
        "annotations": sum(item.annotations for item in items),
        "tiny_annotations": sum(item.tiny_annotations for item in items),
    }


def choose_holdout(
    sequences: dict[str, SequenceStats], fraction: float, seed: int
) -> tuple[set[str], dict]:
    """Choose whole videos whose aggregate statistics best match the requested share."""
    if not 0.0 < fraction < 0.5:
        raise ValueError("holdout fraction must be greater than 0 and less than 0.5")
    if len(sequences) < 3:
        raise ValueError("Need at least three source sequences to create a locked holdout")
    all_items = list(sequences.values())
    overall = totals(all_items)
    targets = {metric: value * fraction for metric, value in overall.items()}
    holdout_count = min(len(sequences) - 2, max(1, round(len(sequences) * fraction)))
    names = sorted(sequences)
    possible_combinations = math.comb(len(names), holdout_count)
    exhaustive_limit = 100_000
    random_trials = 50_000
    if possible_combinations <= exhaustive_limit:
        candidates = itertools.combinations(names, holdout_count)
        search_method = "exhaustive"
        candidates_considered = possible_combinations
    else:
        rng = random.Random(seed)
        candidates = (
            tuple(sorted(rng.sample(names, holdout_count))) for _ in range(random_trials)
        )
        search_method = "seeded_random"
        candidates_considered = random_trials

    best: tuple[float, tuple[str, ...], dict[str, int]] | None = None
    for candidate in candidates:
        selected_totals = totals([sequences[name] for name in candidate])
        score = sum(
            ((selected_totals[metric] - targets[metric]) / max(targets[metric], 1.0)) ** 2
            for metric in ("images", "annotations", "tiny_annotations")
        )
        choice = (score, candidate, selected_totals)
        if best is None or choice[:2] < best[:2]:
            best = choice
    assert best is not None
    score, selected_names, selected_totals = best
    selected = set(selected_names)
    realized = {
        metric: round(selected_totals[metric] / value, 6) if value else None
        for metric, value in overall.items()
    }
    report = {
        "requested_fraction": fraction,
        "holdout_sequence_count": holdout_count,
        "selection_score": round(score, 8),
        "search_method": search_method,
        "candidates_considered": candidates_considered,
        "seed": seed,
        "dataset_totals": overall,
        "holdout_totals": selected_totals,
        "realized_fractions": realized,
        "holdout_sequences": sorted(selected),
        "selection_basis": ["sequences", "images", "annotations", "tiny_annotations"],
    }
    return selected, report


def main() -> None:
    args = parse_args()
    if not 0.0 < args.fraction < 0.5:
        raise SystemExit("--fraction must be greater than 0 and less than 0.5")
    output = args.output.expanduser().resolve()
    report_path = (
        args.report.expanduser().resolve()
        if args.report
        else output.with_suffix(".json")
    )
    existing = [path for path in (output, report_path) if path.exists()]
    if existing and not args.exist_ok:
        raise SystemExit(f"Refusing to overwrite existing output: {existing[0]}")

    yaml_path = find_data_yaml(args.dataset)
    sequences = load_records(load_dataset_config(yaml_path))
    try:
        selected, report = choose_holdout(sequences, args.fraction, args.seed)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    report["dataset_yaml"] = str(yaml_path.resolve())
    report["output"] = str(output)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(sorted(selected)) + "\n", encoding="utf-8")
    write_json(report_path, report)
    print(f"Locked holdout sequence list: {output}")
    print(f"Selection report: {report_path}")
    print(
        f"  {report['holdout_totals']['sequences']} / "
        f"{report['dataset_totals']['sequences']} videos; "
        f"{report['holdout_totals']['images']} / "
        f"{report['dataset_totals']['images']} images"
    )


if __name__ == "__main__":
    main()
