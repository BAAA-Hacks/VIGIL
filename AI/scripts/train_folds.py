#!/usr/bin/env python3
"""Train one recipe on every cross-validation fold, skipping folds that already have weights.

The default recipe reproduces ``thermal_medium_range_yolo26s_p2``: a YOLO26s base fine-tuned on
the medium-crop fold, whose weights are transferred into ``yolo26s-p2.yaml`` and fine-tuned on
the medium-range fold. Every path is relative to ``--root`` so the launcher runs on any checkout.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

try:
    from AI.scripts.check_leakage import find_leaks, format_report
    from AI.scripts.portable_paths import default_root, portable_dataset_yaml
except ModuleNotFoundError:
    from AI.scripts.check_leakage import find_leaks, format_report  # type: ignore
    from AI.scripts.portable_paths import default_root, portable_dataset_yaml  # type: ignore


# Recovered from thermal_medium_range_yolo26s_p2/args.yaml and results.csv: best.pt fitness equals
# presence F1 and the epoch-1 warmup LR implies 538 batches of 21, i.e. --epoch-fraction 0.20.
P2_STAGE_ARGS = [
    "--epochs", "50", "--patience", "25", "--batch", "0.85", "--imgsz", "640",
    "--optimizer", "AdamW", "--lr0", "0.001", "--scale", "0.25", "--seed", "26",
    "--epoch-fraction", "0.20", "--selection-metric", "presence_f1", "--presence-conf", "0.40",
]
# Recovered from AI/checkpoints/thermal_mega_medium_crop_fold0_best.pt train_args (batch 36 there was
# AutoBatch on the other machine; warmup LR implies 247 batches of 36, i.e. --epoch-fraction 0.20).
BASE_STAGE_ARGS = [
    "--epochs", "50", "--patience", "50", "--batch", "0.8", "--imgsz", "640",
    "--optimizer", "AdamW", "--lr0", "0.001", "--scale", "0.25", "--seed", "26",
    "--epoch-fraction", "0.20",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Arguments after '--' are appended to every main-stage train.py call and override defaults.",
    )
    parser.add_argument("--root", type=Path, default=None, help="repository root (default: $VIGIL_ROOT or this checkout)")
    parser.add_argument("--folds", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    parser.add_argument("--dataset", default="AI/datasets/thermal_mega_5fold_lepton_medium_range")
    parser.add_argument("--model", default="yolo26s-p2.yaml")
    parser.add_argument("--name", default="thermal_medium_range_yolo26s_p2_fold{fold}", help="run name; {fold} is substituted")
    parser.add_argument("--project", default="AI/models/runs")
    parser.add_argument(
        "--init",
        default="AI/models/runs/{base_name}/weights/best.pt",
        help="--pretrained-weights per fold ({fold}, {base_name} substituted); 'none' to train from --model alone",
    )
    parser.add_argument("--no-base-stage", action="store_true", help="fail instead of training missing init weights")
    parser.add_argument("--base-dataset", default="AI/datasets/thermal_mega_5fold_lepton_medium_crops")
    parser.add_argument("--base-model", default="yolo26s.pt")
    parser.add_argument("--base-name", default="thermal_mega_medium_crop_fold_{fold}")
    parser.add_argument("--device", default="0")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--no-recipe-defaults", action="store_true", help="pass only the extra arguments to train.py")
    parser.add_argument("--dry-run", action="store_true")
    args, extra = parser.parse_known_args()
    args.extra = [item for item in extra if item != "--"]
    return args


def run_state(run_dir: Path) -> str:
    if (run_dir / "weights" / "best.pt").is_file():
        return "done"
    return "incomplete" if run_dir.exists() else "missing"


def fold_yaml(root: Path, dataset: str, fold: int) -> Path:
    source = root / dataset / f"fold_{fold}" / "data.yaml"
    cache = root / "AI" / "models" / "runs" / "portable_yamls" / Path(dataset).name / f"fold_{fold}"
    return portable_dataset_yaml(source, root, cache)


def train_command(
    args: argparse.Namespace, data: Path, model: str, name: str, stage_args: list[str], init: Path | None
) -> list[str]:
    command = [
        args.python, "-m", "AI.scripts.train", "--data", str(data), "--model", model, "--name", name,
        "--project", str(args.root / args.project), "--device", args.device,
    ]
    if init is not None:
        command += ["--pretrained-weights", str(init)]
    return command + stage_args


def launch(command: list[str], root: Path, run_dir: Path, lineage: dict, dry_run: bool) -> None:
    print("$ " + shlex.join(command), flush=True)
    if dry_run:
        return
    subprocess.run(command, cwd=root, check=True)
    if not (run_dir / "weights" / "best.pt").is_file():
        raise SystemExit(f"Training finished without {run_dir}/weights/best.pt (Ultralytics may have renamed the run)")
    (run_dir / "vigil_lineage.json").write_text(json.dumps(lineage, indent=2) + "\n", encoding="utf-8")


def guard_fold(data: Path, root: Path) -> None:
    report = find_leaks(data, data, ("val", "test"), root, follow_ancestors=False)
    if report.leaked:
        print(format_report(report))
        raise SystemExit(f"Fold dataset {data} leaks evaluation sequences into train")


def ensure_base(args: argparse.Namespace, fold: int) -> tuple[Path | None, str | None]:
    if args.init.lower() == "none":
        return None, None
    base_name = args.base_name.format(fold=fold)
    init = args.root / args.init.format(fold=fold, base_name=base_name)
    if init.is_file():
        return init, base_name
    base_dir = args.root / args.project / base_name
    if args.no_base_stage or init.parent.parent != base_dir:
        raise SystemExit(f"Initialization weights missing for fold {fold}: {init}")
    if run_state(base_dir) == "incomplete":
        raise SystemExit(f"{base_dir} exists without weights/best.pt; resume or remove it before relaunching")
    data = fold_yaml(args.root, args.base_dataset, fold)
    guard_fold(data, args.root)
    command = train_command(args, data, args.base_model, base_name, BASE_STAGE_ARGS, None)
    lineage = {"fold": fold, "stage": "base", "data": str(data), "pretrained_weights": None, "command": command}
    launch(command, args.root, base_dir, lineage, args.dry_run)
    return init, base_name


def main() -> None:
    args = parse_args()
    args.root = (args.root or default_root()).expanduser().resolve()
    stage_args = ([] if args.no_recipe_defaults else list(P2_STAGE_ARGS)) + args.extra
    for fold in args.folds:
        name = args.name.format(fold=fold)
        run_dir = args.root / args.project / name
        state = run_state(run_dir)
        if state == "done":
            print(f"fold {fold}: {run_dir}/weights/best.pt exists; skipping")
            continue
        if state == "incomplete":
            print(f"fold {fold}: {run_dir} exists without best.pt; resume or remove it. Skipping.")
            continue
        data = fold_yaml(args.root, args.dataset, fold)
        guard_fold(data, args.root)
        init, base_name = ensure_base(args, fold)
        command = train_command(args, data, args.model, name, stage_args, init)
        lineage = {
            "fold": fold,
            "stage": "main",
            "data": str(data),
            "pretrained_weights": str(init) if init else None,
            "base_run": base_name,
            "command": command,
        }
        launch(command, args.root, run_dir, lineage, args.dry_run)


if __name__ == "__main__":
    main()
