#!/usr/bin/env python3
"""Write a reconstructed drone track for a recorded session, keyed by camera frame index.

The flight in session 20261011_013730 has no telemetry (no GPS yet). This rebuilds it from
what is known: take-off on the lawn between Business Administration I and Biological
Sciences at UCF, a low flight (never above ~4 ft) north-east towards BA I, then landing.
`telemetry_bridge.py --track` replays the file in step with `./replay.sh`, so the drone on
the map moves, pauses and loops with the video. It is a reconstruction, not recorded GPS:
every keyframe is marked `reconstructed`.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

FPS = 8.7  # replay frame rate (fake_lepton default)
EARTH_M_PER_DEG_LAT = 110_574.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, default=Path("AI/recordings/session_20261011_013730"))
    parser.add_argument("--start-frame", type=int, default=1120)
    parser.add_argument("--end-frame", type=int, default=1400)
    parser.add_argument("--lat", type=float, default=28.600247, help="Take-off point (tree-lined grass patch between BA I and Bio Sci)")
    parser.add_argument("--lon", type=float, default=-81.19916)
    parser.add_argument("--heading", type=float, default=45.0, help="Direction of flight, degrees from north")
    parser.add_argument("--distance", type=float, default=7.0, help="Metres flown before landing (across the patch)")
    parser.add_argument("--height", type=float, default=1.2, help="Cruise height above take-off, metres (4 ft)")
    parser.add_argument("--climb-frames", type=int, default=30)
    parser.add_argument("--land-frames", type=int, default=25)
    return parser.parse_args()


def offset(lat: float, lon: float, north_m: float, east_m: float) -> tuple[float, float]:
    return (lat + north_m / EARTH_M_PER_DEG_LAT,
            lon + east_m / (EARTH_M_PER_DEG_LAT * math.cos(math.radians(lat))))


def smooth(x: float) -> float:
    """0 -> 1 ease in/out."""
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def main() -> None:
    args = parse_args()
    frames = range(args.start_frame, args.end_frame)
    total = len(frames)
    cruise_start = args.climb_frames
    cruise_end = total - args.land_frames
    cruise_s = (cruise_end - cruise_start) / FPS
    speed = args.distance / cruise_s
    keyframes = []
    for k, frame in enumerate(frames):
        progress = smooth((k - cruise_start) / max(1, cruise_end - cruise_start))
        travelled = args.distance * progress
        north = travelled * math.cos(math.radians(args.heading))
        east = travelled * math.sin(math.radians(args.heading))
        lat, lon = offset(args.lat, args.lon, north, east)
        if k < cruise_start:
            height = args.height * smooth(k / max(1, cruise_start))
        elif k >= cruise_end:
            height = args.height * (1 - smooth((k - cruise_end) / max(1, args.land_frames)))
        else:
            height = args.height
        moving = cruise_start <= k < cruise_end
        t = k / FPS
        armed = k < total - 3  # disarm just after touchdown
        keyframes.append({
            "frame": frame,
            "lat": round(lat, 7),
            "lon": round(lon, 7),
            "alt_m": round(height, 2),
            "heading_deg": round((args.heading + 6 * math.sin(2 * math.pi * t / 9)) % 360, 1),
            "pitch_deg": round((-3.0 if moving else 0.0) + 0.8 * math.sin(2 * math.pi * t / 3.1), 1),
            "roll_deg": round(1.2 * math.sin(2 * math.pi * t / 2.3 + 1.0), 1),
            "speed_ms": round(speed if moving else 0.0, 2),
            "course_deg": round(args.heading, 1),
            "armed": armed,
            "mode": "ANGL" if armed else "OK",
        })
    track = {
        "reconstructed": True,
        "description": "Reconstructed from the flight notes: take-off on the lawn between Business "
                       "Administration I and Biological Sciences (UCF), flown north-east towards BA I "
                       "at about 4 ft, then landed. Not recorded GPS.",
        "fps": FPS,
        "keyframes": keyframes,
    }
    out = args.session / "telemetry_track.json"
    out.write_text(json.dumps(track, indent=1), encoding="utf-8")
    end = keyframes[cruise_end - 1]
    print(f"Wrote {out}: {total} frames, {args.distance:.0f} m at {speed:.2f} m/s, "
          f"{args.height} m high, landing at {end['lat']}, {end['lon']}")


if __name__ == "__main__":
    main()
