#!/usr/bin/env python3
"""Stream native Lepton frames through YOLO and publish VIGIL website events."""

from __future__ import annotations

import argparse
import base64
import json
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import cv2
import numpy as np

try:
    from AI.scripts.model_utils import load_model, parse_device
except ModuleNotFoundError:
    from AI.scripts.model_utils import load_model, parse_device  # type: ignore


HEADER = struct.Struct("<4sIIHHHHI")
MAGIC = b"LEP1"
EXPECTED_WIDTH = 160
EXPECTED_HEIGHT = 120
TLINEAR_FLAG = 1


@dataclass(frozen=True)
class LeptonFrame:
    camera_frame_id: int
    camera_timestamp_ms: int
    width: int
    height: int
    raw_min: int
    raw_max: int
    flags: int
    pixels: np.ndarray


class EventSink(Protocol):
    def publish(self, event: str, payload: object) -> None: ...

    def close(self) -> None: ...


def read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise EOFError("Lepton stream closed mid-record")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(stream: BinaryIO) -> LeptonFrame:
    header = read_exact(stream, HEADER.size)
    magic, frame_id, timestamp_ms, width, height, raw_min, raw_max, flags = HEADER.unpack(header)
    if magic != MAGIC:
        raise ValueError(f"Lepton stream is out of sync: expected {MAGIC!r}, received {magic!r}")
    if (width, height) != (EXPECTED_WIDTH, EXPECTED_HEIGHT):
        raise ValueError(f"Unexpected Lepton dimensions: {width}x{height}")
    pixel_bytes = read_exact(stream, width * height * 2)
    pixels = np.frombuffer(pixel_bytes, dtype="<u2").reshape(height, width).copy()
    return LeptonFrame(frame_id, timestamp_ms, width, height, raw_min, raw_max, flags, pixels)


