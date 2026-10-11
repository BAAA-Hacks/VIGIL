#!/usr/bin/env python3
"""Serve recorded thermal images as a fake Lepton `/raw` stream for demo rehearsal.

Sources: an image folder, a .txt image list, a video, or a `raw.lep` session recording
from lepton_live.py (replayed with its original raw values and TLinear flags).

Speaks the firmware's LEP1 record protocol (one raw client, 503 when busy), so
`lepton_live.py --camera-url http://127.0.0.1:8090` and the website run unchanged.
8-bit grayscale input is mapped onto a plausible TLinear range (kelvin x 100), so
`center_temperature_c` is populated; the values are illustrative, not measurements.
"""

from __future__ import annotations

import argparse
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

try:
    from AI.scripts.lepton_live import EXPECTED_HEIGHT, EXPECTED_WIDTH, HEADER, MAGIC, TLINEAR_FLAG, read_frame
    from AI.scripts.prepare_wisard import letterbox_grayscale
except ModuleNotFoundError:
    from AI.scripts.lepton_live import EXPECTED_HEIGHT, EXPECTED_WIDTH, HEADER, MAGIC, TLINEAR_FLAG, read_frame  # type: ignore
    from AI.scripts.prepare_wisard import letterbox_grayscale  # type: ignore


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".pgm"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Image directory, a .txt list of images, or a video file")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--fps", type=float, default=8.7, help="Lepton 3.5 delivers about 8.7 frames per second")
    parser.add_argument("--cold-c", type=float, default=10.0, help="Temperature mapped to black")
    parser.add_argument("--hot-c", type=float, default=40.0, help="Temperature mapped to white")
    parser.add_argument("--no-loop", action="store_true", help="Close the stream after the last frame")
    parser.add_argument("--start", type=int, default=0, help="First frame to serve (index into the source)")
    parser.add_argument("--end", type=int, default=None, help="Stop before this frame index (default: the end)")
    return parser.parse_args()


def load_frames(source: Path) -> list[np.ndarray]:
    source = source.expanduser()
    if source.is_dir():
        paths = sorted(p for p in source.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
        images = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in paths]
    elif source.suffix.lower() == ".txt":
        paths = [Path(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
        images = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in paths]
    else:
        capture = cv2.VideoCapture(str(source))
        images = []
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            images.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    frames = [
        letterbox_grayscale(image, EXPECTED_WIDTH, EXPECTED_HEIGHT, 0)[0]
        for image in images
        if image is not None
    ]
    if not frames:
        raise SystemExit(f"No readable frames in {source}")
    return frames


def load_recording(path: Path) -> list[tuple[np.ndarray, int]]:
    """Raw records from a lepton_live raw.lep file as (pixels, flags)."""
    records = []
    with path.open("rb") as stream:
        while True:
            try:
                frame = read_frame(stream)
            except EOFError:
                break
            records.append((frame.pixels.astype("<u2"), frame.flags))
    if not records:
        raise SystemExit(f"No complete LEP1 records in {path}")
    return records


def to_tlinear(frame: np.ndarray, cold_c: float, hot_c: float) -> np.ndarray:
    kelvin = cold_c + frame.astype(np.float32) / 255.0 * (hot_c - cold_c) + 273.15
    return np.clip(np.round(kelvin * 100.0), 0, 65535).astype("<u2")


def make_handler(records: list[tuple[np.ndarray, int]], args: argparse.Namespace):
    busy = threading.Lock()
    started = time.monotonic()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *values) -> None:
            print(f"[fake-lepton] {self.address_string()} {format % values}", flush=True)

        def do_GET(self) -> None:
            if self.path.split("?")[0] == "/status":
                body = f'{{"fake":true,"frames":{len(records)},"fps":{args.fps}}}\n'.encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.split("?")[0] != "/raw":
                self.send_error(404, "Endpoints: /raw /status")
                return
            if not busy.acquire(blocking=False):
                self.send_error(503, "Too many raw clients")
                return
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Record-Format", "LEP1")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                frame_id = 0
                interval = 1.0 / args.fps
                next_time = time.monotonic()
                while True:
                    for pixels, flags in records:
                        frame_id += 1
                        timestamp = int((time.monotonic() - started) * 1000) & 0xFFFFFFFF
                        header = HEADER.pack(
                            MAGIC, frame_id, timestamp, EXPECTED_WIDTH, EXPECTED_HEIGHT,
                            int(pixels.min()), int(pixels.max()), flags,
                        )
                        self.wfile.write(header + pixels.tobytes())
                        self.wfile.flush()
                        next_time += interval
                        time.sleep(max(0.0, next_time - time.monotonic()))
                    if args.no_loop:
                        return
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                busy.release()

    return Handler


def main() -> None:
    args = parse_args()
    if args.fps <= 0 or args.hot_c <= args.cold_c:
        raise SystemExit("--fps must be positive and --hot-c above --cold-c")
    if args.source.suffix.lower() == ".lep":
        records = load_recording(args.source.expanduser())
    else:
        records = [(to_tlinear(frame, args.cold_c, args.hot_c), TLINEAR_FLAG) for frame in load_frames(args.source)]
    records = records[args.start:args.end]
    if not records:
        raise SystemExit("--start/--end select no frames")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(records, args))
    print(f"Fake Lepton serving {len(records)} frames at {args.fps} fps on http://{args.host}:{args.port}/raw", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
