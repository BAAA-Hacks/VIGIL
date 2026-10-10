#!/usr/bin/env python3
"""Evaluate YOLO26 with localization, frame-presence, and temporal metrics."""

from __future__ import annotations

import argparse
import math
import tempfile
import time
from collections import defaultdict
from pathlib import Path

try:
    from AI.scripts.dataset_utils import (
        chunks,
        find_data_yaml,
        label_path_for_image,
        load_dataset_config,
        read_yolo_labels,
        source_frame_id,
        split_images,
        write_json,
        write_resolved_dataset_yaml,
    )
    from AI.scripts.model_utils import load_model, parse_device, result_processing_ms
    from AI.scripts.temporal_metrics import (
        Detection,
        EvaluationFrame,
        frame_metrics,
        macro_average,
        sequence_metrics,
    )
except ModuleNotFoundError:
    from AI.scripts.dataset_utils import (  # type: ignore
        chunks,
        find_data_yaml,
        label_path_for_image,
        load_dataset_config,
        read_yolo_labels,
        source_frame_id,
        split_images,
        write_json,
        write_resolved_dataset_yaml,
    )
    from AI.scripts.model_utils import load_model, parse_device, result_processing_ms  # type: ignore
    from AI.scripts.temporal_metrics import (  # type: ignore
        Detection,
        EvaluationFrame,
        frame_metrics,
        macro_average,
        sequence_metrics,
    )


DEFAULT_THRESHOLDS = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path, help="Dataset root or data.yaml")
    parser.add_argument("--split", choices=("train", "val", "test"), default="test")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--device", default="0")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--person-class", default="person")
    parser.add_argument(
        "--presence-conf",
        "--empty-conf",
        dest="presence_conf",
        type=float,
        default=0.25,
        help="confidence threshold for frame and temporal metrics",
    )
    parser.add_argument(
        "--prediction-conf",
        type=float,
        default=0.001,
        help="minimum confidence retained for the threshold curve",
    )
    parser.add_argument("--iou", type=float, default=0.7, help="NMS IoU threshold")
    parser.add_argument("--match-iou", type=float, default=0.25)
    parser.add_argument(
        "--match-mode",
        choices=("iou", "center", "iou_or_center"),
        default="iou_or_center",
    )
    parser.add_argument("--temporal-window", type=int, default=3)
    parser.add_argument("--temporal-min-hits", type=int, default=2)
    parser.add_argument(
        "--thresholds", nargs="+", type=float, default=list(DEFAULT_THRESHOLDS)
    )
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


def yolo_box_xyxy(box) -> tuple[float, float, float, float]:
    return (
        max(0.0, box.x_center - box.width / 2.0),
        max(0.0, box.y_center - box.height / 2.0),
        min(1.0, box.x_center + box.width / 2.0),
        min(1.0, box.y_center + box.height / 2.0),
    )


def predict_frames(
    model,
    images: list[Path],
    person_id: int,
    imgsz: int,
    device,
    prediction_conf: float,
    nms_iou: float,
    batch: int,
) -> tuple[list[EvaluationFrame], dict]:
    frames: list[EvaluationFrame] = []
    processing_ms: list[float] = []
    started = time.perf_counter()
    for image_chunk in chunks(images, max(1, batch)):
        results = model.predict(
            source=[str(path) for path in image_chunk],
            imgsz=imgsz,
            conf=prediction_conf,
            iou=nms_iou,
            device=device,
            stream=True,
            verbose=False,
        )
        for image, result in zip(image_chunk, results, strict=True):
            labels, errors = read_yolo_labels(label_path_for_image(image))
            if errors:
                raise ValueError(f"Invalid label for {image}: {'; '.join(errors)}")
            ground_truth = tuple(
                yolo_box_xyxy(box) for box in labels if box.class_id == person_id
            )
            detections: list[Detection] = []
            if result.boxes is not None:
                normalized_boxes = result.boxes.xyxyn.detach().cpu().tolist()
                confidences = result.boxes.conf.detach().cpu().tolist()
                classes = result.boxes.cls.detach().cpu().tolist()
                for coordinates, confidence, class_value in zip(
                    normalized_boxes, confidences, classes, strict=True
                ):
                    if int(class_value) != person_id:
                        continue
                    detections.append(
                        Detection(
                            confidence=float(confidence),
                            box=tuple(float(value) for value in coordinates),  # type: ignore[arg-type]
                        )
                    )
            sequence, frame_number = source_frame_id(image)
            frames.append(
                EvaluationFrame(
                    image=image,
                    sequence=sequence,
                    frame_number=frame_number,
                    derived_negative="_negative" in image.stem.casefold(),
                    ground_truth=ground_truth,
                    detections=tuple(detections),
                )
            )
            processing_ms.append(result_processing_ms(result))
    wall_ms = (time.perf_counter() - started) * 1000.0
    return frames, {
        "minimum_prediction_confidence": prediction_conf,
        "mean_pipeline_ms_per_frame": (
            round(sum(processing_ms) / len(processing_ms), 3) if processing_ms else None
        ),
        "wall_ms_per_frame": round(wall_ms / len(frames), 3) if frames else None,
    }


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


