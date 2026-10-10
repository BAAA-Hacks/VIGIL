#!/usr/bin/env python3
"""Replay recorded raw.lep sessions through the live pipeline offline, as fast as the GPU allows.

Uses lepton_live's own normalization, tracker config, track hold and temperature gate, so
results match a live run with the same settings (minus live frame drops). Compares models
on identical footage without needing the camera.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import cv2

try:
    from AI.scripts.lepton_live import (
        TrackHold,
        model_person_class,
        normalize_frame,
        read_frame,
        result_people,
        tracker_config,
    )
    from AI.scripts.model_utils import load_model, parse_device
except ModuleNotFoundError:
    from AI.scripts.lepton_live import (  # type: ignore
        TrackHold,
        model_person_class,
        normalize_frame,
        read_frame,
        result_people,
        tracker_config,
    )
    from AI.scripts.model_utils import load_model, parse_device  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sessions", nargs="+", type=Path, help="Session dirs or raw.lep files")
    parser.add_argument("--weights", nargs="+", type=Path, required=True)
    parser.add_argument("--device", default="0")
    parser.add_argument("--conf", type=float, default=0.30)
    parser.add_argument("--keep-conf", type=float, default=0.10)
    parser.add_argument("--hold-frames", type=int, default=4)
    parser.add_argument("--max-person-temp-c", type=float, default=42.0)
    parser.add_argument("--output", type=Path, help="Write per-frame results as JSON")
    return parser.parse_args()


def load_raw(path: Path) -> list:
    path = path / "raw.lep" if path.is_dir() else path
    frames = []
    with path.open("rb") as stream:
        while True:
            try:
                frames.append(read_frame(stream))
            except EOFError:
                return frames


def replay(weights: Path, frames: list, args) -> list[list[dict]]:
    model = load_model(weights.expanduser().resolve())
    person_class = model_person_class(model, "person")
    tracker = tracker_config("bytetrack.yaml", args.conf, args.keep_conf, 30, Path(tempfile.mkdtemp()))
    hold = TrackHold(args.hold_frames)
    device = parse_device(args.device)
    outputs = []
    for frame in frames:
        image = cv2.cvtColor(normalize_frame(frame), cv2.COLOR_GRAY2BGR)
        result = model.track(source=image, persist=True, tracker=tracker, imgsz=640, conf=args.keep_conf,
                             iou=0.7, device=device, verbose=False)[0]
        gate = args.max_person_temp_c if args.max_person_temp_c >= 0 else None
        outputs.append(hold.apply(result_people(result, person_class, frame, 0.01, gate)))
    return outputs


def summarize(people_per_frame: list[list[dict]]) -> dict:
    on = [bool(people) for people in people_per_frame]
    n = len(on)
    episodes = sum(1 for i in range(n) if on[i] and (i == 0 or not on[i - 1]))
    blinks = sum(1 for i in range(1, n - 1) if on[i - 1] and not on[i] and any(on[i + 1:i + 4]))
    confident = [max((p["confidence"] for p in people if not p["held"]), default=0.0) for people in people_per_frame]
    return {
        "frames": n,
        "frames_with_person": sum(on),
        "episodes": episodes,
        "blinks": blinks,
        "held_frames": sum(any(p["held"] for p in people) for people in people_per_frame),
        "tracks": len({p["tracking_id"] for people in people_per_frame for p in people if p["tracking_id"] is not None}),
        "mean_conf_when_on": round(sum(c for c in confident if c) / max(1, sum(1 for c in confident if c)), 3),
    }


def main() -> None:
    args = parse_args()
    report: dict = {}
    for session in args.sessions:
        frames = load_raw(session.expanduser())
        name = session.name if session.is_dir() else session.parent.name
        report[name] = {}
        for weights in args.weights:
            people = replay(weights, frames, args)
            summary = summarize(people)
            report[name][weights.stem] = {"summary": summary, "frames": people}
            print(f"{name} {weights.stem:45s} {summary}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report), encoding="utf-8")


if __name__ == "__main__":
    main()
