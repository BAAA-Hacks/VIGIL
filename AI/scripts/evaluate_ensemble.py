#!/usr/bin/env python3
"""Evaluate a weighted-box-fusion ensemble of YOLO26 detectors with VIGIL metrics.

Each member's raw predictions are cached, so fusion settings can be swept without
re-running inference. mAP is computed by this script for both the members and the
ensemble so the localization comparison is like for like.
"""

from __future__ import annotations

import argparse
import itertools
import json
import time
from collections import defaultdict
from pathlib import Path

try:
    from AI.scripts.dataset_utils import find_data_yaml, load_dataset_config, split_images, write_json
    from AI.scripts.evaluate import (
        DEFAULT_THRESHOLDS,
        choose_operating_points,
        pooled_temporal_metrics,
        predict_frames,
    )
    from AI.scripts.model_utils import load_model, parse_device
    from AI.scripts.temporal_metrics import (
        Detection,
        EvaluationFrame,
        box_iou,
        frame_metrics,
        sequence_metrics,
    )
except ModuleNotFoundError:
    from AI.scripts.dataset_utils import find_data_yaml, load_dataset_config, split_images, write_json  # type: ignore
    from AI.scripts.evaluate import (  # type: ignore
        DEFAULT_THRESHOLDS,
        choose_operating_points,
        pooled_temporal_metrics,
        predict_frames,
    )
    from AI.scripts.model_utils import load_model, parse_device  # type: ignore
    from AI.scripts.temporal_metrics import (  # type: ignore
        Detection,
        EvaluationFrame,
        box_iou,
        frame_metrics,
        sequence_metrics,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", required=True, nargs="+", type=Path, help="Two or more member checkpoints")
    parser.add_argument("--data", required=True, type=Path, help="Dataset root or data.yaml")
    parser.add_argument("--split", choices=("train", "val", "test"), default="val")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--device", default="0")
    parser.add_argument("--person-class", default="person")
    parser.add_argument("--presence-conf", type=float, default=0.40)
    parser.add_argument("--prediction-conf", type=float, default=0.001)
    parser.add_argument("--iou", type=float, default=0.7, help="Per-member NMS IoU")
    parser.add_argument("--match-iou", type=float, default=0.25)
    parser.add_argument("--match-mode", choices=("iou", "center", "iou_or_center"), default="iou_or_center")
    parser.add_argument("--temporal-window", type=int, default=3)
    parser.add_argument("--temporal-min-hits", type=int, default=2)
    parser.add_argument(
        "--member-weights",
        nargs="+",
        type=float,
        help="Fusion weight per member (default: equal). Ignored with --grid.",
    )
    parser.add_argument("--fusion-iou", type=float, default=0.55, help="WBF clustering IoU. Ignored with --grid.")
    parser.add_argument("--skip-box-conf", type=float, default=0.001, help="Drop member boxes below this before fusion")
    parser.add_argument(
        "--grid",
        action="store_true",
        help="Sweep fusion IoU and member weights; write one report per setting plus a summary",
    )
    parser.add_argument("--cache-dir", type=Path, default=Path("AI/reports/ensemble/cache"))
    parser.add_argument("--output", type=Path, default=Path("AI/reports/ensemble"))
    return parser.parse_args()


# ---------------------------------------------------------------- member predictions


def cache_path(cache_dir: Path, weights: Path, split: str, yaml_path: Path) -> Path:
    stem = f"{weights.parent.parent.name}_{weights.stem}" if weights.parent.name == "weights" else weights.stem
    return cache_dir / f"{split}_{yaml_path.parent.name}_{stem}.json"


def frames_to_json(frames: list[EvaluationFrame], speed: dict) -> dict:
    return {
        "speed": speed,
        "frames": [
            {
                "image": str(frame.image),
                "sequence": frame.sequence,
                "frame_number": frame.frame_number,
                "derived_negative": frame.derived_negative,
                "ground_truth": frame.ground_truth,
                "detections": [[d.confidence, *d.box] for d in frame.detections],
            }
            for frame in frames
        ],
    }


def frames_from_json(payload: dict) -> tuple[list[EvaluationFrame], dict]:
    frames = [
        EvaluationFrame(
            image=Path(item["image"]),
            sequence=item["sequence"],
            frame_number=item["frame_number"],
            derived_negative=item["derived_negative"],
            ground_truth=tuple(tuple(box) for box in item["ground_truth"]),
            detections=tuple(Detection(confidence=d[0], box=tuple(d[1:])) for d in item["detections"]),
        )
        for item in payload["frames"]
    ]
    return frames, payload["speed"]


def member_frames(args: argparse.Namespace, weights: Path, images: list[Path], person_id: int, yaml_path: Path):
    path = cache_path(args.cache_dir.expanduser().resolve(), weights.expanduser().resolve(), args.split, yaml_path)
    if path.is_file():
        print(f"Cached predictions: {path}")
        return frames_from_json(json.loads(path.read_text(encoding="utf-8")))
    model = load_model(weights.expanduser().resolve())
    names = model.names if isinstance(model.names, dict) else dict(enumerate(model.names))
    if str(names.get(person_id, "")).casefold() != args.person_class.casefold():
        raise SystemExit(f"{weights}: class {person_id} is {names.get(person_id)!r}, not {args.person_class!r}")
    print(f"Predicting {len(images)} images with {weights}")
    frames, speed = predict_frames(
        model, images, person_id, args.imgsz, parse_device(args.device), args.prediction_conf, args.iou, args.batch
    )
    write_json(path, frames_to_json(frames, speed))
    return frames, speed


# ---------------------------------------------------------------- fusion


def weighted_box_fusion(
    member_detections: list[tuple[Detection, ...]],
    member_weights: list[float],
    fusion_iou: float,
    skip_conf: float,
) -> tuple[Detection, ...]:
    """Single-class WBF (Solovyev et al.). Boxes seen by fewer members are down-weighted."""
    candidates = sorted(
        (
            (detection.confidence * weight, detection.box, member)
            for member, (detections, weight) in enumerate(zip(member_detections, member_weights, strict=True))
            for detection in detections
            if detection.confidence >= skip_conf
        ),
        key=lambda item: -item[0],
    )
    clusters: list[list[tuple[float, tuple, int]]] = []
    fused_boxes: list[tuple[float, float, float, float]] = []
    for candidate in candidates:
        best_index, best_iou = -1, fusion_iou
        for index, fused in enumerate(fused_boxes):
            overlap = box_iou(candidate[1], fused)
            if overlap > best_iou:
                best_index, best_iou = index, overlap
        if best_index < 0:
            clusters.append([candidate])
            fused_boxes.append(candidate[1])
            continue
        clusters[best_index].append(candidate)
        scores = [item[0] for item in clusters[best_index]]
        total = sum(scores)
        fused_boxes[best_index] = tuple(
            sum(score * item[1][axis] for score, item in zip(scores, clusters[best_index])) / total
            for axis in range(4)
        )

    total_weight = sum(member_weights)
    fused: list[Detection] = []
    for cluster, box in zip(clusters, fused_boxes, strict=True):
        # One box per member at most counts toward agreement; extra overlapping boxes from
        # the same member must not inflate confidence.
        best_per_member: dict[int, float] = {}
        for score, _, member in cluster:
            best_per_member[member] = max(best_per_member.get(member, 0.0), score)
        confidence = sum(best_per_member.values()) / total_weight
        fused.append(Detection(confidence=min(1.0, confidence), box=box))
    return tuple(sorted(fused, key=lambda detection: -detection.confidence))


def fuse_frames(
    members: list[list[EvaluationFrame]], member_weights: list[float], fusion_iou: float, skip_conf: float
) -> list[EvaluationFrame]:
    fused_frames: list[EvaluationFrame] = []
    for per_member in zip(*members, strict=True):
        reference = per_member[0]
        if any(frame.image != reference.image for frame in per_member):
            raise RuntimeError("Member predictions are not aligned; clear the prediction cache")
        detections = weighted_box_fusion(
            [frame.detections for frame in per_member], member_weights, fusion_iou, skip_conf
        )
        fused_frames.append(
            EvaluationFrame(
                image=reference.image,
                sequence=reference.sequence,
                frame_number=reference.frame_number,
                derived_negative=reference.derived_negative,
                ground_truth=reference.ground_truth,
                detections=detections,
            )
        )
    return fused_frames


# ---------------------------------------------------------------- metrics


def average_precision(frames: list[EvaluationFrame], iou_threshold: float) -> float | None:
    """COCO-style 101-point interpolated AP for one class."""
    ground_truth_count = sum(len(frame.ground_truth) for frame in frames)
    if not ground_truth_count:
        return None
    scored: list[tuple[float, int, tuple]] = [
        (detection.confidence, index, detection.box)
        for index, frame in enumerate(frames)
        for detection in frame.detections
    ]
    scored.sort(key=lambda item: -item[0])
    matched: dict[int, set[int]] = defaultdict(set)
    true_positives: list[int] = []
    for _, index, box in scored:
        best_gt, best_iou = -1, iou_threshold
        for gt_index, gt_box in enumerate(frames[index].ground_truth):
            if gt_index in matched[index]:
                continue
            overlap = box_iou(box, gt_box)
            if overlap >= best_iou:
                best_gt, best_iou = gt_index, overlap
        if best_gt >= 0:
            matched[index].add(best_gt)
        true_positives.append(1 if best_gt >= 0 else 0)

    precisions: list[float] = []
    recalls: list[float] = []
    hits = 0
    for rank, hit in enumerate(true_positives, start=1):
        hits += hit
        precisions.append(hits / rank)
        recalls.append(hits / ground_truth_count)
    for index in range(len(precisions) - 2, -1, -1):
        precisions[index] = max(precisions[index], precisions[index + 1])
    total = 0.0
    cursor = 0
    for step in range(101):
        target = step / 100.0
        while cursor < len(recalls) and recalls[cursor] < target:
            cursor += 1
        total += precisions[cursor] if cursor < len(precisions) else 0.0
    return round(total / 101.0, 6)


def localization_metrics(frames: list[EvaluationFrame]) -> dict:
    map50 = average_precision(frames, 0.5)
    per_threshold = [average_precision(frames, 0.5 + 0.05 * step) for step in range(10)]
    map50_95 = (
        round(sum(per_threshold) / len(per_threshold), 6) if all(v is not None for v in per_threshold) else None
    )
    return {"map50": map50, "map50_95": map50_95, "implementation": "evaluate_ensemble.average_precision"}


def build_report(args: argparse.Namespace, frames: list[EvaluationFrame], extra: dict) -> dict:
    thresholds = sorted(set([args.presence_conf, *DEFAULT_THRESHOLDS]))
    curve = [frame_metrics(frames, threshold, args.match_iou, args.match_mode) for threshold in thresholds]
    grouped: dict[str, list[EvaluationFrame]] = defaultdict(list)
    for frame in frames:
        grouped[frame.sequence].append(frame)
    per_video = {
        sequence: {
            "frame_metrics": frame_metrics(sequence_frames, args.presence_conf, args.match_iou, args.match_mode),
            "temporal": sequence_metrics(
                sequence_frames,
                args.presence_conf,
                args.match_iou,
                args.match_mode,
                args.temporal_window,
                args.temporal_min_hits,
            ),
        }
        for sequence, sequence_frames in sorted(grouped.items())
    }
    return {
        **extra,
        "split": args.split,
        "images": len(frames),
        "person_metrics": localization_metrics(frames),
        "evaluation_definition": {
            "presence_confidence": args.presence_conf,
            "relaxed_match_mode": args.match_mode,
            "relaxed_match_iou": args.match_iou,
            "nms_iou": args.iou,
            "temporal_window": args.temporal_window,
            "temporal_minimum_hits": args.temporal_min_hits,
        },
        "frame_presence_and_relaxed_matching": frame_metrics(
            frames, args.presence_conf, args.match_iou, args.match_mode
        ),
        "confidence_curve": curve,
        "suggested_operating_points": choose_operating_points(curve),
        "per_video_metrics": per_video,
        "temporal_metrics": pooled_temporal_metrics(per_video),
    }


def summary_row(label: str, report: dict) -> str:
    frame = report["frame_presence_and_relaxed_matching"]
    smoothed = report["temporal_metrics"]["smoothed"]
    best = report["suggested_operating_points"]["maximum_frame_f1"]
    loc = report["person_metrics"]
    return (
        f"{label:34s} F1={frame['f1']:.3f} R={frame['recall']:.3f} spec={frame['specificity']:.3f} "
        f"mAP50={loc['map50']:.3f} mAP50-95={loc['map50_95']:.3f} FA={smoothed['false_alert_episodes']:3d} "
        f"miss={smoothed['longest_miss_streak_frames']:3d} | best F1 {best['f1']:.3f} @ {best['confidence_threshold']:.2f}"
    )


def main() -> None:
    args = parse_args()
    if len(args.weights) < 2:
        raise SystemExit("An ensemble needs at least two --weights")
    if args.member_weights and len(args.member_weights) != len(args.weights):
        raise SystemExit("--member-weights needs one value per --weights entry")
    if not 0.0 < args.fusion_iou < 1.0:
        raise SystemExit("--fusion-iou must be in (0, 1)")

    yaml_path = find_data_yaml(args.data)
    config = load_dataset_config(yaml_path)
    person_ids = [key for key, name in config.names.items() if name.casefold() == args.person_class.casefold()]
    if len(person_ids) != 1:
        raise SystemExit(f"Expected one {args.person_class!r} class, found {person_ids}")
    images = split_images(config, args.split)
    if not images:
        raise SystemExit(f"Dataset split {args.split!r} is empty")

    members = []
    member_speed = []
    for weights in args.weights:
        frames, speed = member_frames(args, weights, images, person_ids[0], yaml_path)
        members.append(frames)
        member_speed.append(speed)

    output_root = args.output.expanduser().resolve()
    lines = []
    member_names = [
        w.parent.parent.name if w.parent.name == "weights" else w.stem for w in args.weights
    ]
    for name, weights, frames, speed in zip(member_names, args.weights, members, member_speed, strict=True):
        report = build_report(args, frames, {"weights": str(weights), "prediction_speed": speed})
        write_json(output_root / f"{args.split}_member_{name}.json", report)
        lines.append(summary_row(f"member {name}", report))

    if args.grid:
        weight_options = sorted(set(itertools.product((1.0, 2.0), repeat=len(args.weights))))
        weight_options = [w for w in weight_options if min(w) == 1.0]
        settings = [(iou, list(w)) for iou in (0.4, 0.55, 0.7) for w in weight_options]
    else:
        settings = [(args.fusion_iou, args.member_weights or [1.0] * len(args.weights))]

    combined_ms = sum(speed.get("wall_ms_per_frame") or 0.0 for speed in member_speed)
    for fusion_iou, weights in settings:
        started = time.perf_counter()
        fused = fuse_frames(members, weights, fusion_iou, args.skip_box_conf)
        fusion_ms = (time.perf_counter() - started) * 1000.0 / max(1, len(fused))
        tag = f"wbf_iou{fusion_iou:.2f}_w" + "-".join(f"{w:g}" for w in weights)
        report = build_report(
            args,
            fused,
            {
                "members": [str(w) for w in args.weights],
                "fusion": {"method": "weighted_box_fusion", "iou": fusion_iou, "member_weights": weights,
                           "skip_box_conf": args.skip_box_conf},
                "prediction_speed": {
                    "wall_ms_per_frame": round(combined_ms + fusion_ms, 3),
                    "note": "Sum of member wall time plus fusion; members could run in parallel.",
                },
            },
        )
        write_json(output_root / f"{args.split}_ensemble_{tag}.json", report)
        lines.append(summary_row(tag, report))

    summary = "\n".join(lines)
    (output_root / f"{args.split}_summary.txt").write_text(summary + "\n", encoding="utf-8")
    print(summary)
    print(f"Reports: {output_root}")


if __name__ == "__main__":
    main()