def pooled_temporal_metrics(per_video: dict[str, dict]) -> dict:
    output: dict[str, object] = {
        "videos": len(per_video),
        "timeline_frames": sum(item["temporal"]["timeline_frames"] for item in per_video.values()),
        "synthetic_negative_crops_excluded": sum(
            item["temporal"]["synthetic_negative_crops_excluded"] for item in per_video.values()
        ),
        "note": "All frame durations are measured in observed original frames, not seconds.",
    }
    for mode in ("raw", "relaxed_match", "smoothed"):
        positive_frames = sum(item["temporal"]["positive_frames"] for item in per_video.values())
        detected_frames = sum(
            item["temporal"][mode]["positive_frames_detected"] for item in per_video.values()
        )
        events = sum(item["temporal"][mode]["events"] for item in per_video.values())
        detected_events = sum(
            item["temporal"][mode]["detected_events"] for item in per_video.values()
        )
        mode_output = {
            "positive_frames": positive_frames,
            "positive_frames_detected": detected_frames,
            "coverage": round(detected_frames / positive_frames, 6) if positive_frames else None,
            "macro_video_coverage": macro_average(per_video, ("temporal", mode, "coverage")),
            "longest_miss_streak_frames": max(
                (item["temporal"][mode]["longest_miss_streak_frames"] for item in per_video.values()),
                default=0,
            ),
            "events": events,
            "detected_events": detected_events,
            "event_recall": round(detected_events / events, 6) if events else None,
            "macro_video_event_recall": macro_average(
                per_video, ("temporal", mode, "event_recall")
            ),
        }
        delays = [
            detail["time_to_first_detection_frames"]
            for item in per_video.values()
            for detail in item["temporal"][mode]["details"]
            if detail["time_to_first_detection_frames"] is not None
        ]
        mode_output["mean_time_to_first_detection_frames"] = (
            round(sum(delays) / len(delays), 3) if delays else None
        )
        mode_output["worst_time_to_first_detection_frames"] = max(delays, default=None)
        if mode in {"raw", "smoothed"}:
            mode_output["false_alert_episodes"] = sum(
                item["temporal"][mode]["false_alert_episodes"] for item in per_video.values()
            )
        if mode == "smoothed" and per_video:
            first = next(iter(per_video.values()))["temporal"][mode]
            mode_output["window"] = first["window"]
            mode_output["minimum_hits"] = first["minimum_hits"]
            eligible = {
                name: item
                for name, item in per_video.items()
                if item["temporal"]["temporal_smoothing_eligible"]
            }
            eligible_events = sum(
                item["temporal"][mode]["events"] for item in eligible.values()
            )
            eligible_detected_events = sum(
                item["temporal"][mode]["detected_events"] for item in eligible.values()
            )
            mode_output["eligible_videos"] = len(eligible)
            mode_output["ineligible_short_videos"] = len(per_video) - len(eligible)
            mode_output["eligible_event_recall"] = (
                round(eligible_detected_events / eligible_events, 6)
                if eligible_events
                else None
            )
            mode_output["eligible_macro_video_coverage"] = macro_average(
                eligible, ("temporal", mode, "coverage")
            )
        output[mode] = mode_output
    return output


