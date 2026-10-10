#!/usr/bin/env python3
"""Read the Lepton streamer's /raw endpoint (standard library only).

Each record is a 24-byte little-endian header followed by width*height uint16 LE pixels:
  magic "LEP1" | u32 frame_id | u32 timestamp_ms | u16 width | u16 height
  | u16 raw_min | u16 raw_max | u32 flags (bit0 = TLinear)

Usage:
  python3 tools/lepton_raw.py                       # print per-second stats
  python3 tools/lepton_raw.py --save 5 --out frames # also write the first 5 frames as 8-bit PGM
"""

import argparse
import array
import os
import socket
import struct
import sys
import time
from urllib.parse import urlparse

HEADER = struct.Struct("<4sIIHHHHI")
MAGIC = b"LEP1"


def open_raw_stream(url, timeout=5.0):
    """Connects, sends GET, consumes the HTTP response header, returns a file-like reader."""
    parsed = urlparse(url)
    sock = socket.create_connection((parsed.hostname, parsed.port or 80), timeout=timeout)
    path = parsed.path or "/raw"
    sock.sendall(f"GET {path} HTTP/1.1\r\nHost: {parsed.hostname}\r\nConnection: close\r\n\r\n".encode())
    reader = sock.makefile("rb")
    status = reader.readline().decode("latin-1").strip()
    if " 200 " not in status + " ":
        raise RuntimeError(f"unexpected response: {status}")
    while reader.readline() not in (b"\r\n", b"\n", b""):
        pass
    return sock, reader


def read_exact(reader, length):
    data = reader.read(length)
    if data is None or len(data) != length:
        raise EOFError("stream closed")
    return data


def read_frames(reader):
    """Yields (header dict, pixels as array('H')) for each record."""
    while True:
        magic, frame_id, timestamp_ms, width, height, raw_min, raw_max, flags = HEADER.unpack(
            read_exact(reader, HEADER.size)
        )
        if magic != MAGIC:
            raise ValueError(f"bad record magic {magic!r}, stream out of sync")
        pixels = array.array("H")
        pixels.frombytes(read_exact(reader, width * height * 2))
        if sys.byteorder == "big":
            pixels.byteswap()
        yield {
            "frame_id": frame_id,
            "timestamp_ms": timestamp_ms,
            "width": width,
            "height": height,
            "raw_min": raw_min,
            "raw_max": raw_max,
            "tlinear": bool(flags & 1),
        }, pixels


def to_pgm(info, pixels):
    """Min/max-stretched 8-bit PGM bytes."""
    low, high = info["raw_min"], info["raw_max"]
    span = max(high - low, 1)
    body = bytes((v - low) * 255 // span for v in pixels)
    return f"P5 {info['width']} {info['height']} 255\n".encode() + body


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://192.168.4.1/raw")
    parser.add_argument("--save", type=int, default=0, help="number of frames to save as PGM")
    parser.add_argument("--out", default="frames")
    parser.add_argument("--count", type=int, default=0, help="stop after this many frames (0 = forever)")
    args = parser.parse_args()

    sock, reader = open_raw_stream(args.url)
    if args.save:
        os.makedirs(args.out, exist_ok=True)

    total = gaps = 0
    last_id = None
    window_start, window_frames = time.monotonic(), 0
    try:
        for info, pixels in read_frames(reader):
            total += 1
            window_frames += 1
            if last_id is not None and info["frame_id"] != last_id + 1:
                gaps += info["frame_id"] - last_id - 1
            last_id = info["frame_id"]
            if total <= args.save:
                with open(os.path.join(args.out, f"frame_{info['frame_id']:06d}.pgm"), "wb") as f:
                    f.write(to_pgm(info, pixels))
            now = time.monotonic()
            if now - window_start >= 1.0:
                print(
                    f"frame {info['frame_id']} fps={window_frames / (now - window_start):.2f} "
                    f"skipped={gaps} raw=[{info['raw_min']}, {info['raw_max']}]",
                    flush=True,
                )
                window_start, window_frames = now, 0
            if args.count and total >= args.count:
                break
    except EOFError:
        print("stream closed by the camera", file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
    print(f"received {total} frames, {gaps} skipped by the camera side")


if __name__ == "__main__":
    main()
