#!/usr/bin/env python3
"""Evaluate YOLO26 weights and measure false positives on empty frames."""

from __future__ import annotations

import argparse
import math
import tempfile
import time
from pathlib import Path

try:
    from AI.scripts.dataset_utils import (
        chunks,
        find_data_yaml,
        label_path_for_image,
        load_dataset_config,
        read_yolo_labels,
        split_images,
        write_resolved_dataset_yaml,
        write_json,
    )
    from AI.scripts.model_utils import load_model, parse_device
except ModuleNotFoundError:
    from AI.scripts.dataset_utils import (  # type: ignore
        chunks,
        find_data_yaml,
        label_path_for_image,
        load_dataset_config,
        read_yolo_labels,
        split_images,
        write_resolved_dataset_yaml,
        write_json,
    )
    from AI.scripts.model_utils import load_model, parse_device  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path, help="Dataset root or data.yaml")
    parser.add_argument("--split", choices=("val", "test"), default="test")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--device", default="0")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--person-class", default="person")
    parser.add_argument("--empty-conf", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.7)
    parser.add_argument("--output", type=Path, default=Path("evaluation.json"))
    return parser.parse_args()


def finite_float(value) -> float | None:
    number = float(value)
    return round(number, 6) if math.isfinite(number) else None


def person_metrics(metrics, class_id: int) -> dict:
    box = getattr(metrics, "box", None)
    if box is None:
        raise RuntimeError("Ultralytics did not return detection box metrics")
    class_indexes = [int(value) for value in getattr(box, "ap_class_index", [])]
    if class_id not in class_indexes:
        return {"precision": None, "recall": None, "map50": None, "map50_95": None}
    metric_index = class_indexes.index(class_id)
    return {
        "precision": finite_float(box.p[metric_index]),
        "recall": finite_float(box.r[metric_index]),
        "map50": finite_float(box.ap50[metric_index]),
        "map50_95": finite_float(box.ap[metric_index]),
    }


def empty_frame_metrics(
    model,
    images: list[Path],
    class_id: int,
    imgsz: int,
    device,
    confidence: float,
    iou: float,
    batch: int,
) -> dict:
    empty_images: list[Path] = []
    invalid_labels = 0
    for image in images:
        boxes, errors = read_yolo_labels(label_path_for_image(image))
        if errors:
            invalid_labels += 1
        elif not boxes:
            empty_images.append(image)

    false_positive_detections = 0
    frames_with_false_positives = 0
    processing_ms: list[float] = []
    started = time.perf_counter()
    for image_chunk in chunks(empty_images, max(1, batch)):
        results = model.predict(
            source=[str(path) for path in image_chunk],
            imgsz=imgsz,
            conf=confidence,
            iou=iou,
            device=device,
            stream=True,
            verbose=False,
        )
        for result in results:
            classes = [] if result.boxes is None else result.boxes.cls.detach().cpu().tolist()
            count = sum(1 for detected_class in classes if int(detected_class) == class_id)
            false_positive_detections += count
            frames_with_false_positives += int(count > 0)
            speed = getattr(result, "speed", {}) or {}
            processing_ms.append(
                sum(float(speed.get(key, 0.0) or 0.0) for key in ("preprocess", "inference", "postprocess"))
            )
    wall_ms = (time.perf_counter() - started) * 1000.0
    empty_count = len(empty_images)
    return {
        "confidence_threshold": confidence,
        "empty_frames": empty_count,
        "invalid_label_frames_excluded": invalid_labels,
        "frames_with_false_positives": frames_with_false_positives,
        "false_positive_detections": false_positive_detections,
        "false_positive_frame_rate": (
            round(frames_with_false_positives / empty_count, 6) if empty_count else None
        ),
        "mean_pipeline_ms_per_frame": (
            round(sum(processing_ms) / len(processing_ms), 3) if processing_ms else None
        ),
        "wall_ms_per_frame": round(wall_ms / empty_count, 3) if empty_count else None,
    }


def main() -> None:
    args = parse_args()
    if args.imgsz <= 0 or args.batch <= 0 or args.workers < 0:
        raise SystemExit("imgsz/batch must be positive and workers cannot be negative")
    if not 0.0 <= args.empty_conf <= 1.0 or not 0.0 <= args.iou <= 1.0:
        raise SystemExit("confidence and IoU thresholds must be between 0 and 1")

    yaml_path = find_data_yaml(args.data)
    config = load_dataset_config(yaml_path)
    person_ids = [
        class_id
        for class_id, name in config.names.items()
        if name.strip().casefold() == args.person_class.strip().casefold()
    ]
    if len(person_ids) != 1:
        raise SystemExit(
            f"Expected exactly one {args.person_class!r} class, found {person_ids}; names={config.names}"
        )
    person_id = person_ids[0]
    images = split_images(config, args.split)
    if not images:
        raise SystemExit(f"Dataset split {args.split!r} is missing or empty")

    device = parse_device(args.device)
    model = load_model(args.weights)
    with tempfile.TemporaryDirectory(prefix="vigil-eval-") as temporary_directory:
        runtime_yaml = write_resolved_dataset_yaml(
            config, Path(temporary_directory) / "data.yaml"
        )
        metrics = model.val(
            data=str(runtime_yaml),
            split=args.split,
            imgsz=args.imgsz,
            batch=args.batch,
            device=device,
            workers=args.workers,
            plots=False,
            verbose=False,
        )
    speed = getattr(metrics, "speed", {}) or {}
    report = {
        "weights": str(args.weights.expanduser().resolve()),
        "dataset_yaml": str(yaml_path),
        "split": args.split,
        "images": len(images),
        "person_class_id": person_id,
        "person_metrics": person_metrics(metrics, person_id),
        "validation_speed_ms_per_image": {
            str(key): round(float(value), 3) for key, value in speed.items()
        },
        "empty_frame_metrics": empty_frame_metrics(
            model,
            images,
            person_id,
            args.imgsz,
            device,
            args.empty_conf,
            args.iou,
            args.batch,
        ),
    }
    write_json(args.output, report)
    print(f"Evaluation report: {args.output.expanduser().resolve()}")
    print(f"Person metrics: {report['person_metrics']}")
    print(f"Empty-frame metrics: {report['empty_frame_metrics']}")


if __name__ == "__main__":
    main()
