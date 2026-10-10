#!/usr/bin/env python3
"""VIGIL ground telemetry bridge.

Reads CRSF telemetry mirrored by the RadioMaster Pocket (EdgeTX, USB serial)
and publishes VehicleTelemetry JSON (one object per line) for the UI.

  ./telemetry_bridge.py --port /dev/serial/by-id/usb-EdgeTX...   live, from the Pocket
  ./telemetry_bridge.py --port ... --record flight1.crsf          live + save raw bytes
  ./telemetry_bridge.py --replay flight1.crsf                     replay a recording
  ./telemetry_bridge.py --synthetic                               fake drone, for UI development
  add  --udp 127.0.0.1:5600  to also send each JSON object as a UDP datagram

Fields with no real source are null, never invented:
  yaw_deg      null: no compass, so INAV's yaw has no north reference
               (--relative-yaw publishes it anyway, marked yaw_reference="relative")
  altitude_m, lat, lon, fix_valid   null until the drone sends GPS frames (milestone M4)
"""

from __future__ import annotations

import argparse
import json
import math
import signal
import socket
import sys
import time
from dataclasses import dataclass
from typing import Optional

import crsf

# INAV flight-mode strings sent while DISARMED (src/main/telemetry/crsf.c);
# every other string means armed.
DISARMED_MODES = {"OK", "!ERR", "WAIT"}

LINK_LOST_AFTER_S = 1.5     # no drone telemetry for this long -> link "lost"
LQ_DEGRADED_BELOW = 70      # uplink link quality (%) below this -> "degraded"
MIN_SATS_FOR_FIX = 6        # heuristic: CRSF's GPS frame carries no explicit fix flag


@dataclass
class _Timed:
    value: object
    t: float


class TelemetryState:
    """Latest decoded values plus the time each arrived (monotonic seconds)."""

    def __init__(self, relative_yaw: bool = False, source: str = "pocket") -> None:
        self.relative_yaw = relative_yaw
        self.source = source
        self.latest: dict[type, _Timed] = {}
        self.last_drone_frame: Optional[float] = None

    def update(self, decoded: crsf.Decoded, now: float) -> None:
        self.latest[type(decoded)] = _Timed(decoded, now)
        if not isinstance(decoded, crsf.LinkStats):  # link stats come from the TX module, not the drone
            self.last_drone_frame = now

    def _get(self, kind):
        entry = self.latest.get(kind)
        return entry.value if entry else None

    def link_state(self, now: float) -> str:
        if self.last_drone_frame is None:
            return "no_data"
        if now - self.last_drone_frame > LINK_LOST_AFTER_S:
            return "lost"
        link = self._get(crsf.LinkStats)
        if link is not None and link.uplink_lq < LQ_DEGRADED_BELOW:
            return "degraded"
        return "connected"

    def snapshot(self, now: float) -> dict:
        battery = self._get(crsf.Battery)
        attitude = self._get(crsf.Attitude)
        gps = self._get(crsf.Gps)
        mode = self._get(crsf.FlightMode)
        link = self._get(crsf.LinkStats)
        vario = self._get(crsf.Vario)

        fix_valid = None
        if gps is not None:
            fix_valid = gps.satellites >= MIN_SATS_FOR_FIX and not (gps.lat == 0 and gps.lon == 0)

        msg = {
            "timestamp_ms": int(time.time() * 1000),   # ground receive time
            "armed": None if mode is None else mode.mode not in DISARMED_MODES,
            "battery_v": None if battery is None else round(battery.voltage_v, 2),
            "roll_deg": None if attitude is None else round(attitude.roll_deg, 1),
            "pitch_deg": None if attitude is None else round(attitude.pitch_deg, 1),
            "yaw_deg": None,
            "altitude_m": None if gps is None else gps.altitude_m,
            "lat": gps.lat if fix_valid else None,
            "lon": gps.lon if fix_valid else None,
            "fix_valid": fix_valid,
            "link_state": self.link_state(now),
            # extras (not in the shared contract, safe for the UI to ignore)
            "flight_mode": None if mode is None else mode.mode,
            "climb_ms": None if vario is None else round(vario.climb_ms, 2),
            "satellites": None if gps is None else gps.satellites,
            "link": None if link is None else {
                "uplink_lq": link.uplink_lq,
                "uplink_rssi_dbm": link.uplink_rssi_dbm,
                "downlink_lq": link.downlink_lq,
                "downlink_rssi_dbm": link.downlink_rssi_dbm,
            },
            "data_age_ms": None if self.last_drone_frame is None else int((now - self.last_drone_frame) * 1000),
            "source": self.source,
        }
        if self.relative_yaw and attitude is not None:
            msg["yaw_deg"] = round(attitude.yaw_deg % 360.0, 1)
            msg["yaw_reference"] = "relative"
        return msg


