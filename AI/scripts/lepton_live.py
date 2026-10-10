#!/usr/bin/env python3
"""Stream native Lepton frames through YOLO and publish VIGIL website events."""

from __future__ import annotations

import argparse
import base64
import json
import logging
import struct
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import cv2
import numpy as np

try:
    from AI.scripts.live_recorder import SessionRecorder, environment_info
    from AI.scripts.model_utils import load_model, parse_device
    from AI.scripts.temporal_utils import ALIGN_MODES, stack_frames
except ModuleNotFoundError:
    from AI.scripts.live_recorder import SessionRecorder, environment_info  # type: ignore
    from AI.scripts.model_utils import load_model, parse_device  # type: ignore
    from AI.scripts.temporal_utils import ALIGN_MODES, stack_frames  # type: ignore


HEADER = struct.Struct("<4sIIHHHHI")
MAGIC = b"LEP1"
EXPECTED_WIDTH = 160
EXPECTED_HEIGHT = 120
TLINEAR_FLAG = 1
MAX_TEMPORAL_GAP = 4


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


def hottest_temperature_c(frame: LeptonFrame, bbox: list[float]) -> float | None:
    """95th-percentile TLinear temperature inside the box (robust to single hot pixels)."""
    if not frame.flags & TLINEAR_FLAG:
        return None
    left, top, right, bottom = bbox
    x0 = min(frame.width - 1, max(0, int(left * (frame.width - 1))))
    y0 = min(frame.height - 1, max(0, int(top * (frame.height - 1))))
    x1 = max(x0 + 1, min(frame.width, int(np.ceil(right * (frame.width - 1))) + 1))
    y1 = max(y0 + 1, min(frame.height, int(np.ceil(bottom * (frame.height - 1))) + 1))
    region = frame.pixels[y0:y1, x0:x1].astype(np.float32)
    return round(float(np.percentile(region, 95)) / 100.0 - 273.15, 2)


def feet_visible(bbox: list[float], edge_margin: float) -> bool:
    """Conservative box-based heuristic; this is not pose estimation."""
    bottom = bbox[3]
    return bottom < 1.0 - edge_margin


class TemporalBuffer:
    """Builds [t-2k, t-k, t] model inputs; replicates the current frame until history fills."""

    def __init__(self, step: int, align: str) -> None:
        self.step = step
        self.align = align
        self.frames: deque[np.ndarray] = deque(maxlen=2 * step + 1)

    def reset(self) -> None:
        self.frames.clear()

    def model_input(self, image: np.ndarray) -> np.ndarray:
        self.frames.append(image)
        if self.step == 0:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        history = list(self.frames)

        def back(offset: int) -> np.ndarray:
            return history[-1 - offset] if len(history) > offset else image

        return stack_frames([back(2 * self.step), back(self.step), image], self.align)


class TrackHold:
    """Re-emit a vanished track's last box for a few frames, flagged `held`.

    ByteTrack keeps lost tracks internally but only outputs matched ones, so a single
    missed frame (motion smear, a dip below the keep threshold) blinks the person out.
    Held boxes decay in confidence and stop after `frames` misses or on a camera reset.
    """

    DECAY = 0.85

    def __init__(self, frames: int) -> None:
        self.frames = frames
        self.last: dict[int, tuple[dict, int]] = {}

    def reset(self) -> None:
        self.last.clear()

    def apply(self, people: list[dict]) -> list[dict]:
        if self.frames <= 0:
            return people
        seen = {p["tracking_id"] for p in people if p.get("tracking_id") is not None}
        held: list[dict] = []
        for track, (person, misses) in list(self.last.items()):
            if track in seen:
                continue
            misses += 1
            if misses > self.frames:
                del self.last[track]
                continue
            self.last[track] = (person, misses)
            ghost = dict(person, held=True, confidence=round(person["confidence"] * self.DECAY**misses, 6))
            held.append(ghost)
        for person in people:
            if person.get("tracking_id") is not None:
                self.last[person["tracking_id"]] = (person, 0)
        return people + held


def tracker_config(path: str, start_conf: float, keep_conf: float, buffer: int, directory: Path) -> str:
    """Write a ByteTrack config whose thresholds follow the CLI; the stock file is the base."""
    import yaml
    from ultralytics.utils import checks

    base = Path(checks.check_yaml(path)) if not Path(path).is_file() else Path(path)
    config = yaml.safe_load(base.read_text(encoding="utf-8"))
    if config.get("tracker_type") == "bytetrack":
        config.update(
            track_high_thresh=start_conf,
            new_track_thresh=start_conf,
            track_low_thresh=keep_conf,
            track_buffer=buffer,
        )
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / "tracker.yaml"
    output.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return str(output)


class JsonLineSink:
    def publish(self, event: str, payload: object) -> None:
        print(json.dumps({"event": event, "payload": payload}, separators=(",", ":")), flush=True)

    def close(self) -> None:
        return None


