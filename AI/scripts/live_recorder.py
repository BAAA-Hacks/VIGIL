"""Session recording and logging for lepton_live.py.

Each run writes one directory:
  log.txt            full log: config, connections, errors with tracebacks, 5 s status lines
  config.json        arguments, model, versions, host, git commit
  raw.lep            raw LEP1 camera records, replayable with fake_lepton.py
  detections.jsonl   one line per frame: ids, timing, camera stats, people (boxes, conf, temp)
  frames/            8-bit grayscale frame exactly as the model saw it
  annotated/         4x upscaled JPEG with boxes, confidence, track id and temperature
  annotated.mp4      annotated frames as video (4x upscaled)
  summary.json       totals written on exit
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import socket
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


LOGGER_NAME = "vigil.live"
STATUS_INTERVAL_S = 5.0
VIDEO_SCALE = 4


def setup_logging(log_path: Path | None) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)
    if log_path is not None:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5, check=True
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def environment_info(weights: Path, model, device: str) -> dict:
    info: dict = {
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "git_commit": git_commit(),
        "weights": str(weights),
        "weights_md5": file_md5(weights),
        "model_names": {str(k): v for k, v in dict(model.names).items()},
        "device_requested": device,
    }
    try:
        import torch
        import ultralytics

        info["torch"] = torch.__version__
        info["ultralytics"] = ultralytics.__version__
        info["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            info["cuda_device"] = torch.cuda.get_device_name(0)
    except Exception as exc:  # version probing must never stop a live run
        info["version_probe_error"] = repr(exc)
    return info


def annotate(image: np.ndarray, people: list[dict]) -> np.ndarray:
    """Upscaled BGR frame with boxes, confidence, track id and nominal temperature."""
    canvas = cv2.resize(
        cv2.cvtColor(image, cv2.COLOR_GRAY2BGR),
        (image.shape[1] * VIDEO_SCALE, image.shape[0] * VIDEO_SCALE),
        interpolation=cv2.INTER_NEAREST,
    )
    height, width = canvas.shape[:2]
    for person in people:
        left, top, right, bottom = person["bbox"]
        p1 = (int(left * width), int(top * height))
        p2 = (int(right * width) - 1, int(bottom * height) - 1)
        colour = (0, 200, 255) if person.get("feet_visible") else (0, 0, 255)
        cv2.rectangle(canvas, p1, p2, colour, 2)
        parts = [f"{person['confidence']:.2f}"]
        if person.get("tracking_id") is not None:
            parts.insert(0, f"#{person['tracking_id']}")
        if person.get("center_temperature_c") is not None:
            parts.append(f"{person['center_temperature_c']:.1f}C")
        label = " ".join(parts)
        y = max(14, p1[1] - 4)
        cv2.putText(canvas, label, (p1[0], y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(canvas, label, (p1[0], y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, colour, 1, cv2.LINE_AA)
    return canvas


class SessionRecorder:
    """Writes every frame, detection, and status line of a live session to disk."""

    def __init__(self, root: Path | None, args, header) -> None:
        self.started = time.monotonic()
        self.started_wall = datetime.now()
        self.header = header
        self.directory: Path | None = None
        if root is not None:
            name = self.started_wall.strftime("session_%Y%m%d_%H%M%S")
            self.directory = root.expanduser().resolve() / name
            (self.directory / "frames").mkdir(parents=True)
            (self.directory / "annotated").mkdir()
        self.log = setup_logging(self.directory / "log.txt" if self.directory else None)
        self.args = args
        self.raw_file = (self.directory / "raw.lep").open("ab") if self.directory else None
        self.jsonl = (self.directory / "detections.jsonl").open("a", encoding="utf-8") if self.directory else None
        self.video: cv2.VideoWriter | None = None
        self.frames = 0
        self.frames_with_people = 0
        self.people_total = 0
        self.max_people = 0
        self.track_ids: set[int] = set()
        self.camera_gaps = 0
        self.camera_dropped = 0
        self.camera_reboots = 0
        self.stream_errors = 0
        self.publish_failures = 0
        self.processing: deque[float] = deque(maxlen=200)
        self.all_processing_total = 0.0
        self.max_processing = 0.0
        self.window_frames = 0
        self.last_status = time.monotonic()
        self.last_camera_frame: int | None = None
        self.raw_min = self.raw_max = None
        if self.directory:
            self.log.info("Recording session to %s", self.directory)

    def write_config(self, info: dict) -> None:
        config = {"arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(self.args).items()}, **info}
        self.log.info("Config: %s", json.dumps(config))
        if self.directory:
            (self.directory / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    def camera_frame(self, frame) -> None:
        """Track camera frame continuity and store the raw record."""
        if self.last_camera_frame is not None:
            if frame.camera_frame_id <= self.last_camera_frame:
                self.camera_reboots += 1
                self.log.warning(
                    "Camera frame counter went %d -> %d: camera rebooted or reconnected",
                    self.last_camera_frame, frame.camera_frame_id,
                )
            elif frame.camera_frame_id > self.last_camera_frame + 1:
                skipped = frame.camera_frame_id - self.last_camera_frame - 1
                self.camera_gaps += 1
                self.camera_dropped += skipped
                level = logging.WARNING if skipped > 4 else logging.DEBUG
                self.log.log(level, "Skipped %d camera frame(s) before %d", skipped, frame.camera_frame_id)
        self.last_camera_frame = frame.camera_frame_id
        self.raw_min, self.raw_max = frame.raw_min, frame.raw_max
        if self.raw_file:
            self.raw_file.write(
                self.header.pack(
                    b"LEP1", frame.camera_frame_id, frame.camera_timestamp_ms, frame.width, frame.height,
                    frame.raw_min, frame.raw_max, frame.flags,
                )
                + frame.pixels.astype("<u2").tobytes()
            )
            self.raw_file.flush()

    def detection(self, frame, image: np.ndarray, frame_id: str, capture_ms: int, processing_ms: float,
                  people: list[dict]) -> None:
        index = self.frames
        self.frames += 1
        self.window_frames += 1
        self.processing.append(processing_ms)
        self.all_processing_total += processing_ms
        self.max_processing = max(self.max_processing, processing_ms)
        if people:
            self.frames_with_people += 1
        self.people_total += len(people)
        self.max_people = max(self.max_people, len(people))
        new_tracks = {p["tracking_id"] for p in people if p.get("tracking_id") is not None} - self.track_ids
        for track in sorted(new_tracks):
            person = next(p for p in people if p.get("tracking_id") == track)
            self.log.info(
                "New person track #%d at frame %d (conf %.2f, box %s)",
                track, index, person["confidence"], person["bbox"],
            )
        self.track_ids |= new_tracks

        if self.directory:
            stem = f"{index:06d}"
            frame_path = self.directory / "frames" / f"{stem}.png"
            annotated_path = self.directory / "annotated" / f"{stem}.jpg"
            cv2.imwrite(str(frame_path), image)
            annotated = annotate(image, people)
            cv2.imwrite(str(annotated_path), annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if self.video is None:
                self.video = cv2.VideoWriter(
                    str(self.directory / "annotated.mp4"),
                    cv2.VideoWriter_fourcc(*"mp4v"),
                    8.7,
                    (annotated.shape[1], annotated.shape[0]),
                )
            self.video.write(annotated)
            record = {
                "index": index,
                "frame_id": frame_id,
                "camera_frame_id": frame.camera_frame_id,
                "capture_timestamp_ms": capture_ms,
                "camera_timestamp_ms": frame.camera_timestamp_ms,
                "processing_ms": processing_ms,
                "raw_min": frame.raw_min,
                "raw_max": frame.raw_max,
                "tlinear": bool(frame.flags & 1),
                "persons": people,
                "frame_png": f"frames/{stem}.png",
                "annotated_jpg": f"annotated/{stem}.jpg",
            }
            self.jsonl.write(json.dumps(record, separators=(",", ":")) + "\n")
            self.jsonl.flush()
        self.maybe_status(people)

    def maybe_status(self, people: list[dict], force: bool = False) -> None:
        now = time.monotonic()
        elapsed = now - self.last_status
        if not force and elapsed < STATUS_INTERVAL_S:
            return
        recent = list(self.processing)
        mean_ms = sum(recent) / len(recent) if recent else 0.0
        temps = [p["center_temperature_c"] for p in people if p.get("center_temperature_c") is not None]
        self.log.info(
            "STATUS frames=%d fps=%.1f infer_ms(mean=%.1f max=%.1f) people_now=%d tracks_total=%d "
            "frames_with_people=%d camera_gaps=%d dropped=%d reboots=%d stream_errors=%d publish_failures=%d "
            "raw_range=%s..%s temps_now=%s",
            self.frames, self.window_frames / elapsed if elapsed > 0 else 0.0, mean_ms,
            max(recent) if recent else 0.0, len(people), len(self.track_ids), self.frames_with_people,
            self.camera_gaps, self.camera_dropped, self.camera_reboots, self.stream_errors,
            self.publish_failures, self.raw_min, self.raw_max, temps,
        )
        self.window_frames = 0
        self.last_status = now

    def close(self) -> None:
        duration = time.monotonic() - self.started
        summary = {
            "started": self.started_wall.isoformat(timespec="seconds"),
            "duration_s": round(duration, 1),
            "frames": self.frames,
            "mean_fps": round(self.frames / duration, 2) if duration > 0 else None,
            "mean_processing_ms": round(self.all_processing_total / self.frames, 2) if self.frames else None,
            "max_processing_ms": round(self.max_processing, 2),
            "frames_with_people": self.frames_with_people,
            "people_detections": self.people_total,
            "max_people_in_frame": self.max_people,
            "unique_tracks": len(self.track_ids),
            "camera_gaps": self.camera_gaps,
            "camera_frames_dropped": self.camera_dropped,
            "camera_reboots": self.camera_reboots,
            "stream_errors": self.stream_errors,
            "publish_failures": self.publish_failures,
        }
        self.log.info("Session summary: %s", json.dumps(summary))
        if self.video is not None:
            self.video.release()
        for handle in (self.raw_file, self.jsonl):
            if handle:
                handle.close()
        if self.directory:
            (self.directory / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            self.log.info("Session saved: %s", self.directory)
