#!/usr/bin/env python3
"""VIGIL ground telemetry bridge.

Reads CRSF telemetry mirrored by the RadioMaster Pocket (EdgeTX, USB serial)
and publishes VehicleTelemetry JSON (one object per line) for the UI.

  ./telemetry_bridge.py --port /dev/serial/by-id/usb-EdgeTX...   live, from the Pocket
  ./telemetry_bridge.py --port ... --record flight1.crsf          live + save raw bytes
  ./telemetry_bridge.py --replay flight1.crsf                     replay a recording
  ./telemetry_bridge.py --synthetic                               scripted fake mission, for UI development
  add  --http 8765            to serve Server-Sent Events at http://HOST:8765/telemetry (browser EventSource)
  add  --udp 127.0.0.1:5600   to also send each JSON object as a UDP datagram

Fields with no real source are null, never invented:
  yaw_deg      null: no compass, so INAV's yaw has no north reference
               (--relative-yaw publishes it anyway, marked yaw_reference="relative")
  altitude_m, lat, lon, fix_valid, speed_ms, course_deg   null until the drone sends GPS frames (milestone M4)
  battery_v    null while the pack isn't connected to the board's voltage divider (reads < 2 V)
"""

from __future__ import annotations

import argparse
import json
import math
import signal
import socket
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import urlsplit

import crsf

# INAV flight-mode strings sent while DISARMED (src/main/telemetry/crsf.c);
# every other string means armed.
DISARMED_MODES = {"OK", "!ERR", "WAIT"}

LINK_LOST_AFTER_S = 1.5     # no drone telemetry for this long -> link "lost"
LQ_DEGRADED_BELOW = 70      # uplink link quality (%) below this -> "degraded"
MIN_SATS_FOR_FIX = 6        # heuristic: CRSF's GPS frame carries no explicit fix flag
BATTERY_PRESENT_ABOVE_V = 2.0  # below this the sense input is floating (no pack on the XT60)


@dataclass
class _Timed:
    value: object
    t: float