class SocketIOSink:
    """Publishes to the relay; never stops the detector when the relay is down or restarts."""

    RETRY_S = 3.0

    def __init__(self, url: str, namespace: str | None, recorder: SessionRecorder) -> None:
        try:
            import socketio
        except ImportError as exc:
            raise SystemExit(
                "Socket.IO output requires `python -m pip install 'python-socketio[client]'`."
            ) from exc
        self.url = url
        self.namespace = namespace
        self.recorder = recorder
        self.log = recorder.log
        self.client = socketio.Client(reconnection=True, logger=False, engineio_logger=False)
        self.client.on("connect", self.on_connect, namespace=namespace or "/")
        self.client.on("disconnect", lambda *_: self.log.warning("Relay disconnected"), namespace=namespace or "/")
        self.next_attempt = 0.0
        self.failing = False
        self.unavailable_logged = False
        self.connect()

    def on_connect(self) -> None:
        self.log.info("Relay connected: %s", self.url)
        self.unavailable_logged = False

    def connect(self) -> None:
        if self.client.connected or time.monotonic() < self.next_attempt:
            return
        self.next_attempt = time.monotonic() + self.RETRY_S
        try:
            self.client.connect(self.url, namespaces=[self.namespace] if self.namespace else None, wait_timeout=2)
        except Exception as exc:
            level = logging.DEBUG if self.unavailable_logged else logging.WARNING
            self.log.log(level, "Relay %s unavailable (%s); recording continues, retrying every %.0f s",
                         self.url, exc, self.RETRY_S)
            self.unavailable_logged = True

    def publish(self, event: str, payload: object) -> None:
        if not self.client.connected:
            self.connect()
        try:
            self.client.emit(event, payload, namespace=self.namespace)
            if self.failing:
                self.log.info("Relay publishing resumed")
                self.failing = False
        except Exception as exc:
            self.recorder.publish_failures += 1
            if not self.failing:
                self.log.warning("Relay publish failed (%s); frames are still recorded", exc)
                self.failing = True

    def close(self) -> None:
        try:
            self.client.disconnect()
        except Exception:
            pass


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


