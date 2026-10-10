from __future__ import annotations

from pathlib import Path


def load_model(weights: str | Path):
    try:
        import ultralytics
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit(
            "Ultralytics is not installed. Activate the project environment and run "
            "`python -m pip install -U ultralytics`."
        ) from exc

    try:
        return YOLO(str(weights))
    except Exception as exc:
        version = getattr(ultralytics, "__version__", "unknown")
        if Path(str(weights)).name.lower().startswith("yolo26"):
            raise SystemExit(
                f"Could not load required YOLO26 weights {weights!s} with Ultralytics "
                f"{version}. Upgrade with `python -m pip install -U ultralytics` and "
                "confirm that the weights can be downloaded. VIGIL will not silently "
                "substitute another model. Original error: "
                f"{exc}"
            ) from exc
        raise SystemExit(f"Could not load model weights {weights!s}: {exc}") from exc


def parse_device(value: str):
    lowered = value.strip().lower()
    if lowered in {"cpu", "mps"} or "," in value:
        return value
    try:
        return int(value)
    except ValueError:
        return value


def result_processing_ms(result) -> float:
    speed = getattr(result, "speed", {}) or {}
    return round(
        sum(float(speed.get(stage, 0.0) or 0.0) for stage in ("preprocess", "inference", "postprocess")),
        3,
    )
