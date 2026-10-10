#!/usr/bin/env python3
"""Cross-validated benchmark: mean +/- std over the five fold val sets, plus the locked test check."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path

try:
    from AI.scripts.check_leakage import find_leaks, format_report, sequence_key
    from AI.scripts.portable_paths import default_root, portable_dataset_yaml
except ModuleNotFoundError:
    from AI.scripts.check_leakage import find_leaks, format_report, sequence_key  # type: ignore
    from AI.scripts.portable_paths import default_root, portable_dataset_yaml  # type: ignore


# Labelled all-negative, but the frames show an unlabelled person (AI/BENCHMARK.md, audit).
DEFAULT_FLAGGED = ["dji_0585"]
METRICS = (
    ("presence_f1", "F1", True),
    ("presence_recall", "recall", True),
    ("presence_precision", "precision", True),
    ("specificity", "specificity", True),
    ("map50", "mAP50", True),
    ("map50_95", "mAP50-95", True),
    ("event_recall", "event recall", True),
    ("false_alert_episodes", "false alerts", False),
    ("false_alerts_per_1k_neg", "FA / 1k neg frames", False),
    ("longest_miss", "longest miss (frames)", False),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", required=True, help="run-name pattern with {fold}, e.g. thermal_medium_range_yolo26s_p2_fold{fold}")
    parser.add_argument(
        "--fold-run",
        nargs="*",
        default=[],
        metavar="FOLD=RUN",
        help="per-fold override: a run name under --project or a path to weights",
    )
    parser.add_argument("--label", default=None, help="report directory name (default: pattern without {fold})")
    parser.add_argument("--root", type=Path, default=None, help="repository root (default: $VIGIL_ROOT or this checkout)")
    parser.add_argument("--dataset", default="AI/datasets/thermal_mega_5fold_lepton_medium_range")
    parser.add_argument("--project", default="AI/models/runs")
    parser.add_argument("--folds", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    parser.add_argument("--weights", default="best.pt")
    parser.add_argument("--presence-conf", type=float, default=0.40)
    parser.add_argument("--device", default="0")
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--reports-dir", default="AI/reports/benchmark")
    parser.add_argument("--flag-sequence", nargs="*", default=DEFAULT_FLAGGED, help="sequence keys shown in a second, excluded column")
    parser.add_argument("--ancestor", nargs="*", type=Path, default=[], help="extra init checkpoints for the leakage guard")
    parser.add_argument("--allow-leakage", action="store_true", help="report leaked folds (flagged) instead of skipping them")
    parser.add_argument("--python", default=sys.executable)
    return parser.parse_args()


def resolve_weights(args: argparse.Namespace, fold: int) -> tuple[Path, Path | None]:
    overrides = dict(item.split("=", 1) for item in args.fold_run)
    target = overrides.get(str(fold), args.runs.format(fold=fold))
    candidate = args.root / target if not Path(target).is_absolute() else Path(target)
    if candidate.suffix == ".pt":
        args_yaml = candidate.parent.parent / "args.yaml"
        return candidate, args_yaml if args_yaml.is_file() else None
    run_dir = args.root / args.project / target
    return run_dir / "weights" / args.weights, run_dir / "args.yaml"


def run_evaluation(args: argparse.Namespace, weights: Path, data: Path, split: str, output: Path) -> dict:
    if not output.is_file():
        command = [
            args.python, "-m", "AI.scripts.evaluate", "--weights", str(weights), "--data", str(data),
            "--split", split, "--presence-conf", str(args.presence_conf), "--device", args.device,
            "--batch", str(args.batch), "--output", str(output),
        ]
        print("$ " + " ".join(command), flush=True)
        with output.with_suffix(".log").open("w", encoding="utf-8") as log:
            subprocess.run(command, cwd=args.root, check=True, stdout=log, stderr=subprocess.STDOUT)
    else:
        print(f"  reusing {output}")
    return json.loads(output.read_text(encoding="utf-8"))


def ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def summarize(report: dict, excluded: set[str]) -> dict:
    """Pool per-video counts so metrics can be recomputed with flagged sequences removed."""
    videos = {
        name: item for name, item in report["per_video_metrics"].items() if sequence_key(name) not in excluded
    }
    counts = {key: sum(item["frame_metrics"][key] for item in videos.values()) for key in ("tp_frames", "fp_frames", "fn_frames", "tn_frames")}
    tp, fp, fn, tn = (counts[key] for key in ("tp_frames", "fp_frames", "fn_frames", "tn_frames"))
    precision, recall = ratio(tp, tp + fp), ratio(tp, tp + fn)
    smoothed = [item["temporal"]["smoothed"] for item in videos.values()]
    events = sum(item["events"] for item in smoothed)
    false_alerts = sum(item["false_alert_episodes"] for item in smoothed)
    negatives = fp + tn
    full = not excluded or len(videos) == len(report["per_video_metrics"])
    person = report["person_metrics"]
    return {
        "videos": len(videos),
        "positive_frames": tp + fn,
        "negative_frames": negatives,
        "tp_frames": tp, "fp_frames": fp, "fn_frames": fn, "tn_frames": tn,
        "presence_precision": precision,
        "presence_recall": recall,
        "presence_f1": ratio(2 * precision * recall, precision + recall) if precision and recall else None,
        "specificity": ratio(tn, negatives),
        # Box mAP comes from Ultralytics over the whole split and cannot be split per video.
        "map50": person["map50"] if full else None,
        "map50_95": person["map50_95"] if full else None,
        "events": events,
        "detected_events": sum(item["detected_events"] for item in smoothed),
        "event_recall": ratio(sum(item["detected_events"] for item in smoothed), events),
        "false_alert_episodes": false_alerts,
        "false_alerts_per_1k_neg": 1000 * false_alerts / negatives if negatives else None,
        "longest_miss": max((item["longest_miss_streak_frames"] for item in smoothed), default=0),
    }


def mean_std(values: list[float | None]) -> dict:
    usable = [value for value in values if value is not None and math.isfinite(value)]
    return {
        "n": len(usable),
        "mean": statistics.fmean(usable) if usable else None,
        "std": statistics.stdev(usable) if len(usable) > 1 else None,
        "values": values,
    }


def pooled(rows: list[dict]) -> dict:
    tp, fp, fn, tn = (sum(row[key] for row in rows) for key in ("tp_frames", "fp_frames", "fn_frames", "tn_frames"))
    precision, recall = ratio(tp, tp + fp), ratio(tp, tp + fn)
    events = sum(row["events"] for row in rows)
    negatives = fp + tn
    false_alerts = sum(row["false_alert_episodes"] for row in rows)
    return {
        "presence_precision": precision,
        "presence_recall": recall,
        "presence_f1": ratio(2 * precision * recall, precision + recall) if precision and recall else None,
        "specificity": ratio(tn, negatives),
        "event_recall": ratio(sum(row["detected_events"] for row in rows), events),
        "false_alert_episodes": false_alerts,
        "false_alerts_per_1k_neg": 1000 * false_alerts / negatives if negatives else None,
        "longest_miss": max((row["longest_miss"] for row in rows), default=None),
        "map50": None,
        "map50_95": None,
    }


def per_sequence_rows(report: dict, fold: int, flagged: set[str]) -> list[dict]:
    rows = []
    for name, item in report["per_video_metrics"].items():
        frame, smoothed = item["frame_metrics"], item["temporal"]["smoothed"]
        rows.append({
            "sequence": name,
            "fold": fold,
            "flagged": sequence_key(name) in flagged,
            "positive_frames": frame["positive_frames"],
            "negative_frames": frame["negative_frames"],
            "recall": frame["recall"],
            "specificity": frame["specificity"],
            "event_recall": smoothed["event_recall"],
            "false_alert_episodes": smoothed["false_alert_episodes"],
            "longest_miss": smoothed["longest_miss_streak_frames"],
        })
    return rows


def fmt(value: float | int | None) -> str:
    if value is None:
        return "-"
    return str(value) if isinstance(value, int) else f"{value:.3f}"


def cell(stats: dict, integer: bool) -> str:
    if stats["mean"] is None:
        return "n/a"
    digits = 1 if integer else 3
    std = f" ± {stats['std']:.{digits}f}" if stats["std"] is not None else " (n=1)"
    return f"{stats['mean']:.{digits}f}{std}"


def markdown(summary: dict) -> str:
    lines = [f"# Benchmark: {summary['label']}", ""]
    lines.append(f"Folds evaluated: {summary['folds_evaluated']} of {summary['folds_requested']}; "
                 f"missing: {summary['folds_missing'] or 'none'}; leaked: {summary['folds_leaked'] or 'none'}")
    lines.append(f"Val sequences covered: {summary['val_sequences_covered']} (39 non-test sequences exist)")
    lines.append(f"Presence confidence {summary['presence_conf']}; flagged sequences: {', '.join(summary['flagged']) or 'none'}")
    lines.append("")
    lines.append("| metric | fold val, mean ± std | fold val, flagged excluded | pooled val (all folds) | pooled, flagged excluded | locked test, mean ± std |")
    lines.append("|---|---|---|---|---|---|")
    for key, title, _ in METRICS:
        integer = key in {"false_alert_episodes", "longest_miss"}
        agg = summary["aggregate"]
        pool_all = agg["val_pooled"]["all"].get(key)
        pool_excl = agg["val_pooled"]["excluded"].get(key)
        lines.append(
            f"| {title} | {cell(agg['val']['all'][key], integer)} | {cell(agg['val']['excluded'][key], integer)} | "
            f"{fmt(pool_all) if pool_all is not None else 'n/a'} | {fmt(pool_excl) if pool_excl is not None else 'n/a'} | "
            f"{cell(agg['test']['all'][key], integer)} |"
        )
    lines += [
        "",
        "Test caveat: the locked test is 2 sequences (1 positive event, 1 negative video), identical for every fold; "
        "its std reflects model variance only. mAP cannot be recomputed with sequences excluded.",
        "",
        "## Per-sequence (each sequence is val in exactly one fold)",
        "",
        "| sequence | fold | pos | neg | recall | specificity | event recall | false alerts | longest miss | flag |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    ordered = sorted(summary["per_sequence"], key=lambda row: (row["recall"] is None, row["recall"] or 0.0, -(row["false_alert_episodes"] or 0)))
    for row in ordered:
        lines.append(
            f"| {row['sequence']} | {row['fold']} | {row['positive_frames']} | {row['negative_frames']} | {fmt(row['recall'])} | "
            f"{fmt(row['specificity'])} | {fmt(row['event_recall'])} | {row['false_alert_episodes']} | {row['longest_miss']} | "
            f"{'FLAGGED' if row['flagged'] else ''} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    args.root = (args.root or default_root()).expanduser().resolve()
    flagged = {sequence_key(item) for item in args.flag_sequence}
    label = args.label or args.runs.replace("{fold}", "").strip("_-") or "benchmark"
    output_dir = args.root / args.reports_dir / label
    output_dir.mkdir(parents=True, exist_ok=True)
    folds: dict[int, dict] = {}
    missing, leaked = [], []
    for fold in args.folds:
        weights, args_yaml = resolve_weights(args, fold)
        print(f"fold {fold}: {weights}")
        if not weights.is_file():
            print("  missing weights; skipping")
            missing.append(fold)
            continue
        data = portable_dataset_yaml(
            args.root / args.dataset / f"fold_{fold}" / "data.yaml",
            args.root,
            args.root / args.project / "portable_yamls" / Path(args.dataset).name / f"fold_{fold}",
        )
        training = args_yaml if args_yaml and args_yaml.is_file() else weights
        guard = find_leaks(training, data, ("val", "test"), args.root, True, args.ancestor)
        print("  " + format_report(guard).replace("\n", "\n  "))
        if guard.leaked:
            leaked.append(fold)
            if not args.allow_leakage:
                print("  LEAKAGE: fold excluded (use --allow-leakage to report it flagged)")
                continue
        reports = {
            split: run_evaluation(args, weights, data, split, output_dir / f"fold{fold}_{split}.json")
            for split in ("val", "test")
        }
        folds[fold] = {
            "weights": str(weights),
            "leakage": guard.to_dict(),
            "val": {"all": summarize(reports["val"], set()), "excluded": summarize(reports["val"], flagged)},
            "test": {"all": summarize(reports["test"], set())},
            "per_sequence": per_sequence_rows(reports["val"], fold, flagged),
        }
    aggregate = {
        "val": {
            mode: {key: mean_std([item["val"][mode][key] for item in folds.values()]) for key, _, _ in METRICS}
            for mode in ("all", "excluded")
        },
        "test": {"all": {key: mean_std([item["test"]["all"][key] for item in folds.values()]) for key, _, _ in METRICS}},
        "val_pooled": {
            mode: pooled([item["val"][mode] for item in folds.values()]) if folds else {}
            for mode in ("all", "excluded")
        },
    }
    per_sequence = [row for item in folds.values() for row in item["per_sequence"]]
    summary = {
        "label": label,
        "runs": args.runs,
        "fold_overrides": args.fold_run,
        "presence_conf": args.presence_conf,
        "flagged": sorted(flagged),
        "folds_requested": args.folds,
        "folds_evaluated": sorted(folds),
        "folds_missing": missing,
        "folds_leaked": leaked,
        "val_sequences_covered": len(per_sequence),
        "aggregate": aggregate,
        "folds": folds,
        "per_sequence": per_sequence,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    text = markdown(summary)
    (output_dir / "summary.md").write_text(text, encoding="utf-8")
    print()
    print(text)
    print(f"Saved {output_dir / 'summary.json'} and summary.md")
    if leaked and not args.allow_leakage:
        sys.exit(1)


if __name__ == "__main__":
    main()