# --- byte sources ----------------------------------------------------------

def open_serial(port: str):
    import serial  # pyserial; only needed for live input
    # USB CDC ignores the baud rate; timeout keeps the publish loop ticking.
    return serial.Serial(port, 115200, timeout=0.02)


class ReplaySource:
    """Replays a raw recording at roughly real time (CRSF telemetry is low-rate)."""

    def __init__(self, path: str, chunk: int = 64, rate_bps: int = 2000) -> None:
        self.data = open(path, "rb").read()
        self.pos = 0
        self.chunk = chunk
        self.delay = chunk / rate_bps

    def read(self, _n: int) -> bytes:
        if self.pos >= len(self.data):
            raise EOFError
        time.sleep(self.delay)
        out = self.data[self.pos:self.pos + self.chunk]
        self.pos += self.chunk
        return out


class SyntheticSource:
    """Fake drone gently rocking, disarmed then armed, 4S battery draining.

    Output is marked source="synthetic" so it can never be mistaken for real data.
    """

    def __init__(self) -> None:
        self.t0 = time.monotonic()

    def read(self, _n: int) -> bytes:
        time.sleep(0.05)
        t = time.monotonic() - self.t0
        roll = 10 * math.sin(t)
        pitch = 5 * math.sin(t / 2)
        att = crsf.build_frame(crsf.ATTITUDE, b"".join(
            int(math.radians(a) * 10000).to_bytes(2, "big", signed=True) for a in (pitch, roll, 0.0)))
        volts = max(14.0, 16.6 - t * 0.01)
        bat = crsf.build_frame(crsf.BATTERY, int(volts * 10).to_bytes(2, "big") + b"\x00\x00" + b"\x00\x00\x00" + bytes([80]))
        mode = crsf.build_frame(crsf.FLIGHT_MODE, (b"ANGL" if int(t) % 20 >= 10 else b"OK") + b"\x00")
        link = crsf.build_frame(crsf.LINK_STATISTICS, bytes([60, 0, 100, 10, 0, 7, 3, 65, 100, 8]))
        return att + bat + mode + link


# --- main loop -----------------------------------------------------------------

def run(source, state: TelemetryState, rate_hz: float, udp=None, record=None) -> None:
    parser = crsf.FrameParser()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if udp else None
    period = 1.0 / rate_hz
    next_pub = time.monotonic()
    while True:
        try:
            data = source.read(256)
        except EOFError:
            break
        if data:
            if record:
                record.write(data)
            now = time.monotonic()
            for ftype, payload in parser.feed(data):
                decoded = crsf.decode(ftype, payload)
                if decoded is not None:
                    state.update(decoded, now)
        now = time.monotonic()
        if now >= next_pub:
            next_pub = now + period
            line = json.dumps(state.snapshot(now), separators=(",", ":"))
            print(line, flush=True)
            if sock:
                sock.sendto(line.encode(), udp)


def _raise_keyboard_interrupt(_signum, _frame):
    raise KeyboardInterrupt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--port", help="Pocket USB serial device (EdgeTX, Telemetry Mirror mode)")
    src.add_argument("--replay", metavar="FILE", help="replay raw bytes saved with --record")
    src.add_argument("--synthetic", action="store_true", help="generate fake telemetry for UI work")
    ap.add_argument("--record", metavar="FILE", help="also save the raw serial bytes (live only)")
    ap.add_argument("--udp", metavar="HOST:PORT", help="also send each JSON object as a UDP datagram")
    ap.add_argument("--rate", type=float, default=10.0, help="publish rate in Hz (default 10)")
    ap.add_argument("--relative-yaw", action="store_true", help="publish yaw without a north reference")
    args = ap.parse_args()

    udp = None
    if args.udp:
        host, port = args.udp.rsplit(":", 1)
        udp = (host, int(port))

    if args.port:
        source, label = open_serial(args.port), "pocket"
    elif args.replay:
        source, label = ReplaySource(args.replay), "replay"
    else:
        source, label = SyntheticSource(), "synthetic"

    # Unbuffered, so a recording survives the bridge being killed mid-session.
    record = open(args.record, "ab", buffering=0) if args.record and args.port else None
    # Treat SIGTERM (e.g. from `timeout` or a service manager) like Ctrl+C.
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
    state = TelemetryState(relative_yaw=args.relative_yaw, source=label)
    try:
        run(source, state, args.rate, udp=udp, record=record)
    except (KeyboardInterrupt, BrokenPipeError):
        # Ctrl+C, or the consumer of stdout went away
        sys.stdout = None
    finally:
        if record:
            record.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
