"""Tests for the CRSF decoder and VehicleTelemetry mapping.

Run:  python3 -m unittest -v      (from the ground/ directory)
Frames are built with the same field layouts INAV 7.1.2 uses in telemetry/crsf.c.
"""

import math
import unittest

import crsf
from telemetry_bridge import TelemetryState


def frame(ftype, payload, address=0xEA):
    return crsf.build_frame(ftype, payload, address)


def battery_payload(volts, amps=0.0, mah=0, pct=0):
    return (int(round(volts * 10)).to_bytes(2, "big") + int(round(amps * 10)).to_bytes(2, "big")
            + mah.to_bytes(3, "big") + bytes([pct]))


def attitude_payload(pitch_deg, roll_deg, yaw_deg):
    return b"".join(int(round(math.radians(a) * 10000)).to_bytes(2, "big", signed=True)
                    for a in (pitch_deg, roll_deg, yaw_deg))


def gps_payload(lat, lon, alt_m, sats, speed_kmh=0.0, heading=0.0):
    return (int(lat * 1e7).to_bytes(4, "big", signed=True) + int(lon * 1e7).to_bytes(4, "big", signed=True)
            + int(speed_kmh * 10).to_bytes(2, "big") + int(heading * 100).to_bytes(2, "big")
            + (alt_m + 1000).to_bytes(2, "big") + bytes([sats]))


class CrcAndFraming(unittest.TestCase):
    def test_crc_known_value(self):
        # CRC-8/DVB-S2 check value for "123456789" is 0xBC
        self.assertEqual(crsf.crc8_dvb_s2(b"123456789"), 0xBC)

    def test_parser_resyncs_after_garbage_and_bad_crc(self):
        good = frame(crsf.FLIGHT_MODE, b"OK\x00")
        bad = bytearray(frame(crsf.FLIGHT_MODE, b"ANGL\x00"))
        bad[-1] ^= 0xFF
        p = crsf.FrameParser()
        out = list(p.feed(b"\x01\x02\xff" + bytes(bad) + good))
        self.assertEqual(out, [(crsf.FLIGHT_MODE, b"OK\x00")])
        self.assertGreaterEqual(p.crc_errors, 1)

    def test_parser_handles_split_reads(self):
        data = frame(crsf.BATTERY, battery_payload(16.8)) * 3
        p = crsf.FrameParser()
        got = []
        for i in range(0, len(data), 5):
            got += list(p.feed(data[i:i + 5]))
        self.assertEqual(len(got), 3)


class Decoding(unittest.TestCase):
    def test_battery(self):
        b = crsf.decode(crsf.BATTERY, battery_payload(15.2, 12.3, 1234, 77))
        self.assertAlmostEqual(b.voltage_v, 15.2)
        self.assertAlmostEqual(b.current_a, 12.3)
        self.assertEqual((b.capacity_mah, b.remaining_pct), (1234, 77))

    def test_attitude_order_is_pitch_roll_yaw(self):
        a = crsf.decode(crsf.ATTITUDE, attitude_payload(-10.0, 20.0, 90.0))
        self.assertAlmostEqual(a.pitch_deg, -10.0, places=1)
        self.assertAlmostEqual(a.roll_deg, 20.0, places=1)
        self.assertAlmostEqual(a.yaw_deg, 90.0, places=1)

    def test_gps(self):
        g = crsf.decode(crsf.GPS, gps_payload(28.6024, -81.2001, 35, 11))
        self.assertAlmostEqual(g.lat, 28.6024, places=5)
        self.assertAlmostEqual(g.lon, -81.2001, places=5)
        self.assertEqual((g.altitude_m, g.satellites), (35, 11))

    def test_link_stats_uses_stronger_antenna(self):
        ls = crsf.decode(crsf.LINK_STATISTICS, bytes([70, 80, 99, 9, 0, 7, 3, 60, 100, 8]))
        self.assertEqual(ls.uplink_rssi_dbm, -70)
        self.assertEqual(ls.uplink_lq, 99)

    def test_link_stats_from_live_elrs_capture(self):
        # Captured from the RP1/Pocket on 2026-10-10: ExpressLRS sends signed dBm.
        raw = bytes.fromhex("ea 0c 14 e3 00 64 0c 00 07 03 e9 64 0c ec")
        (ftype, payload), = list(crsf.FrameParser().feed(raw))
        ls = crsf.decode(ftype, payload)
        self.assertEqual((ls.uplink_rssi_dbm, ls.uplink_lq, ls.downlink_rssi_dbm), (-29, 100, -23))


class VehicleTelemetryMapping(unittest.TestCase):
    def feed(self, state, data, now):
        p = crsf.FrameParser()
        for ftype, payload in p.feed(data):
            d = crsf.decode(ftype, payload)
            if d is not None:
                state.update(d, now)

    def test_nothing_received_means_all_unavailable(self):
        s = TelemetryState().snapshot(0.0)
        self.assertEqual(s["link_state"], "no_data")
        for key in ("armed", "battery_v", "roll_deg", "pitch_deg", "yaw_deg", "altitude_m", "lat", "lon", "fix_valid"):
            self.assertIsNone(s[key], key)

    def test_armed_from_inav_flight_mode_strings(self):
        for mode, armed in (("OK", False), ("!ERR", False), ("WAIT", False),
                            ("ANGL", True), ("ACRO", True), ("!FS!", True), ("HOLD", True)):
            st = TelemetryState()
            self.feed(st, frame(crsf.FLIGHT_MODE, mode.encode() + b"\x00"), 1.0)
            self.assertIs(st.snapshot(1.0)["armed"], armed, mode)

    def test_yaw_unavailable_without_flag(self):
        st = TelemetryState()
        self.feed(st, frame(crsf.ATTITUDE, attitude_payload(1, 2, 45)), 1.0)
        snap = st.snapshot(1.0)
        self.assertIsNone(snap["yaw_deg"])
        self.assertAlmostEqual(snap["roll_deg"], 2.0, places=1)

        st = TelemetryState(relative_yaw=True)
        self.feed(st, frame(crsf.ATTITUDE, attitude_payload(1, 2, 45)), 1.0)
        snap = st.snapshot(1.0)
        self.assertAlmostEqual(snap["yaw_deg"], 45.0, places=1)
        self.assertEqual(snap["yaw_reference"], "relative")

    def test_no_gps_position_without_fix(self):
        st = TelemetryState()
        self.feed(st, frame(crsf.GPS, gps_payload(28.6, -81.2, 10, 3)), 1.0)
        snap = st.snapshot(1.0)
        self.assertFalse(snap["fix_valid"])
        self.assertIsNone(snap["lat"])
        self.assertIsNone(snap["lon"])

    def test_link_lost_after_timeout(self):
        st = TelemetryState()
        self.feed(st, frame(crsf.BATTERY, battery_payload(16.0)), 10.0)
        self.assertEqual(st.snapshot(10.5)["link_state"], "connected")
        self.assertEqual(st.snapshot(11.6)["link_state"], "lost")

    def test_link_stats_alone_do_not_count_as_drone_data(self):
        # The TX module emits link stats even when the drone is off.
        st = TelemetryState()
        self.feed(st, frame(crsf.LINK_STATISTICS, bytes([0, 0, 0, 0, 0, 7, 3, 0, 0, 0])), 1.0)
        self.assertEqual(st.snapshot(1.0)["link_state"], "no_data")


if __name__ == "__main__":
    unittest.main()