def lepton_frames(camera_url: str, timeout: float) -> Iterable[LeptonFrame]:
    url = camera_url.rstrip("/") + "/raw"
    request = Request(url, headers={"Connection": "close", "User-Agent": "VIGIL-Lepton/1"})
    try:
        response = urlopen(request, timeout=timeout)
    except HTTPError as exc:
        if exc.code == 503:
            raise RuntimeError("Lepton /raw is busy; only one raw-stream client is allowed") from exc
        raise RuntimeError(f"Lepton returned HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        raise ConnectionError(f"Could not connect to Lepton at {url}: {exc.reason}") from exc
    with response:
        while True:
            yield read_frame(response)


def normalize_frame(frame: LeptonFrame) -> np.ndarray:
    low = int(frame.raw_min)
    high = int(frame.raw_max)
    values = frame.pixels.astype(np.int32)
    return np.clip((values - low) * 255 // max(high - low, 1), 0, 255).astype(np.uint8)


def png_data_url(image: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("Could not encode Lepton frame as PNG")
    payload = base64.b64encode(encoded.tobytes()).decode("ascii")
    return f"data:image/png;base64,{payload}"


def center_temperature_c(frame: LeptonFrame, bbox: list[float]) -> float | None:
    if not frame.flags & TLINEAR_FLAG:
        return None
    left, top, right, bottom = bbox
    x = min(frame.width - 1, max(0, int(round(((left + right) / 2.0) * (frame.width - 1)))))
    y = min(frame.height - 1, max(0, int(round(((top + bottom) / 2.0) * (frame.height - 1)))))
    # Lepton TLinear is nominally kelvin x 100. Hardware calibration remains the camera's concern.
    return round(float(frame.pixels[y, x]) / 100.0 - 273.15, 2)


def feet_visible(bbox: list[float], edge_margin: float) -> bool:
    """Conservative box-based heuristic; this is not pose estimation."""
    bottom = bbox[3]
    return bottom < 1.0 - edge_margin


class JsonLineSink:
    def publish(self, event: str, payload: object) -> None:
        print(json.dumps({"event": event, "payload": payload}, separators=(",", ":")), flush=True)

    def close(self) -> None:
        return None


class SocketIOSink:
    def __init__(self, url: str, namespace: str | None) -> None:
        try:
            import socketio
        except ImportError as exc:
            raise SystemExit(
                "Socket.IO output requires `python -m pip install 'python-socketio[client]'`."
            ) from exc
        self.namespace = namespace
        self.client = socketio.Client(reconnection=True, logger=False, engineio_logger=False)
        self.client.connect(url, namespaces=[namespace] if namespace else None)

    def publish(self, event: str, payload: object) -> None:
        self.client.emit(event, payload, namespace=self.namespace)

    def close(self) -> None:
        self.client.disconnect()


def model_person_class(model, requested: str) -> int:
    raw_names = model.names
    names = (
        {index: str(value) for index, value in enumerate(raw_names)}
        if isinstance(raw_names, list)
        else {int(key): str(value) for key, value in raw_names.items()}
    )
    matches = [key for key, value in names.items() if value.casefold() == requested.casefold()]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {requested!r} class, found {matches}: {names}")
    return matches[0]


def result_people(result, person_class: int, frame: LeptonFrame, edge_margin: float) -> list[dict]:
    if result.boxes is None or len(result.boxes) == 0:
        return []
    height, width = result.orig_shape
    xyxy = result.boxes.xyxy.detach().cpu().tolist()
    confidences = result.boxes.conf.detach().cpu().tolist()
    classes = result.boxes.cls.detach().cpu().tolist()
    ids = result.boxes.id.detach().cpu().tolist() if result.boxes.id is not None else []
    people: list[dict] = []
    for index, (coordinates, confidence, class_value) in enumerate(
        zip(xyxy, confidences, classes, strict=True)
    ):
        if int(class_value) != person_class:
            continue
        left, top, right, bottom = coordinates
        bbox = [
            round(min(1.0, max(0.0, float(left) / width)), 6),
            round(min(1.0, max(0.0, float(top) / height)), 6),
            round(min(1.0, max(0.0, float(right) / width)), 6),
            round(min(1.0, max(0.0, float(bottom) / height)), 6),
        ]
        tracking_id = int(ids[index]) if index < len(ids) else None
        people.append(
            {
                "bbox": bbox,
                "bottom_center": [round((bbox[0] + bbox[2]) / 2.0, 6), bbox[3]],
                "tracking_id": tracking_id,
                "confidence": round(float(confidence), 6),
                "feet_visible": feet_visible(bbox, edge_margin),
                "center_temperature_c": center_temperature_c(frame, bbox),
                "class": "person",
            }
        )
    return people


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--weights",
        type=Path,
        default=Path("AI/checkpoints/thermal_mega_medium_crop_fold0_best.pt"),
    )
    parser.add_argument("--camera-url", default="http://192.168.4.1")
    parser.add_argument("--socket-url", help="Website Socket.IO URL; omit for JSON-lines stdout")
    parser.add_argument("--socket-namespace", default=None)
    parser.add_argument("--frame-event", default="vigil:frame")
    parser.add_argument("--detection-event", default="vigil:detection")
    parser.add_argument("--device", default="0")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.40)
    parser.add_argument("--iou", type=float, default=0.70)
    parser.add_argument("--tracker", default="bytetrack.yaml")
    parser.add_argument("--person-class", default="person")
    parser.add_argument("--feet-edge-margin", type=float, default=0.01)
    parser.add_argument("--connect-timeout", type=float, default=5.0)
    parser.add_argument("--reconnect-delay", type=float, default=1.0)
    parser.add_argument("--max-frames", type=int, help="Stop after N frames; useful for testing")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.imgsz <= 0 or args.max_frames is not None and args.max_frames <= 0:
        raise SystemExit("--imgsz and --max-frames must be positive")
    if not 0 <= args.conf <= 1 or not 0 <= args.iou <= 1:
        raise SystemExit("--conf and --iou must be between zero and one")
    if not 0 <= args.feet_edge_margin < 0.5:
        raise SystemExit("--feet-edge-margin must be in [0, 0.5)")

    model = load_model(args.weights.expanduser().resolve())
    person_class = model_person_class(model, args.person_class)
    sink: EventSink = (
        SocketIOSink(args.socket_url, args.socket_namespace) if args.socket_url else JsonLineSink()
    )
    published = 0
    boot_session = 0
    process_session = time.time_ns() // 1_000_000
    last_camera_frame: int | None = None
    try:
        while args.max_frames is None or published < args.max_frames:
            try:
                for frame in lepton_frames(args.camera_url, args.connect_timeout):
                    if last_camera_frame is not None and frame.camera_frame_id <= last_camera_frame:
                        boot_session += 1
                    last_camera_frame = frame.camera_frame_id
                    capture_timestamp_ms = time.time_ns() // 1_000_000
                    frame_id = f"lepton-{process_session}-{boot_session}-{frame.camera_frame_id}"
                    image = normalize_frame(frame)
                    model_input = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

                    started = time.perf_counter()
                    results = model.track(
                        source=model_input,
                        persist=True,
                        tracker=args.tracker,
                        imgsz=args.imgsz,
                        conf=args.conf,
                        iou=args.iou,
                        device=parse_device(args.device),
                        verbose=False,
                    )
                    processing_ms = round((time.perf_counter() - started) * 1000.0, 3)
                    result = results[0]
                    people = result_people(result, person_class, frame, args.feet_edge_margin)

                    common = {
                        "frame_id": frame_id,
                        "capture_timestamp_ms": capture_timestamp_ms,
                        "camera_timestamp_ms": frame.camera_timestamp_ms,
                    }
                    sink.publish(
                        args.frame_event,
                        {
                            **common,
                            "width": frame.width,
                            "height": frame.height,
                            "image_data_url": png_data_url(image),
                        },
                    )
                    sink.publish(
                        args.detection_event,
                        {**common, "processing_ms": processing_ms, "persons": people},
                    )
                    published += 1
                    if args.max_frames is not None and published >= args.max_frames:
                        break
            except (ConnectionError, EOFError, OSError, RuntimeError, ValueError) as exc:
                print(f"Lepton stream error: {exc}; reconnecting", file=sys.stderr, flush=True)
                time.sleep(args.reconnect_delay)
    except KeyboardInterrupt:
        pass
    finally:
        sink.close()


if __name__ == "__main__":
    main()
