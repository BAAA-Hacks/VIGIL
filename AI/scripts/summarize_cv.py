#!/usr/bin/env python3
"""Summarize person metrics from multiple VIGIL fold evaluation reports."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

try:
    from AI.scripts.dataset_utils import write_json
except ModuleNotFoundError:
    from AI.scripts.dataset_utils import write_json  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports/cv_summary.json"))
    return parser.parse_args()


def summarize(values: list[float]) -> dict:
    return {
        "mean": round(statistics.fmean(values), 6),
        "std": round(statistics.pstdev(values), 6),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "fold_values": [round(value, 6) for value in values],
    }


def main() -> None:
    args = parse_args()
    reports = []
    for path in args.reports:
        resolved = path.expanduser().resolve()
        reports.append((resolved, json.loads(resolved.read_text(encoding="utf-8"))))
    if len(reports) < 2:
        raise SystemExit("At least two fold reports are required")

    metrics = {}
    for key in ("precision", "recall", "map50", "map50_95"):
        values = [data["person_metrics"].get(key) for _, data in reports]
        if any(value is None for value in values):
            raise SystemExit(f"Metric {key!r} is missing from one or more reports")
        metrics[key] = summarize([float(value) for value in values])

    empty_frames = sum(data["empty_frame_metrics"]["empty_frames"] for _, data in reports)
    fp_frames = sum(
        data["empty_frame_metrics"]["frames_with_false_positives"] for _, data in reports
    )
    fp_detections = sum(
        data["empty_frame_metrics"]["false_positive_detections"] for _, data in reports
    )
    output = {
        "fold_count": len(reports),
        "reports": [str(path) for path, _ in reports],
        "person_metrics_unweighted": metrics,
        "empty_frames_pooled": {
            "empty_frames": empty_frames,
            "frames_with_false_positives": fp_frames,
            "false_positive_detections": fp_detections,
            "false_positive_frame_rate": round(fp_frames / empty_frames, 6) if empty_frames else None,
        },
        "note": (
            "Person metrics are the unweighted mean and population standard deviation across "
            "sequence-grouped folds; AP is not recomputed from pooled predictions."
        ),
    }
    write_json(args.output, output)
    print(f"Cross-validation summary: {args.output.expanduser().resolve()}")
    for key, summary in metrics.items():
        print(f"  {key}: {summary['mean']:.6f} +/- {summary['std']:.6f}")
    print(f"  pooled empty-frame FP rate: {output['empty_frames_pooled']['false_positive_frame_rate']}")


if __name__ == "__main__":
    main()
