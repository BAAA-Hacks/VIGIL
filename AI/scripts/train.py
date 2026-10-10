#!/usr/bin/env python3
"""Fine-tune a required YOLO26 checkpoint on a VIGIL dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    from AI.scripts.dataset_utils import (
        find_data_yaml,
        load_dataset_config,
        split_images,
        write_resolved_dataset_yaml,
    )
    from AI.scripts.model_utils import load_model, parse_device
except ModuleNotFoundError:
    from AI.scripts.dataset_utils import (  # type: ignore
        find_data_yaml,
        load_dataset_config,
        split_images,
        write_resolved_dataset_yaml,
    )
    from AI.scripts.model_utils import load_model, parse_device  # type: ignore


def parse_batch(value: str) -> int | float:
    """Parse a fixed batch size or an AutoBatch GPU-memory fraction."""
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("batch must be -1, a positive integer, or a fraction") from exc
    if number == -1:
        return -1
    if 0 < number < 1:
        return number
    if number >= 1 and number.is_integer():
        return int(number)
    raise argparse.ArgumentTypeError(
        "batch must be -1, a positive integer, or a GPU-memory fraction between 0 and 1"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path, help="Dataset root or data.yaml")
    parser.add_argument("--model", default="yolo26s.pt")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument(
        "--batch",
        type=parse_batch,
        default=-1,
        help="fixed batch size, -1 for automatic 60%% VRAM, or a fraction such as 0.85",
    )
    parser.add_argument("--device", default="0")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--project", type=Path, default=Path("models/runs"))
    parser.add_argument("--name", default="yolo26s_wisard")
    parser.add_argument("--freeze", type=int, default=0, help="Freeze the first N model layers")
    parser.add_argument("--optimizer", default="auto")
    parser.add_argument("--lr0", type=float, default=None)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--mosaic", type=float, default=0.0)
    parser.add_argument("--mixup", type=float, default=0.0)
    parser.add_argument(
        "--scale",
        type=float,
        default=0.5,
        help="random training scale gain; reduce this for very small native images",
    )
    parser.add_argument("--seed", type=int, default=26)
    parser.add_argument(
        "--epoch-fraction",
        type=float,
        default=1.0,
        help=(
            "fresh fraction of train images sampled each epoch; preserves the global "
            "positive/negative ratio and balances source sequences"
        ),
    )
    parser.add_argument("--cache", action="store_true")
    parser.add_argument("--exist-ok", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.epochs <= 0 or args.imgsz <= 0 or args.workers < 0:
        raise SystemExit("epochs/imgsz must be positive and workers cannot be negative")
    if args.freeze < 0:
        raise SystemExit("--freeze cannot be negative")
    if not 0.0 <= args.mosaic <= 1.0 or not 0.0 <= args.mixup <= 1.0:
        raise SystemExit("--mosaic and --mixup must be between 0 and 1")
    if not 0.0 <= args.scale <= 1.0:
        raise SystemExit("--scale must be between 0 and 1")
    if not 0.0 < args.epoch_fraction <= 1.0:
        raise SystemExit("--epoch-fraction must be in (0, 1]")

    yaml_path = find_data_yaml(args.data)
    config = load_dataset_config(yaml_path)
    train_count = len(split_images(config, "train"))
    val_count = len(split_images(config, "val"))
    if not train_count or not val_count:
        raise SystemExit("Both train and val splits must contain images")

    project = args.project.expanduser().resolve()
    runtime_yaml = write_resolved_dataset_yaml(
        config, project / "dataset_yamls" / f"{args.name}.yaml"
    )

    model = load_model(args.model)
    settings = {
        "data": str(runtime_yaml),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "device": parse_device(args.device),
        "workers": args.workers,
        "project": str(project),
        "name": args.name,
        "freeze": args.freeze,
        "optimizer": args.optimizer,
        "patience": args.patience,
        "mosaic": args.mosaic,
        "mixup": args.mixup,
        "scale": args.scale,
        "seed": args.seed,
        "cache": args.cache,
        "exist_ok": args.exist_ok,
        "plots": True,
    }
    if args.lr0 is not None:
        if args.optimizer.lower() == "auto":
            raise SystemExit("Ultralytics ignores --lr0 with optimizer=auto; select an optimizer")
        settings["lr0"] = args.lr0

    sampled_count = max(1, round(train_count * args.epoch_fraction))
    print(
        f"Training pool: {train_count} images; sampling {sampled_count} per epoch "
        f"({args.epoch_fraction:.1%}); validating on all {val_count} images"
    )
    print(f"Model: {args.model}; freeze={args.freeze}; device={args.device}")
    if args.epoch_fraction < 1.0:
        from AI.scripts.epoch_sampler import make_resampled_detection_trainer

        trainer = make_resampled_detection_trainer(args.epoch_fraction, args.seed)
        model.train(trainer=trainer, **settings)
    else:
        model.train(**settings)


if __name__ == "__main__":
    main()