def _fix_valid(gps: Optional[crsf.Gps]) -> Optional[bool]:
    if gps is None:
        return None
    return gps.satellites >= MIN_SATS_FOR_FIX and not (gps.lat == 0 and gps.lon == 0)


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Equirectangular approximation; accurate to well under 1 m over a few km."""
    dn = math.radians(lat2 - lat1) * 6371000.0
    de = math.radians(lon2 - lon1) * 6371000.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dn, de)


class TelemetryState:
    """Latest decoded values plus the time each arrived (monotonic seconds)."""

    def __init__(self, relative_yaw: bool = False, source: str = "pocket") -> None:
        self.relative_yaw = relative_yaw
        self.source = source
        self.latest: dict[type, _Timed] = {}
        self.synthetic_started: Optional[float] = None
        self.last_drone_frame: Optional[float] = None
        self.armed_since: Optional[float] = None     # ground time of the last arm edge
        self.home: Optional[tuple[float, float]] = None  # first valid fix after arming (like INAV's home)

    def update(self, decoded: crsf.Decoded, now: float) -> None:
        self.latest[type(decoded)] = _Timed(decoded, now)
        if not isinstance(decoded, crsf.LinkStats):  # link stats come from the TX module, not the drone
            self.last_drone_frame = now
        if isinstance(decoded, crsf.FlightMode):
            armed = decoded.mode not in DISARMED_MODES
            if armed and self.armed_since is None:
                self.armed_since = now
                self.home = None
            elif not armed:
                self.armed_since = None
        gps = self._get(crsf.Gps)
        if self.armed_since is not None and self.home is None and _fix_valid(gps):
            self.home = (gps.lat, gps.lon)

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

        fix_valid = _fix_valid(gps)
        battery_present = battery is not None and battery.voltage_v >= BATTERY_PRESENT_ABOVE_V
        here = (gps.lat, gps.lon) if fix_valid else None

        # Explicit fake PCB reading only for the synthetic source; live CRSF has no PCB sensor.
        pcb_temp = None
        if self.source == "synthetic":
            if self.synthetic_started is None:
                self.synthetic_started = now
            pcb_temp = round(38.0 + min(5.0, max(0.0, now - self.synthetic_started) * 0.025), 1)

        msg = {
            "timestamp_ms": int(time.time() * 1000),   # ground receive time
            "armed": None if mode is None else mode.mode not in DISARMED_MODES,
            "battery_v": round(battery.voltage_v, 2) if battery_present else None,
            "pcb_temp_c": pcb_temp,
            "roll_deg": None if attitude is None else round(attitude.roll_deg, 1),
            # INAV sends pitch positive nose-down; the VehicleTelemetry contract is nose-up positive.
            "pitch_deg": None if attitude is None else round(-attitude.pitch_deg, 1),
            "yaw_deg": None,
            "altitude_m": None if gps is None else gps.altitude_m,
            "lat": gps.lat if fix_valid else None,
            "lon": gps.lon if fix_valid else None,
            "fix_valid": fix_valid,
            "link_state": self.link_state(now),
            # extras (not in the shared contract, safe for the UI to ignore)
            "flight_mode": None if mode is None else mode.mode,
            "battery_pct": battery.remaining_pct if battery_present else None,  # INAV, from voltage
            "climb_ms": None if vario is None else round(vario.climb_ms, 2),
            "speed_ms": round(gps.groundspeed_kmh / 3.6, 1) if fix_valid else None,
            "course_deg": round(gps.heading_deg % 360.0, 1) if fix_valid else None,
            "satellites": None if gps is None else gps.satellites,
            "home": None if self.home is None else {"lat": self.home[0], "lon": self.home[1]},
            "distance_home_m": round(_distance_m(*self.home, *here), 1) if self.home and here else None,
            "armed_time_s": None if self.armed_since is None else round(now - self.armed_since, 1),
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
    """Scripted ~110 s mission that exercises every frame the drone will eventually send
    (attitude, battery, flight mode, GPS, vario, link stats), looping forever:

      WAIT for GPS (satellites climb, no fix) -> OK (disarmed, fix) -> arm, ANGL climb to 10 m
      -> AH -> HOLD -> WP square (link degraded, then a 2.5 s dropout) -> RTH and land -> disarm

    It produces CRSF bytes, so it goes through the same decoder as live data.
    Output is marked source="synthetic" so it can never be mistaken for real data.
    """

    HOME = (28.6024, -81.2001)
    CELLS = 4
    # (seconds, INAV flight-mode string, north_m, east_m, alt_m at the END of the segment)
    SEGMENTS = [
        (12, "WAIT", 0, 0, 0),
        (8, "OK", 0, 0, 0),
        (10, "ANGL", 0, 0, 10),
        (12, "AH", 0, 0, 10),
        (12, "HOLD", 0, 0, 10),
        (10, "WP", 40, 0, 10),
        (10, "WP", 40, 40, 10),
        (5, "WP", 20, 40, 10),
        (2, "WP", 20, 40, 10),
        (11, "RTH", 0, 0, 10),
        (10, "RTH", 0, 0, 0),
        (8, "OK", 0, 0, 0),
    ]
    DEGRADED = (62.0, 68.0)   # uplink LQ drops to 55 %
    DROPOUT = (72.0, 74.5)    # no frames at all -> link_state "lost"

    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.cycle = sum(seg[0] for seg in self.SEGMENTS)
        self._pitch_deg = 0.0
        self._roll_deg = 0.0
        self._last_attitude_time = self.t0

    def _state(self, t: float) -> dict:
        start, pos, yaw, armed_s = 0.0, (0.0, 0.0, 0.0), 0.0, 0.0
        for dur, mode, n, e, alt in self.SEGMENTS:
            dn, de, da = n - pos[0], e - pos[1], alt - pos[2]
            if math.hypot(dn, de) > 0:
                yaw = math.degrees(math.atan2(de, dn)) % 360.0
            armed = mode not in DISARMED_MODES
            if t < start + dur:
                f = (t - start) / dur
                if armed:
                    armed_s += t - start
                return {
                    "mode": mode, "armed": armed, "armed_s": armed_s, "yaw": yaw,
                    "north": pos[0] + dn * f, "east": pos[1] + de * f, "alt": pos[2] + da * f,
                    "speed": math.hypot(dn, de) / dur, "climb": da / dur,
                }
            if armed:
                armed_s += dur
            start, pos = start + dur, (n, e, alt)
        raise AssertionError("t outside the mission")

    def read(self, _n: int) -> bytes:
        time.sleep(0.05)
        now = time.monotonic()
        t = (now - self.t0) % self.cycle
        if self.DROPOUT[0] <= t < self.DROPOUT[1]:
            return b""
        s = self._state(t)

        # Attitude: nose down when moving forward, plus a little hover wobble while armed.
        wobble = 0.3 if s["armed"] else 0.0
        target_pitch = -min(3.0, 0.6 * s["speed"]) + wobble * math.sin(0.2 * t)
        target_roll = (0.4 if s["armed"] else 0.0) * math.sin(0.25 * t + 1.0)
        # Limit attitude changes to 0.6 deg/s, including mission boundaries/dropout recovery.
        dt = max(0.0, min(0.2, now - self._last_attitude_time))
        self._last_attitude_time = now
        step = 0.6 * dt
        self._pitch_deg += max(-step, min(step, target_pitch - self._pitch_deg))
        self._roll_deg += max(-step, min(step, target_roll - self._roll_deg))
        pitch, roll = self._pitch_deg, self._roll_deg
        yaw = (s["yaw"] + 180.0) % 360.0 - 180.0  # INAV sends -180..180
        # pitch above is nose-up positive (the published contract); INAV puts nose-down positive on the wire.
        att = crsf.build_frame(crsf.ATTITUDE, b"".join(
            int(round(math.radians(a) * 10000)).to_bytes(2, "big", signed=True) for a in (-pitch, roll, yaw)))

        # Battery: 4S at rest 16.6 V, sags under load and drains while armed. No current sensor.
        volts = 16.6 - 0.012 * s["armed_s"] - (0.5 if s["armed"] else 0.0)
        pct = max(0, min(100, int((volts / self.CELLS - 3.3) / (4.2 - 3.3) * 100)))
        bat = crsf.build_frame(crsf.BATTERY, int(volts * 10).to_bytes(2, "big") + b"\x00\x00"
                               + b"\x00\x00\x00" + bytes([pct]))

        mode = crsf.build_frame(crsf.FLIGHT_MODE, s["mode"].encode() + b"\x00")

        # GPS: satellites climb during WAIT; before a fix INAV sends a zero position.
        sats = min(9, int(t * 0.8)) if s["mode"] == "WAIT" else 11 + int(math.sin(t / 7) > 0.5)
        if sats >= MIN_SATS_FOR_FIX:
            lat = self.HOME[0] + s["north"] / 111320.0
            lon = self.HOME[1] + s["east"] / (111320.0 * math.cos(math.radians(self.HOME[0])))
        else:
            lat = lon = 0.0
        gps = crsf.build_frame(crsf.GPS, int(lat * 1e7).to_bytes(4, "big", signed=True)
                               + int(lon * 1e7).to_bytes(4, "big", signed=True)
                               + int(s["speed"] * 3.6 * 10).to_bytes(2, "big")
                               + int(s["yaw"] * 100).to_bytes(2, "big")
                               + (int(round(s["alt"])) + 1000).to_bytes(2, "big") + bytes([sats]))
        vario = crsf.build_frame(crsf.VARIO, int(s["climb"] * 100).to_bytes(2, "big", signed=True))

        lq = 55 if self.DEGRADED[0] <= t < self.DEGRADED[1] else 100
        rssi = (-95 if lq < 70 else -45 - int(s["north"] / 4)) & 0xFF
        link = crsf.build_frame(crsf.LINK_STATISTICS, bytes([rssi, 0, lq, 10, 0, 7, 3, rssi, lq, 8]))
        return att + bat + mode + gps + vario + link


# --- Server-Sent Events output ----------------------------------------------

class SseHub:
    """Holds the latest JSON line; every connected browser gets each new one."""

    KEEPALIVE_S = 15.0

    def __init__(self) -> None:
        self.cond = threading.Condition()
        self.latest: Optional[str] = None
        self.seq = 0

    def publish(self, line: str) -> None:
        with self.cond:
            self.latest = line
            self.seq += 1
            self.cond.notify_all()

    def wait(self, seen: int, timeout: float) -> tuple[int, Optional[str]]:
        """Block until a line newer than `seen` exists (or timeout). Slow clients skip stale lines."""
        with self.cond:
            self.cond.wait_for(lambda: self.seq != seen, timeout)
            return self.seq, self.latest


def _make_handler(hub: SseHub):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:  # keep stdout for JSON lines only
            pass

        def _head(self, code: int, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")

        def do_OPTIONS(self) -> None:  # CORS preflight
            self._head(204, "text/plain")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()

        def do_GET(self) -> None:
            path = urlsplit(self.path).path.rstrip("/")
            if path == "/telemetry":
                self._stream()
            elif path == "/latest":
                body = (hub.latest or "null").encode()
                self._head(200, "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                body = b"VIGIL telemetry bridge: GET /telemetry (text/event-stream) or /latest (JSON)\n"
                self._head(404, "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def _stream(self) -> None:
            self._head(200, "text/event-stream")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                self.wfile.write(b"retry: 1000\n\n")  # browser reconnects after 1 s if the bridge restarts
                seen, line = hub.seq, hub.latest
                if line is not None:
                    self.wfile.write(f"data: {line}\n\n".encode())
                self.wfile.flush()
                while True:
                    seq, line = hub.wait(seen, SseHub.KEEPALIVE_S)
                    if seq == seen:
                        self.wfile.write(b": keepalive\n\n")
                    else:
                        seen = seq
                        self.wfile.write(f"data: {line}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass  # browser tab closed

    return Handler


def start_http(host: str, port: int) -> SseHub:
    hub = SseHub()
    server = ThreadingHTTPServer((host, port), _make_handler(hub))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="sse", daemon=True).start()
    print(f"SSE: http://{host}:{port}/telemetry", file=sys.stderr, flush=True)
    return hub


# --- main loop -----------------------------------------------------------------

def run(source, state: TelemetryState, rate_hz: float, udp=None, record=None, hub: Optional[SseHub] = None) -> None:
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
            if hub:
                hub.publish(line)


def _raise_keyboard_interrupt(_signum, _frame):
    raise KeyboardInterrupt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--port", help="Pocket USB serial device (EdgeTX, Telemetry Mirror mode)")
    src.add_argument("--replay", metavar="FILE", help="replay raw bytes saved with --record")
    src.add_argument("--synthetic", action="store_true", help="generate a scripted fake mission for UI work")
    ap.add_argument("--record", metavar="FILE", help="also save the raw serial bytes (live only)")
    ap.add_argument("--udp", metavar="HOST:PORT", help="also send each JSON object as a UDP datagram")
    ap.add_argument("--http", metavar="PORT", type=int, help="serve Server-Sent Events at /telemetry on this port")
    ap.add_argument("--http-host", default="127.0.0.1",
                    help="address for --http (default 127.0.0.1; 0.0.0.0 to allow other machines)")
    ap.add_argument("--rate", type=float, default=10.0, help="publish rate in Hz (default 10)")
    ap.add_argument("--relative-yaw", action="store_true",
                    help="publish yaw without a north reference (always on with --synthetic)")
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

    hub = start_http(args.http_host, args.http) if args.http else None
    # Unbuffered, so a recording survives the bridge being killed mid-session.
    record = open(args.record, "ab", buffering=0) if args.record and args.port else None
    # Treat SIGTERM (e.g. from `timeout` or a service manager) like Ctrl+C.
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
    state = TelemetryState(relative_yaw=args.relative_yaw or args.synthetic, source=label)
    try:
        run(source, state, args.rate, udp=udp, record=record, hub=hub)
    except (KeyboardInterrupt, BrokenPipeError):
        # Ctrl+C, or the consumer of stdout went away
        sys.stdout = None
    finally:
        if record:
            record.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
