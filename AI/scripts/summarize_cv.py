#!/usr/bin/env python3
"""Summarize person metrics from multiple VIGIL fold evaluation reports."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
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


def safe_ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None or precision + recall == 0:
        return None
    return round(2 * precision * recall / (precision + recall), 6)


def pool_confidence_curves(reports: list[tuple[Path, dict]]) -> list[dict]:
    pooled: dict[float, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    count_keys = (
        "tp_frames",
        "fp_frames",
        "fn_frames",
        "tn_frames",
        "ground_truth_instances",
        "predicted_instances",
        "matched_instances",
    )
    for _, report in reports:
        for row in report.get("confidence_curve", []):
            threshold = round(float(row["confidence_threshold"]), 6)
            for key in count_keys:
                pooled[threshold][key] += int(row[key])

    output = []
    for threshold, counts in sorted(pooled.items()):
        precision = safe_ratio(counts["tp_frames"], counts["tp_frames"] + counts["fp_frames"])
        recall = safe_ratio(counts["tp_frames"], counts["tp_frames"] + counts["fn_frames"])
        detection_precision = safe_ratio(
            counts["matched_instances"], counts["predicted_instances"]
        )
        detection_recall = safe_ratio(
            counts["matched_instances"], counts["ground_truth_instances"]
        )
        output.append(
            {
                "confidence_threshold": threshold,
                **dict(counts),
                "precision": precision,
                "recall": recall,
                "f1": f1(precision, recall),
                "relaxed_detection_precision": detection_precision,
                "relaxed_detection_recall": detection_recall,
                "relaxed_detection_f1": f1(detection_precision, detection_recall),
            }
        )
    return output


def choose_operating_points(curve: list[dict]) -> dict:
    def best(metric: str, candidates: list[dict]) -> dict | None:
        usable = [row for row in candidates if row[metric] is not None]
        return max(usable, key=lambda row: (row[metric], row["confidence_threshold"])) if usable else None

    return {
        "maximum_frame_f1": best("f1", curve),
        "maximum_relaxed_detection_f1": best("relaxed_detection_f1", curve),
        "maximum_frame_recall_at_precision_gte_0_98": best(
            "recall", [row for row in curve if (row["precision"] or 0.0) >= 0.98]
        ),
        "maximum_frame_precision_at_recall_gte_0_95": best(
            "precision", [row for row in curve if (row["recall"] or 0.0) >= 0.95]
        ),
    }


def pool_temporal(reports: list[tuple[Path, dict]]) -> dict:
    output = {}
    for mode in ("raw", "relaxed_match", "smoothed"):
        blocks = [report["temporal_metrics"][mode] for _, report in reports]
        positive_frames = sum(block["positive_frames"] for block in blocks)
        detected_frames = sum(block["positive_frames_detected"] for block in blocks)
        events = sum(block["events"] for block in blocks)
        detected_events = sum(block["detected_events"] for block in blocks)
        mode_output = {
            "positive_frames": positive_frames,
            "positive_frames_detected": detected_frames,
            "coverage": safe_ratio(detected_frames, positive_frames),
            "events": events,
            "detected_events": detected_events,
            "event_recall": safe_ratio(detected_events, events),
            "longest_miss_streak_frames": max(
                block["longest_miss_streak_frames"] for block in blocks
            ),
        }
        if mode in {"raw", "smoothed"}:
            mode_output["false_alert_episodes"] = sum(
                block["false_alert_episodes"] for block in blocks
            )
        if mode == "smoothed":
            mode_output["window"] = blocks[0]["window"]
            mode_output["minimum_hits"] = blocks[0]["minimum_hits"]
        output[mode] = mode_output
    return output


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
    if all("frame_presence_and_relaxed_matching" in data for _, data in reports):
        frame_keys = (
            "precision",
            "recall",
            "f1",
            "relaxed_frame_recall",
            "relaxed_detection_precision",
            "relaxed_detection_recall",
            "relaxed_detection_f1",
        )
        output["frame_metrics_unweighted"] = {
            key: summarize(
                [float(data["frame_presence_and_relaxed_matching"][key]) for _, data in reports]
            )
            for key in frame_keys
            if all(data["frame_presence_and_relaxed_matching"][key] is not None for _, data in reports)
        }
        pooled_curve = pool_confidence_curves(reports)
        output["out_of_fold_confidence_curve"] = pooled_curve
        output["global_operating_points"] = choose_operating_points(pooled_curve)
    if all("temporal_metrics" in data for _, data in reports):
        output["temporal_metrics_pooled"] = pool_temporal(reports)
    write_json(args.output, output)
    print(f"Cross-validation summary: {args.output.expanduser().resolve()}")
    for key, summary in metrics.items():
        print(f"  {key}: {summary['mean']:.6f} +/- {summary['std']:.6f}")
    print(f"  pooled empty-frame FP rate: {output['empty_frames_pooled']['false_positive_frame_rate']}")


if __name__ == "__main__":
    main()