def main() -> None:
    args = parse_args()
    if args.imgsz <= 0 or args.batch <= 0 or args.workers < 0:
        raise SystemExit("imgsz/batch must be positive and workers cannot be negative")
    probability_values = [
        args.presence_conf, args.prediction_conf, args.iou, args.match_iou, *args.thresholds
    ]
    if not all(0.0 <= value <= 1.0 for value in probability_values):
        raise SystemExit("confidence and IoU values must be between 0 and 1")
    if args.temporal_window <= 0 or not 1 <= args.temporal_min_hits <= args.temporal_window:
        raise SystemExit("temporal hits must be between 1 and the positive temporal window size")

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
        runtime_yaml = write_resolved_dataset_yaml(config, Path(temporary_directory) / "data.yaml")
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

    thresholds = sorted(set([args.presence_conf, *args.thresholds]))
    inference_conf = min(args.prediction_conf, min(thresholds))
    frames, prediction_speed = predict_frames(
        model,
        images,
        person_id,
        args.imgsz,
        device,
        inference_conf,
        args.iou,
        args.batch,
    )
    selected_metrics = frame_metrics(
        frames, args.presence_conf, args.match_iou, args.match_mode
    )
    curve = [
        frame_metrics(frames, threshold, args.match_iou, args.match_mode)
        for threshold in thresholds
    ]

    grouped: dict[str, list[EvaluationFrame]] = defaultdict(list)
    for frame in frames:
        grouped[frame.sequence].append(frame)
    per_video = {}
    for sequence, sequence_frames in sorted(grouped.items()):
        per_video[sequence] = {
            "frame_metrics": frame_metrics(
                sequence_frames, args.presence_conf, args.match_iou, args.match_mode
            ),
            "temporal": sequence_metrics(
                sequence_frames,
                args.presence_conf,
                args.match_iou,
                args.match_mode,
                args.temporal_window,
                args.temporal_min_hits,
            ),
        }

    empty_frames = [frame for frame in frames if not frame.ground_truth]
    empty_fp_frames = sum(
        any(detection.confidence >= args.presence_conf for detection in frame.detections)
        for frame in empty_frames
    )
    empty_fp_detections = sum(
        sum(detection.confidence >= args.presence_conf for detection in frame.detections)
        for frame in empty_frames
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
        "evaluation_definition": {
            "presence_confidence": args.presence_conf,
            "relaxed_match_mode": args.match_mode,
            "relaxed_match_iou": args.match_iou,
            "nms_iou": args.iou,
            "temporal_window": args.temporal_window,
            "temporal_minimum_hits": args.temporal_min_hits,
            "timeline": (
                "Original source frames ordered by inferred frame number; generated negative "
                "crops are excluded from temporal metrics. Durations use observed frames."
            ),
        },
        "frame_presence_and_relaxed_matching": selected_metrics,
        "confidence_curve": curve,
        "suggested_operating_points": choose_operating_points(curve),
        "per_video_metrics": per_video,
        "temporal_metrics": pooled_temporal_metrics(per_video),
        "prediction_speed": prediction_speed,
        "empty_frame_metrics": {
            "confidence_threshold": args.presence_conf,
            "empty_frames": len(empty_frames),
            "invalid_label_frames_excluded": 0,
            "frames_with_false_positives": empty_fp_frames,
            "false_positive_detections": empty_fp_detections,
            "false_positive_frame_rate": (
                round(empty_fp_frames / len(empty_frames), 6) if empty_frames else None
            ),
            "mean_pipeline_ms_per_frame": prediction_speed["mean_pipeline_ms_per_frame"],
            "wall_ms_per_frame": prediction_speed["wall_ms_per_frame"],
        },
    }
    write_json(args.output, report)
    print(f"Evaluation report: {args.output.expanduser().resolve()}")
    print(f"Person metrics: {report['person_metrics']}")
    print(f"Frame metrics: {selected_metrics}")
    print(f"Temporal metrics: {report['temporal_metrics']}")


if __name__ == "__main__":
    main()
