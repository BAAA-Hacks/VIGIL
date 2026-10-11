#!/usr/bin/env python3
"""Stream native Lepton frames through YOLO and publish VIGIL website events."""

from __future__ import annotations

import argparse
import base64
import json
import logging
import signal
import struct
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
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


def open_raw_stream(camera_url: str, timeout: float):
    url = camera_url.rstrip("/") + "/raw"
    request = Request(url, headers={"Connection": "close", "User-Agent": "VIGIL-Lepton/1"})
    try:
        return urlopen(request, timeout=timeout)
    except HTTPError as exc:
        if exc.code == 503:
            raise RuntimeError("Lepton /raw is busy; only one raw-stream client is allowed") from exc
        raise RuntimeError(f"Lepton returned HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        raise ConnectionError(f"Could not connect to Lepton at {url}: {exc.reason}") from exc


def lepton_frames(camera_url: str, timeout: float) -> Iterable[LeptonFrame]:
    with open_raw_stream(camera_url, timeout) as response:
        while True:
            yield read_frame(response)


def latest_lepton_frames(camera_url: str, timeout: float) -> Iterable[tuple[LeptonFrame, int]]:
    """Yield (newest frame, arrival ms), skipping frames that arrived while the caller was busy.

    Reading in order lets frames queue in the socket buffer whenever processing falls
    behind, and the output then stays that many frames late for the rest of the session.
    """
    response = open_raw_stream(camera_url, timeout)
    ready = threading.Condition()
    state: dict = {"item": None, "error": None, "stop": False}

    def reader() -> None:
        try:
            while not state["stop"]:
                frame = read_frame(response)
                with ready:
                    state["item"] = (frame, time.time_ns() // 1_000_000)
                    ready.notify()
        except BaseException as exc:  # handed to the consumer below
            with ready:
                state["error"] = exc
                ready.notify()

    thread = threading.Thread(target=reader, name="lepton-reader", daemon=True)
    thread.start()
    try:
        while True:
            with ready:
                ready.wait_for(lambda: state["item"] is not None or state["error"] is not None)
                item, state["item"] = state["item"], None
                if item is None:
                    raise state["error"]
            yield item
    finally:
        state["stop"] = True
        try:
            response.close()  # frees the camera's single /raw slot; unblocks the reader
        except Exception:
            pass
        thread.join(timeout=timeout)


FLIPS = {
    "none": lambda pixels: pixels,
    "180": lambda pixels: pixels[::-1, ::-1],      # camera mounted upside down
    "horizontal": lambda pixels: pixels[:, ::-1],  # mirror left/right
    "vertical": lambda pixels: pixels[::-1, :],
}


def flip_frame(frame: LeptonFrame, flip: str) -> LeptonFrame:
    """Orient the frame before anything else uses it, so detection, temperatures, the
    published image and the recording all share upright image coordinates."""
    if flip == "none":
        return frame
    return replace(frame, pixels=np.ascontiguousarray(FLIPS[flip](frame.pixels)))


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


def _overlap(a: list[float], b: list[float]) -> tuple[float, float]:
    """(intersection over the smaller box, intersection over union)."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    area_a = max(1e-9, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1e-9, (b[2] - b[0]) * (b[3] - b[1]))
    return inter / min(area_a, area_b), inter / (area_a + area_b - inter)


def _area(box: list[float]) -> float:
    return max(1e-9, (box[2] - box[0]) * (box[3] - box[1]))


def suppress_contained(rows: list[list[float]], threshold: float, min_conf: float = 0.3,
                       group_span: float = 0.7) -> list[list[float]]:
    """Remove group boxes, then nested part boxes (keeping the whole person).

    A box is a group box when it holds two or more confident, mutually separate boxes that
    together span >= group_span of its width (people side by side); the group box goes.
    Head and torso part boxes inside one person are separate too but span only part of
    the width, so they do not trigger this. Then, largest first, a box with >= threshold
    of its area inside a kept box is a part box and goes.
    """
    def is_group(outer: list[float]) -> bool:
        inner = [r for r in rows if r is not outer and r[4] >= min_conf
                 and _area(r) < _area(outer) and _overlap(outer, r)[0] >= threshold]
        separate = [(a, b) for k, a in enumerate(inner) for b in inner[k + 1:] if _overlap(a, b)[1] < 0.3]
        width = outer[2] - outer[0]
        return any((max(a[2], b[2]) - min(a[0], b[0])) >= group_span * width for a, b in separate)

    rows = [r for r in rows if not is_group(r)]
    kept: list[list[float]] = []
    for row in sorted(rows, key=lambda r: -_area(r)):
        if all(_overlap(row, other)[0] < threshold for other in kept):
            kept.append(row)
    return kept


class MergedDetector:
    """Run a near-range and an optional far-range model, merge their boxes, track the union.

    Neither model covers every distance: the close-up model misses people beyond a few
    metres and the drone model hallucinates small "distant people" on skin and clothing up
    close. Far-model boxes shorter than `near_height` of the frame are dropped when their
    centre lies inside a tall box from either model (a distant person cannot be inside a
    near one), then class-agnostic NMS merges the rest before one ByteTrack instance.
    Finally any box lying mostly inside a more confident one is dropped: YOLO26 is NMS-free
    and, at the low keep threshold, emits nested torso/part boxes on the same person, which
    IoU-based NMS cannot remove because a part box has low IoU with the whole.
    """

    def __init__(self, models: list, person_classes: list[int], tracker_yaml: str, imgsz: int, iou: float,
                 device, near_height: float = 0.35, merge_iou: float = 0.45, contain: float = 0.8) -> None:
        import yaml
        from ultralytics.trackers.byte_tracker import BYTETracker
        from ultralytics.utils import IterableSimpleNamespace

        self.models = models
        self.person_classes = person_classes
        self.imgsz, self.iou, self.device = imgsz, iou, device
        self.near_height, self.merge_iou, self.contain = near_height, merge_iou, contain
        config = yaml.safe_load(Path(tracker_yaml).read_text(encoding="utf-8"))
        self.tracker = BYTETracker(IterableSimpleNamespace(**config))

    def __call__(self, image: np.ndarray, conf: float):
        import torch
        import torchvision
        from types import SimpleNamespace

        from ultralytics.engine.results import Boxes

        height, width = image.shape[:2]
        rows: list[list[float]] = []
        sources: list[int] = []
        for source, (model, person_class) in enumerate(zip(self.models, self.person_classes, strict=True)):
            result = model.predict(image, imgsz=self.imgsz, conf=conf, iou=self.iou, device=self.device,
                                   verbose=False)[0]
            if result.boxes is None:
                continue
            for xyxy, score, cls in zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist(),
                                        result.boxes.cls.tolist(), strict=True):
                if int(cls) == person_class:
                    rows.append([*xyxy, float(score)])
                    sources.append(source)
        if len(self.models) > 1 and rows:
            tall = [r for r in rows if (r[3] - r[1]) >= self.near_height * height]
            margin = 0.02 * width

            def contained(r: list[float]) -> bool:
                cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
                return any(t[0] - margin <= cx <= t[2] + margin and t[1] - margin <= cy <= t[3] + margin
                           for t in tall if t is not r)

            keep = [i for i, r in enumerate(rows)
                    if sources[i] == 0 or (r[3] - r[1]) >= self.near_height * height or not contained(r)]
            rows = [rows[i] for i in keep]
        if rows:
            boxes = torch.tensor([r[:4] for r in rows], dtype=torch.float32)
            scores = torch.tensor([r[4] for r in rows], dtype=torch.float32)
            rows = [rows[i] for i in torchvision.ops.nms(boxes, scores, self.merge_iou).tolist()]
            rows = suppress_contained(rows, self.contain)
        data = torch.tensor([[*r[:4], r[4], self.person_classes[0]] for r in rows], dtype=torch.float32).reshape(-1, 6)
        tracks = self.tracker.update(Boxes(data, (height, width)).cpu().numpy(), image)
        tracks = np.asarray(tracks)[:, :7] if len(tracks) else np.zeros((0, 7))
        # Two live tracks can settle on one person (e.g. started by different models); keep the
        # more confident one. Columns: x1, y1, x2, y2, track_id, score, cls.
        def duplicate(a: np.ndarray, b: np.ndarray) -> bool:
            inside, iou = _overlap(list(a[:4]), list(b[:4]))
            return inside >= self.contain or iou >= self.merge_iou

        kept: list[np.ndarray] = []
        for track in sorted(tracks, key=lambda t: -t[5]):
            if not any(duplicate(track, other) for other in kept):
                kept.append(track)
        tracked = torch.as_tensor(np.array(kept) if kept else np.zeros((0, 7)), dtype=torch.float32)
        return SimpleNamespace(boxes=Boxes(tracked, (height, width)), orig_shape=(height, width))


class TrackGate:
    """Only publish a track once it has been detected in `min_hits` frames.

    Flicker from clutter and partial views rarely survives several frames, while a real
    person does; the cost is min_hits frames of delay (~0.1 s each) before a new person shows.
    """

    def __init__(self, min_hits: int) -> None:
        self.min_hits = min_hits
        self.hits: dict[int, int] = {}

    def reset(self) -> None:
        self.hits.clear()

    def apply(self, people: list[dict]) -> list[dict]:
        if self.min_hits <= 1:
            return people
        output = []
        for person in people:
            track = person.get("tracking_id")
            if track is None:
                continue
            if not person.get("held"):
                self.hits[track] = self.hits.get(track, 0) + 1
            if self.hits.get(track, 0) >= self.min_hits:
                output.append(person)
        return output


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
    parser.add_argument(
        "--flip", choices=sorted(FLIPS), default="180",
        help="Image orientation fix. Default 180: the camera is mounted upside down on the drone; "
             "use 'none' for an upright camera",
    )
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
        default=0.15,
        help="Weaker detections that overlap an existing track keep it alive (ByteTrack second stage)",
    )
    parser.add_argument("--hold-frames", type=int, default=2, help="Frames to re-emit a vanished track (0 = off)")
    parser.add_argument("--min-hits", type=int, default=3, help="Frames a new track must be seen before it is shown")
    parser.add_argument(
        "--far-weights",
        default="AI/checkpoints/thermal_medium_range_yolo26s_p2_best.pt",
        help="Second model for distant people, merged with --weights each frame; 'none' disables",
    )
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


def _stop_like_ctrl_c(_signum, _frame) -> None:
    raise KeyboardInterrupt


def main() -> None:
    # Closing the terminal (SIGHUP) or a kill (SIGTERM) otherwise ends the process without
    # running the cleanup below, leaving annotated.mp4 unplayable and no summary.json.
    signal.signal(signal.SIGTERM, _stop_like_ctrl_c)
    signal.signal(signal.SIGHUP, _stop_like_ctrl_c)
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
    models, person_classes = [model], [person_class]
    if str(args.far_weights).lower() != "none":
        far_weights = Path(args.far_weights).expanduser().resolve()
        log.info("Loading far-range model %s", far_weights)
        far_model = load_model(far_weights)
        models.append(far_model)
        person_classes.append(model_person_class(far_model, args.person_class))
    info = environment_info(weights, model, args.device)
    info["far_weights"] = str(args.far_weights)
    recorder.write_config(info)
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
    gate = TrackGate(args.min_hits)
    if not 0 <= args.keep_conf <= args.conf:
        raise SystemExit("--keep-conf must be between 0 and --conf")
    import tempfile

    tracker_path = tracker_config(
        args.tracker, args.conf, args.keep_conf, args.track_buffer,
        recorder.directory or Path(tempfile.mkdtemp(prefix="vigil-tracker-")),
    )
    log.info("Tracker: %s (start>=%.2f keep>=%.2f buffer=%d hold=%d frames)",
             tracker_path, args.conf, args.keep_conf, args.track_buffer, args.hold_frames)
    detector = MergedDetector(models, person_classes, tracker_path, args.imgsz, args.iou, parse_device(args.device))
    # The first inference takes seconds (CUDA init); doing it mid-stream stalls the socket long
    # enough for the camera to drop the client, so warm every model up before connecting.
    started = time.perf_counter()
    blank = np.zeros((EXPECTED_HEIGHT, EXPECTED_WIDTH, 3), np.uint8)
    for warm_model in models:
        warm_model.predict(blank, imgsz=args.imgsz, device=parse_device(args.device), verbose=False)
    log.info("Models warmed up in %.1f s", time.perf_counter() - started)
    try:
        while args.max_frames is None or published < args.max_frames:
            try:
                log.info("Connecting to camera %s/raw", args.camera_url.rstrip("/"))
                first = True
                for frame, arrival_ms in latest_lepton_frames(args.camera_url, args.connect_timeout):
                    frame = flip_frame(frame, args.flip)
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
                    capture_timestamp_ms = arrival_ms
                    frame_id = f"lepton-{process_session}-{boot_session}-{frame.camera_frame_id}"
                    image = normalize_frame(frame)
                    model_input = temporal.model_input(image)

                    started = time.perf_counter()
                    result = detector(model_input, args.keep_conf)
                    processing_ms = round((time.perf_counter() - started) * 1000.0, 3)
                    people = gate.apply(hold.apply(
                        result_people(
                            result, person_class, frame, args.feet_edge_margin,
                            args.max_person_temp_c if args.max_person_temp_c >= 0 else None,
                        )
                    ))

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
