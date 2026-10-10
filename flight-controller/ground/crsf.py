"""CRSF frame parsing and decoding for INAV telemetry.

Frame layout: [address][length][type][payload ...][crc8]
  length = len(type + payload + crc)
  crc8   = CRC-8/DVB-S2 (poly 0xD5) over type + payload
All multi-byte fields are big-endian.

Payload formats follow INAV 7.1.2 src/main/telemetry/crsf.c and the ExpressLRS
link-statistics frame.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Iterator, Optional, Union

# Frame types
GPS = 0x02
VARIO = 0x07
BATTERY = 0x08
LINK_STATISTICS = 0x14
RC_CHANNELS = 0x16
ATTITUDE = 0x1E
FLIGHT_MODE = 0x21

# Addresses that can start a frame (FC, radio, receiver, TX module, broadcast/sync)
ADDRESSES = {0x00, 0xC8, 0xEA, 0xEC, 0xEE}

MIN_LEN = 2   # type + crc
MAX_LEN = 62  # CRSF max frame is 64 bytes including address and length


def crc8_dvb_s2(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0xD5) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def build_frame(frame_type: int, payload: bytes, address: int = 0xEA) -> bytes:
    """Encode a CRSF frame (used by tests and the synthetic source)."""
    body = bytes([frame_type]) + payload
    return bytes([address, len(body) + 1]) + body + bytes([crc8_dvb_s2(body)])


class FrameParser:
    """Incremental parser: feed raw bytes, iterate (type, payload) of valid frames.

    Resynchronises on garbage or CRC errors by dropping one byte at a time.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self.crc_errors = 0
        self.frames = 0

    def feed(self, data: bytes) -> Iterator[tuple[int, bytes]]:
        self._buf.extend(data)
        buf = self._buf
        while len(buf) >= 2:
            if buf[0] not in ADDRESSES or not (MIN_LEN <= buf[1] <= MAX_LEN):
                del buf[0]
                continue
            total = buf[1] + 2
            if len(buf) < total:
                break
            body = bytes(buf[2:total - 1])
            if crc8_dvb_s2(body) != buf[total - 1]:
                self.crc_errors += 1
                del buf[0]
                continue
            del buf[:total]
            self.frames += 1
            yield body[0], body[1:]


@dataclass
class Battery:
    voltage_v: float
    current_a: float
    capacity_mah: int
    remaining_pct: int


@dataclass
class Attitude:
    pitch_deg: float
    roll_deg: float
    yaw_deg: float


@dataclass
class Gps:
    lat: float
    lon: float
    groundspeed_kmh: float
    heading_deg: float
    altitude_m: int     # INAV: estimated altitude relative to home
    satellites: int


@dataclass
class Vario:
    climb_ms: float


@dataclass
class FlightMode:
    mode: str


@dataclass
class LinkStats:
    uplink_rssi_dbm: int
    uplink_lq: int
    uplink_snr_db: int
    rf_mode: int
    tx_power: int
    downlink_rssi_dbm: int
    downlink_lq: int
    downlink_snr_db: int


Decoded = Union[Battery, Attitude, Gps, Vario, FlightMode, LinkStats]


def _rssi_dbm(raw: int) -> int:
    """RSSI byte -> dBm, accepting both signed (ExpressLRS) and magnitude (spec) forms."""
    return raw - 256 if raw > 127 else -raw


def _rad10000_to_deg(value: int) -> float:
    return math.degrees(value / 10000.0)


def decode(frame_type: int, payload: bytes) -> Optional[Decoded]:
    """Decode a frame payload; returns None for types we don't use or short payloads."""
    try:
        if frame_type == BATTERY and len(payload) >= 8:
            v, i = struct.unpack_from(">HH", payload, 0)
            cap = int.from_bytes(payload[4:7], "big")
            return Battery(v / 10.0, i / 10.0, cap, payload[7])
        if frame_type == ATTITUDE and len(payload) >= 6:
            p, r, y = struct.unpack_from(">hhh", payload, 0)
            return Attitude(_rad10000_to_deg(p), _rad10000_to_deg(r), _rad10000_to_deg(y))
        if frame_type == GPS and len(payload) >= 15:
            lat, lon, gs, hdg, alt, sats = struct.unpack_from(">iiHHHB", payload, 0)
            return Gps(lat / 1e7, lon / 1e7, gs / 10.0, hdg / 100.0, alt - 1000, sats)
        if frame_type == VARIO and len(payload) >= 2:
            (climb,) = struct.unpack_from(">h", payload, 0)
            return Vario(climb / 100.0)
        if frame_type == FLIGHT_MODE:
            return FlightMode(payload.split(b"\x00", 1)[0].decode("ascii", "replace"))
        if frame_type == LINK_STATISTICS and len(payload) >= 10:
            (r1, r2, lq, snr, _ant, mode, pwr, drssi, dlq, dsnr) = struct.unpack_from(">BBBbBBBBBb", payload, 0)
            # The CRSF spec sends RSSI as a positive magnitude (-dBm), but ExpressLRS
            # sends the negative dBm as a signed byte (seen live: 0xE3 = -29 dBm).
            # 0 means that antenna is unused. Report the stronger antenna.
            used = [_rssi_dbm(r) for r in (r1, r2) if r] or [0]
            return LinkStats(max(used), lq, snr, mode, pwr, _rssi_dbm(drssi), dlq, dsnr)
    except struct.error:
        return None
    return None
