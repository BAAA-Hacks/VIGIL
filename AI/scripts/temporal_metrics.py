"""Pure metric helpers for frame-presence and sequence-aware detector evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import fmean


Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Detection:
    confidence: float
    box: Box


@dataclass(frozen=True)
class EvaluationFrame:
    image: Path
    sequence: str
    frame_number: int | None
    derived_negative: bool
    ground_truth: tuple[Box, ...]
    detections: tuple[Detection, ...]


def safe_ratio(numerator: int | float, denominator: int | float) -> float | None:
    return round(float(numerator) / float(denominator), 6) if denominator else None


def harmonic_mean(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None or precision + recall == 0:
        return None
    return round(2 * precision * recall / (precision + recall), 6)


def box_iou(first: Box, second: Box) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def center_in_box(prediction: Box, ground_truth: Box) -> bool:
    x_center = (prediction[0] + prediction[2]) / 2.0
    y_center = (prediction[1] + prediction[3]) / 2.0
    return (
        ground_truth[0] <= x_center <= ground_truth[2]
        and ground_truth[1] <= y_center <= ground_truth[3]
    )


def match_count(
    ground_truth: tuple[Box, ...],
    detections: tuple[Detection, ...],
    iou_threshold: float,
    mode: str,
) -> int:
    """Greedily match detections to labels under a relaxed spatial criterion."""
    candidates: list[tuple[float, float, int, int]] = []
    for prediction_index, detection in enumerate(detections):
        for truth_index, truth in enumerate(ground_truth):
            overlap = box_iou(detection.box, truth)
            accepted = {
                "iou": overlap >= iou_threshold,
                "center": center_in_box(detection.box, truth),
                "iou_or_center": overlap >= iou_threshold or center_in_box(detection.box, truth),
            }[mode]
            if accepted:
                candidates.append((overlap, detection.confidence, prediction_index, truth_index))
    used_predictions: set[int] = set()
    used_truth: set[int] = set()
    for _, _, prediction_index, truth_index in sorted(candidates, reverse=True):
        if prediction_index in used_predictions or truth_index in used_truth:
            continue
        used_predictions.add(prediction_index)
        used_truth.add(truth_index)
    return len(used_predictions)


def filtered_detections(frame: EvaluationFrame, confidence: float) -> tuple[Detection, ...]:
    return tuple(detection for detection in frame.detections if detection.confidence >= confidence)


def frame_metrics(
    frames: list[EvaluationFrame], confidence: float, match_iou: float, match_mode: str
) -> dict:
    tp_frames = fp_frames = fn_frames = tn_frames = 0
    predictions = matches = ground_truth_instances = 0
    relaxed_hit_frames = 0
    derived_negative_frames = derived_negative_fp_frames = 0

    for frame in frames:
        detections = filtered_detections(frame, confidence)
        actual_positive = bool(frame.ground_truth)
        predicted_positive = bool(detections)
        if actual_positive and predicted_positive:
            tp_frames += 1
        elif predicted_positive:
            fp_frames += 1
        elif actual_positive:
            fn_frames += 1
        else:
            tn_frames += 1

        matched = match_count(frame.ground_truth, detections, match_iou, match_mode)
        predictions += len(detections)
        matches += matched
        ground_truth_instances += len(frame.ground_truth)
        relaxed_hit_frames += int(actual_positive and matched > 0)
        if frame.derived_negative:
            derived_negative_frames += 1
            derived_negative_fp_frames += int(predicted_positive)

    frame_precision = safe_ratio(tp_frames, tp_frames + fp_frames)
    frame_recall = safe_ratio(tp_frames, tp_frames + fn_frames)
    detection_precision = safe_ratio(matches, predictions)
    detection_recall = safe_ratio(matches, ground_truth_instances)
    positive_frames = tp_frames + fn_frames
    return {
        "confidence_threshold": confidence,
        "frames": len(frames),
        "positive_frames": positive_frames,
        "negative_frames": fp_frames + tn_frames,
        "tp_frames": tp_frames,
        "fp_frames": fp_frames,
        "fn_frames": fn_frames,
        "tn_frames": tn_frames,
        "precision": frame_precision,
        "recall": frame_recall,
        "f1": harmonic_mean(frame_precision, frame_recall),
        "specificity": safe_ratio(tn_frames, tn_frames + fp_frames),
        "relaxed_hit_frames": relaxed_hit_frames,
        "relaxed_frame_recall": safe_ratio(relaxed_hit_frames, positive_frames),
        "ground_truth_instances": ground_truth_instances,
        "predicted_instances": predictions,
        "matched_instances": matches,
        "false_positive_detections": predictions - matches,
        "missed_instances": ground_truth_instances - matches,
        "relaxed_detection_precision": detection_precision,
        "relaxed_detection_recall": detection_recall,
        "relaxed_detection_f1": harmonic_mean(detection_precision, detection_recall),
        "derived_negative_frames": derived_negative_frames,
        "derived_negative_fp_frames": derived_negative_fp_frames,
        "derived_negative_fp_rate": safe_ratio(
            derived_negative_fp_frames, derived_negative_frames
        ),
    }


def _longest_false_run(values: list[bool], eligible: list[bool]) -> int:
    longest = current = 0
    for value, is_eligible in zip(values, eligible, strict=True):
        current = current + 1 if is_eligible and not value else 0
        longest = max(longest, current)
    return longest


def _alert_episodes(alerts: list[bool], eligible: list[bool]) -> int:
    episodes = 0
    active = False
    for alert, is_eligible in zip(alerts, eligible, strict=True):
        now_active = alert and is_eligible
        episodes += int(now_active and not active)
        active = now_active
    return episodes


def _events(positive: list[bool]) -> list[tuple[int, int]]:
    events: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate([*positive, False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            events.append((start, index))
            start = None
    return events


def _event_summary(events: list[tuple[int, int]], alerts: list[bool]) -> dict:
    detected = 0
    delays: list[int] = []
    coverages: list[float] = []
    details: list[dict] = []
    for start, end in events:
        segment = alerts[start:end]
        hits = sum(segment)
        first_hit = next((index for index, value in enumerate(segment) if value), None)
        detected += int(first_hit is not None)
        if first_hit is not None:
            delays.append(first_hit)
        coverage = hits / len(segment)
        coverages.append(coverage)
        details.append(
            {
                "start_observation": start,
                "end_observation": end - 1,
                "positive_frames": len(segment),
                "detected_frames": hits,
                "coverage": round(coverage, 6),
                "time_to_first_detection_frames": first_hit,
            }
        )
    return {
        "events": len(events),
        "detected_events": detected,
        "event_recall": safe_ratio(detected, len(events)),
        "mean_event_coverage": round(fmean(coverages), 6) if coverages else None,
        "mean_time_to_first_detection_frames": round(fmean(delays), 3) if delays else None,
        "worst_time_to_first_detection_frames": max(delays) if delays else None,
        "details": details,
    }


def sequence_metrics(
    frames: list[EvaluationFrame],
    confidence: float,
    match_iou: float,
    match_mode: str,
    temporal_window: int,
    temporal_min_hits: int,
) -> dict:
    """Measure temporal continuity in observed original frames for one sequence."""
    timeline = sorted(
        (frame for frame in frames if not frame.derived_negative),
        key=lambda frame: (
            frame.frame_number is None,
            frame.frame_number if frame.frame_number is not None else 0,
            frame.image.name,
        ),
    )
    positive = [bool(frame.ground_truth) for frame in timeline]
    raw_alerts: list[bool] = []
    matched_alerts: list[bool] = []
    for frame in timeline:
        detections = filtered_detections(frame, confidence)
        raw_alerts.append(bool(detections))
        matched_alerts.append(
            match_count(frame.ground_truth, detections, match_iou, match_mode) > 0
        )
    smoothed_alerts = [
        sum(raw_alerts[max(0, index - temporal_window + 1) : index + 1]) >= temporal_min_hits
        for index in range(len(timeline))
    ]
    negative = [not value for value in positive]
    events = _events(positive)
    positive_count = sum(positive)
    raw_hits = sum(alert and actual for alert, actual in zip(raw_alerts, positive, strict=True))
    matched_hits = sum(
        alert and actual for alert, actual in zip(matched_alerts, positive, strict=True)
    )
    smoothed_hits = sum(
        alert and actual for alert, actual in zip(smoothed_alerts, positive, strict=True)
    )
    return {
        "sequence": timeline[0].sequence if timeline else (frames[0].sequence if frames else ""),
        "timeline_frames": len(timeline),
        "temporal_smoothing_eligible": len(timeline) >= temporal_min_hits,
        "known_frame_numbers": sum(frame.frame_number is not None for frame in timeline),
        "synthetic_negative_crops_excluded": sum(frame.derived_negative for frame in frames),
        "positive_frames": positive_count,
        "negative_frames": len(timeline) - positive_count,
        "raw": {
            "positive_frames_detected": raw_hits,
            "coverage": safe_ratio(raw_hits, positive_count),
            "longest_miss_streak_frames": _longest_false_run(raw_alerts, positive),
            "false_alert_episodes": _alert_episodes(raw_alerts, negative),
            **_event_summary(events, raw_alerts),
        },
        "relaxed_match": {
            "positive_frames_detected": matched_hits,
            "coverage": safe_ratio(matched_hits, positive_count),
            "longest_miss_streak_frames": _longest_false_run(matched_alerts, positive),
            **_event_summary(events, matched_alerts),
        },
        "smoothed": {
            "window": temporal_window,
            "minimum_hits": temporal_min_hits,
            "positive_frames_detected": smoothed_hits,
            "coverage": safe_ratio(smoothed_hits, positive_count),
            "longest_miss_streak_frames": _longest_false_run(smoothed_alerts, positive),
            "false_alert_episodes": _alert_episodes(smoothed_alerts, negative),
            **_event_summary(events, smoothed_alerts),
        },
    }


def macro_average(per_video: dict[str, dict], path: tuple[str, ...]) -> dict:
    values: list[float] = []
    for metrics in per_video.values():
        value: object = metrics
        for key in path:
            value = value[key]  # type: ignore[index]
        if value is not None:
            values.append(float(value))
    return {
        "mean": round(fmean(values), 6) if values else None,
        "videos_with_value": len(values),
    }