def result_people(
    result, person_class: int, frame: LeptonFrame, edge_margin: float, max_person_temp_c: float | None = None
) -> list[dict]:
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
        hottest = hottest_temperature_c(frame, bbox)
        if max_person_temp_c is not None and hottest is not None and hottest > max_person_temp_c:
            # Skin and clothing stay well below this; hot electronics, lamps and engines do not.
            continue
        people.append(
            {
                "bbox": bbox,
                "bottom_center": [round((bbox[0] + bbox[2]) / 2.0, 6), bbox[3]],
                "tracking_id": tracking_id,
                "confidence": round(float(confidence), 6),
                "feet_visible": feet_visible(bbox, edge_margin),
                "center_temperature_c": center_temperature_c(frame, bbox),
                "hottest_temperature_c": hottest,
                "class": "person",
                "held": False,
            }
        )
    return people


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--weights",
        type=Path,
        default=Path("AI/checkpoints/thermal_medium_range_yolo26s_p2_closeup_blur_best.pt"),
    )
    parser.add_argument("--camera-url", default="http://192.168.4.1")
    parser.add_argument("--socket-url", help="Website Socket.IO URL; omit for JSON-lines stdout")
    parser.add_argument("--socket-namespace", default=None)
    parser.add_argument("--frame-event", default="vigil:frame")
    parser.add_argument("--detection-event", default="vigil:detection")
    parser.add_argument("--device", default="0")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.30, help="Confidence needed to start a person track")
    parser.add_argument(
        "--keep-conf",
        type=float,
        default=0.10,
        help="Weaker detections that overlap an existing track keep it alive (ByteTrack second stage)",
    )
    parser.add_argument("--hold-frames", type=int, default=4, help="Frames to re-emit a vanished track (0 = off)")
    parser.add_argument("--track-buffer", type=int, default=30, help="Frames ByteTrack remembers a lost track")
    parser.add_argument(
        "--max-person-temp-c",
        type=float,
        default=42.0,
        help="Drop boxes whose hottest region exceeds this (TLinear only); negative disables",
    )
    parser.add_argument("--iou", type=float, default=0.70)
    parser.add_argument("--tracker", default="bytetrack.yaml")
    parser.add_argument("--person-class", default="person")
    parser.add_argument("--feet-edge-margin", type=float, default=0.01)
    parser.add_argument("--connect-timeout", type=float, default=5.0)
    parser.add_argument("--reconnect-delay", type=float, default=1.0)
    parser.add_argument(
        "--temporal-step",
        type=int,
        default=0,
        help="k for temporal models ([t-2k, t-k, t] as channels); 0 for single-frame models",
    )
    parser.add_argument("--temporal-align", choices=ALIGN_MODES, default="none")
    parser.add_argument("--max-frames", type=int, help="Stop after N frames; useful for testing")
    parser.add_argument(
        "--record",
        type=Path,
        default=Path("AI/recordings"),
        help="Directory for session recordings (raw stream, frames, boxes, logs)",
    )
    parser.add_argument("--no-record", action="store_true", help="Log to the terminal only; save nothing")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.imgsz <= 0 or args.max_frames is not None and args.max_frames <= 0:
        raise SystemExit("--imgsz and --max-frames must be positive")
    if not 0 <= args.conf <= 1 or not 0 <= args.iou <= 1:
        raise SystemExit("--conf and --iou must be between zero and one")
    if args.temporal_step < 0:
        raise SystemExit("--temporal-step cannot be negative")
    if not 0 <= args.feet_edge_margin < 0.5:
        raise SystemExit("--feet-edge-margin must be in [0, 0.5)")

    recorder = SessionRecorder(None if args.no_record else args.record, args, HEADER)
    log = recorder.log
    weights = args.weights.expanduser().resolve()
    log.info("Loading model %s", weights)
    model = load_model(weights)
    person_class = model_person_class(model, args.person_class)
    recorder.write_config(environment_info(weights, model, args.device))
    sink: EventSink = (
        SocketIOSink(args.socket_url, args.socket_namespace, recorder) if args.socket_url else JsonLineSink()
    )
    log.info("Output: %s", f"Socket.IO relay {args.socket_url}" if args.socket_url else "JSON lines on stdout")
    published = 0
    boot_session = 0
    process_session = time.time_ns() // 1_000_000
    last_camera_frame: int | None = None
    temporal = TemporalBuffer(args.temporal_step, args.temporal_align)
    hold = TrackHold(args.hold_frames)
    if not 0 <= args.keep_conf <= args.conf:
        raise SystemExit("--keep-conf must be between 0 and --conf")
    import tempfile

    tracker_path = tracker_config(
        args.tracker, args.conf, args.keep_conf, args.track_buffer,
        recorder.directory or Path(tempfile.mkdtemp(prefix="vigil-tracker-")),
    )
    log.info("Tracker: %s (start>=%.2f keep>=%.2f buffer=%d hold=%d frames)",
             tracker_path, args.conf, args.keep_conf, args.track_buffer, args.hold_frames)
    try:
        while args.max_frames is None or published < args.max_frames:
            try:
                log.info("Connecting to camera %s/raw", args.camera_url.rstrip("/"))
                first = True
                for frame in lepton_frames(args.camera_url, args.connect_timeout):
                    if first:
                        log.info("Camera streaming (first frame id %d, TLinear=%s)",
                                 frame.camera_frame_id, bool(frame.flags & TLINEAR_FLAG))
                        first = False
                    recorder.camera_frame(frame)
                    if last_camera_frame is not None and frame.camera_frame_id <= last_camera_frame:
                        boot_session += 1
                        temporal.reset()
                        hold.reset()
                    elif (
                        last_camera_frame is not None
                        and frame.camera_frame_id - last_camera_frame > MAX_TEMPORAL_GAP
                    ):
                        # /raw sends the newest frame, so small skips are normal; a long gap
                        # means the history no longer shows recent motion.
                        temporal.reset()
                        hold.reset()
                    last_camera_frame = frame.camera_frame_id
                    capture_timestamp_ms = time.time_ns() // 1_000_000
                    frame_id = f"lepton-{process_session}-{boot_session}-{frame.camera_frame_id}"
                    image = normalize_frame(frame)
                    model_input = temporal.model_input(image)

                    started = time.perf_counter()
                    results = model.track(
                        source=model_input,
                        persist=True,
                        tracker=tracker_path,
                        imgsz=args.imgsz,
                        conf=args.keep_conf,
                        iou=args.iou,
                        device=parse_device(args.device),
                        verbose=False,
                    )
                    processing_ms = round((time.perf_counter() - started) * 1000.0, 3)
                    result = results[0]
                    people = hold.apply(
                        result_people(
                            result, person_class, frame, args.feet_edge_margin,
                            args.max_person_temp_c if args.max_person_temp_c >= 0 else None,
                        )
                    )

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
                    recorder.detection(frame, image, frame_id, capture_timestamp_ms, processing_ms, people)
                    published += 1
                    if args.max_frames is not None and published >= args.max_frames:
                        break
            except (ConnectionError, EOFError, OSError, RuntimeError, ValueError) as exc:
                recorder.stream_errors += 1
                log.warning("Lepton stream error: %s; reconnecting in %.1f s", exc, args.reconnect_delay)
                temporal.reset()
                hold.reset()
                time.sleep(args.reconnect_delay)
    except KeyboardInterrupt:
        log.info("Stopped by user (Ctrl+C)")
    except Exception:
        log.exception("Fatal error in live loop")
        raise
    finally:
        sink.close()
        recorder.close()


if __name__ == "__main__":
    main()
