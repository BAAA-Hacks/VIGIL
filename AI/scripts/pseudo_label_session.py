#!/usr/bin/env python3
"""Turn a lepton_live recording into YOLO training data for the real camera.

Confident frames keep the model's boxes. Short runs of unconfident frames between two
confident boxes of the same person get linearly interpolated boxes; these are mostly the
motion-smeared frames the model misses, which is exactly what needs teaching. Frames whose
best candidate is near zero and that sit away from any person are kept as negatives.
The session is split in time: the first part trains, the tail is held out for evaluation.

  session/frames/*.png  ->  out/{train,val}/{images,labels}  (+ review/ previews)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

try:
    from AI.scripts.model_utils import load_model, parse_device
    from AI.scripts.temporal_metrics import box_iou
except ModuleNotFoundError:
    from AI.scripts.model_utils import load_model, parse_device  # type: ignore
    from AI.scripts.temporal_metrics import box_iou  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sessions", nargs="+", type=Path, help="Session directories from lepton_live --record")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--weights", type=Path, default=Path("AI/checkpoints/thermal_medium_range_yolo26s_p2_closeup_best.pt"))
    parser.add_argument("--device", default="0")
    parser.add_argument("--confident", type=float, default=0.30, help="Model boxes at or above this are kept")
    parser.add_argument("--max-gap", type=int, default=6, help="Longest unconfident run to interpolate across")
    parser.add_argument("--same-person-iou", type=float, default=0.3)
    parser.add_argument("--negative-below", type=float, default=0.03)
    parser.add_argument("--negative-margin", type=int, default=10, help="Frames kept clear of any person")
    parser.add_argument("--val-fraction", type=float, default=0.25)
    return parser.parse_args()


def predict(model, frames: list[Path], device) -> list[list[tuple[float, list[float]]]]:
    output = []
    for path in frames:
        image = cv2.cvtColor(cv2.imread(str(path), cv2.IMREAD_GRAYSCALE), cv2.COLOR_GRAY2BGR)
        result = model.predict(image, imgsz=640, conf=0.01, device=device, verbose=False)[0]
        boxes = []
        if result.boxes is not None:
            for conf, xyxyn in zip(result.boxes.conf.tolist(), result.boxes.xyxyn.tolist(), strict=True):
                boxes.append((float(conf), [float(v) for v in xyxyn]))
        output.append(sorted(boxes, key=lambda item: -item[0]))
    return output


def label_session(predictions, args) -> tuple[list[list[list[float]] | None], dict]:
    """Per frame: list of xyxy boxes, [] for a negative, None for unusable."""
    labels: list[list[list[float]] | None] = [None] * len(predictions)
    confident = [[box for conf, box in frame if conf >= args.confident] for frame in predictions]
    stats = {"confident": 0, "interpolated": 0, "negative": 0, "skipped": 0}
    for index, boxes in enumerate(confident):
        if boxes:
            labels[index] = boxes
            stats["confident"] += 1
    anchors = [index for index, boxes in enumerate(confident) if len(boxes) == 1]
    for start, end in zip(anchors, anchors[1:]):
        gap = end - start - 1
        if not 0 < gap <= args.max_gap or any(confident[i] for i in range(start + 1, end)):
            continue
        first, last = confident[start][0], confident[end][0]
        if box_iou(tuple(first), tuple(last)) < args.same_person_iou:
            continue
        for step in range(1, gap + 1):
            t = step / (gap + 1)
            labels[start + step] = [[a + (b - a) * t for a, b in zip(first, last, strict=True)]]
            stats["interpolated"] += 1
    person_frames = [index for index, value in enumerate(labels) if value]
    for index, frame in enumerate(predictions):
        if labels[index] is not None:
            continue
        top = frame[0][0] if frame else 0.0
        near_person = any(abs(index - p) <= args.negative_margin for p in person_frames)
        if top < args.negative_below and not near_person:
            labels[index] = []
            stats["negative"] += 1
        else:
            stats["skipped"] += 1
    return labels, stats


def yolo_line(box: list[float]) -> str:
    left, top, right, bottom = (min(1.0, max(0.0, v)) for v in box)
    return f"0 {(left + right) / 2:.6f} {(top + bottom) / 2:.6f} {right - left:.6f} {bottom - top:.6f}"


def main() -> None:
    args = parse_args()
    if not 0 < args.val_fraction < 1:
        raise SystemExit("--val-fraction must be in (0, 1)")
    model = load_model(args.weights.expanduser().resolve())
    device = parse_device(args.device)
    output = args.output.expanduser().resolve()
    report = {"weights": str(args.weights), "sessions": {}}
    for session in args.sessions:
        session = session.expanduser().resolve()
        frames = sorted((session / "frames").glob("*.png"))
        if not frames:
            raise SystemExit(f"No frames in {session}")
        labels, stats = label_session(predict(model, frames, device), args)
        split_at = int(len(frames) * (1 - args.val_fraction))
        counts = {"train": 0, "val": 0}
        for index, (frame, boxes) in enumerate(zip(frames, labels, strict=True)):
            if boxes is None:
                continue
            split = "train" if index < split_at else "val"
            stem = f"{session.name}_{frame.stem}"
            image_dir = output / split / "images"
            label_dir = output / split / "labels"
            image_dir.mkdir(parents=True, exist_ok=True)
            label_dir.mkdir(parents=True, exist_ok=True)
            (image_dir / f"{stem}.png").write_bytes(frame.read_bytes())
            (label_dir / f"{stem}.txt").write_text("".join(yolo_line(b) + "\n" for b in boxes))
            counts[split] += 1
            if index % 25 == 0:
                preview = cv2.resize(cv2.imread(str(frame)), (640, 480), interpolation=cv2.INTER_NEAREST)
                for box in boxes:
                    cv2.rectangle(preview, (int(box[0] * 640), int(box[1] * 480)), (int(box[2] * 640), int(box[3] * 480)), (0, 255, 0), 2)
                (output / "review").mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(output / "review" / f"{stem}.jpg"), preview)
        report["sessions"][session.name] = {"frames": len(frames), **stats, **counts}
        print(f"{session.name}: {stats} -> train {counts['train']}, val {counts['val']}")
    (output / "pseudo_label_report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
