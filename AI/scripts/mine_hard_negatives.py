#!/usr/bin/env python3
"""Mine false detections from labeled-negative training frames only."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
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
    )
    from AI.scripts.model_utils import load_model, parse_device
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
    )
    from AI.scripts.model_utils import load_model, parse_device  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--split", choices=("train",), default="train")
    parser.add_argument("--confidence", type=float, default=0.4)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--device", default="0")
    parser.add_argument("--iou", type=float, default=0.7)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 0 <= args.confidence <= 1 or not 0 <= args.iou <= 1:
        raise SystemExit("Confidence and IoU must be between zero and one")
    config = load_dataset_config(find_data_yaml(args.data))
    negative_images = []
    for image in split_images(config, args.split):
        labels, errors = read_yolo_labels(label_path_for_image(image))
        if errors:
            raise SystemExit("; ".join(errors))
        if not labels:
            negative_images.append(image)
    if not negative_images:
        raise SystemExit("No labeled-negative training frames found")

    model = load_model(args.weights)
    records = []
    source_counts: Counter[str] = Counter()
    for image_chunk in chunks(negative_images, max(1, args.batch)):
        results = model.predict(
            source=[str(path) for path in image_chunk],
            imgsz=args.imgsz,
            conf=args.confidence,
            iou=args.iou,
            device=parse_device(args.device),
            stream=True,
            verbose=False,
        )
        for image, result in zip(image_chunk, results, strict=True):
            confidences = result.boxes.conf.detach().cpu().tolist() if result.boxes is not None else []
            classes = result.boxes.cls.detach().cpu().tolist() if result.boxes is not None else []
            person_confidences = [
                float(confidence)
                for confidence, class_value in zip(confidences, classes, strict=True)
                if int(class_value) == 0
            ]
            if not person_confidences:
                continue
            source, frame = source_frame_id(image)
            source_counts[source] += 1
            records.append(
                {
                    "image": str(image.resolve()),
                    "source": source,
                    "frame": frame,
                    "detections": len(person_confidences),
                    "maximum_confidence": round(max(person_confidences), 6),
                }
            )

    by_source: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        by_source[record["source"]].append(record)
    episodes = 0
    for source_records in by_source.values():
        numbered = sorted(record["frame"] for record in source_records if record["frame"] is not None)
        previous = None
        for frame in numbered:
            if previous is None or frame != previous + 1:
                episodes += 1
            previous = frame

    payload = {
        "weights": str(args.weights.expanduser().resolve()),
        "dataset_yaml": str(config.yaml_path),
        "split": args.split,
        "confidence": args.confidence,
        "negative_images_scanned": len(negative_images),
        "hard_negative_images": [record["image"] for record in records],
        "hard_negative_count": len(records),
        "source_count": len(source_counts),
        "continuous_episode_count": episodes,
        "hard_negatives_per_source": dict(sorted(source_counts.items())),
        "records": records,
        "safety": "Training split only; validation and test images are excluded.",
    }
    write_json(args.output, payload)
    print(f"Hard-negative manifest: {args.output.expanduser().resolve()}")
    print(f"  scanned negative training frames: {len(negative_images)}")
    print(f"  hard negatives at confidence {args.confidence}: {len(records)}")
    print(f"  sources: {len(source_counts)}; continuous episodes: {episodes}")


if __name__ == "__main__":
    main()
