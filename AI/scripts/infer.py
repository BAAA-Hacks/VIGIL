#!/usr/bin/env python3
"""Run YOLO26 inference and emit normalized VIGIL frame detections as JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from AI.scripts.dataset_utils import IMAGE_SUFFIXES, write_json
    from AI.scripts.model_utils import load_model, parse_device, result_processing_ms
except ModuleNotFoundError:
    from AI.scripts.dataset_utils import IMAGE_SUFFIXES, write_json  # type: ignore
    from AI.scripts.model_utils import load_model, parse_device, result_processing_ms  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path, help="Image file or directory")
    parser.add_argument("--output", type=Path, help="JSON output path; stdout when omitted")
    parser.add_argument("--save-previews", type=Path, help="Directory for annotated images")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.7)
    parser.add_argument("--device", default="0")
    parser.add_argument("--person-class", default="person")
    return parser.parse_args()


def source_images(source: Path) -> list[Path]:
    source = source.expanduser().resolve()
    if source.is_file() and source.suffix.lower() in IMAGE_SUFFIXES:
        return [source]
    if source.is_dir():
        return sorted(
            path for path in source.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
    raise FileNotFoundError(f"Source must be a supported image or directory: {source}")


def main() -> None:
    args = parse_args()
    if args.imgsz <= 0:
        raise SystemExit("--imgsz must be positive")
    if not 0.0 <= args.conf <= 1.0 or not 0.0 <= args.iou <= 1.0:
        raise SystemExit("confidence and IoU thresholds must be between 0 and 1")

    images = source_images(args.source)
    if not images:
        raise SystemExit(f"No supported images found under {args.source}")
    model = load_model(args.weights)
    raw_names = model.names
    names = (
        {index: str(value) for index, value in enumerate(raw_names)}
        if isinstance(raw_names, list)
        else {int(key): str(value) for key, value in raw_names.items()}
    )
    person_ids = [
        class_id
        for class_id, name in names.items()
        if name.strip().casefold() == args.person_class.strip().casefold()
    ]
    if len(person_ids) != 1:
        raise SystemExit(
            f"Expected one {args.person_class!r} class in model names, found {person_ids}: {names}"
        )
    person_id = person_ids[0]
    preview_root = args.save_previews.expanduser().resolve() if args.save_previews else None
    source_root = args.source.expanduser().resolve()
    if source_root.is_file():
        source_root = source_root.parent

    payload: list[dict] = []
    results = model.predict(
        source=[str(path) for path in images],
        imgsz=args.imgsz,
        conf=args.conf,
        iou=args.iou,
        device=parse_device(args.device),
        stream=True,
        verbose=False,
    )
    for image_path, result in zip(images, results, strict=True):
        height, width = result.orig_shape
        detections = []
        if result.boxes is not None:
            xyxy = result.boxes.xyxy.detach().cpu().tolist()
            confidences = result.boxes.conf.detach().cpu().tolist()
            classes = result.boxes.cls.detach().cpu().tolist()
            for coordinates, confidence, class_value in zip(xyxy, confidences, classes, strict=True):
                class_id = int(class_value)
                if class_id != person_id:
                    continue
                left, top, right, bottom = coordinates
                normalized = [
                    min(1.0, max(0.0, left / width)),
                    min(1.0, max(0.0, top / height)),
                    min(1.0, max(0.0, right / width)),
                    min(1.0, max(0.0, bottom / height)),
                ]
                detections.append(
                    {
                        "class": "person",
                        "confidence": round(float(confidence), 6),
                        "bbox_xyxy_norm": [round(float(value), 6) for value in normalized],
                    }
                )
        relative_name = str(image_path.relative_to(source_root))
        payload.append(
            {
                "frame_id": relative_name,
                "detections": detections,
                "processing_ms": result_processing_ms(result),
            }
        )
        if preview_root is not None:
            preview_path = preview_root / image_path.relative_to(source_root)
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            result.save(filename=str(preview_path))

    document: object = payload[0] if len(payload) == 1 else payload
    if args.output:
        write_json(args.output, document)
        print(f"Inference JSON: {args.output.expanduser().resolve()}")
    else:
        print(json.dumps(document, indent=2))


if __name__ == "__main__":
    main()
