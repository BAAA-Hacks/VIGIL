"""Tests for the CRSF decoder and VehicleTelemetry mapping.

Run:  python3 -m unittest -v      (from the ground/ directory)
Frames are built with the same field layouts INAV 7.1.2 uses in telemetry/crsf.c.
"""

import math
import unittest

import crsf
import json
import socket
import time
import urllib.request
from unittest import mock

import telemetry_bridge
from telemetry_bridge import SyntheticSource, TelemetryState


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


def ext(ftype, payload):
    """Extended frame from the flight controller to the radio (dest 0xEA, origin 0xC8)."""
    return frame(ftype, bytes([0xEA, 0xC8]) + payload)


def i16(*values):
    return b"".join(int(v).to_bytes(2, "big", signed=True) for v in values)


def sensors(accel=(0, 0, 1000), gyro=(0, 0, 0), mag=(0, 0, 0), heading=0, flags=0):
    """Redstart sensors frame 0x88 (patch 0010)."""
    return ext(crsf.REDSTART_SENSORS, i16(*accel, *gyro, *mag) + int(heading).to_bytes(2, "big") + bytes([flags]))


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
    def test_inav_nose_down_pitch_is_published_as_negative(self):
        st = TelemetryState()
        st.update(crsf.decode(crsf.ATTITUDE, attitude_payload(10.0, 5.0, 0.0)), 1.0)  # INAV: 10 deg nose down
        snap = st.snapshot(1.0)
        self.assertAlmostEqual(snap["pitch_deg"], -10.0, places=1)
        self.assertAlmostEqual(snap["roll_deg"], 5.0, places=1)

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

    def test_baro_altitude_packing(self):
        b = crsf.decode(crsf.BARO_ALTITUDE, (10000 + 123).to_bytes(2, "big") + bytes([40]))
        self.assertAlmostEqual(b.altitude_m, 12.3)
        self.assertAlmostEqual(b.climb_ms, math.exp(40 * 0.026) - 1, places=3)   # firmware: ln(1+v/100)/0.026
        self.assertAlmostEqual(crsf.decode(crsf.BARO_ALTITUDE, (10000 - 25).to_bytes(2, "big") + b"\xd8").altitude_m, -2.5)
        self.assertLess(crsf.decode(crsf.BARO_ALTITUDE, (10000).to_bytes(2, "big") + b"\xd8").climb_ms, 0)
        self.assertEqual(crsf.decode(crsf.BARO_ALTITUDE, (0x8000 | 3000).to_bytes(2, "big") + b"\x00").altitude_m, 3000)

    def test_sensors_frame_skips_extended_addresses(self):
        parser = crsf.FrameParser()
        data = sensors((10, -20, 1000), (15, -30, 0), (100, -200, 300), 1234, flags=0b11)
        [s] = [crsf.decode(t, p) for t, p in parser.feed(data)]
        self.assertEqual(s.imu.accel_g, (0.01, -0.02, 1.0))
        self.assertEqual(s.imu.gyro_dps, (1.5, -3.0, 0.0))
        self.assertEqual(s.mag.field_counts, (100, -200, 300))
        self.assertAlmostEqual(s.mag.heading_deg, 123.4)
        self.assertTrue(s.mag.healthy)
        self.assertTrue(s.mag.calibrated)

    def test_sensors_frame_without_magnetometer(self):
        s = crsf.decode(*next(crsf.FrameParser().feed(sensors())))
        self.assertIsNone(s.mag)
        self.assertEqual(s.imu.accel_g, (0.0, 0.0, 1.0))

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

    def test_magnetic_heading_replaces_relative_yaw(self):
        mag = lambda flags: sensors(mag=(1, 2, 3), heading=2705, flags=flags)
        st = TelemetryState(relative_yaw=True)
        self.feed(st, frame(crsf.ATTITUDE, attitude_payload(0, 0, 45)) + mag(0b11), 1.0)
        snap = st.snapshot(1.0)
        self.assertAlmostEqual(snap["yaw_deg"], 270.5)
        self.assertEqual(snap["yaw_reference"], "magnetic")
        self.assertEqual(snap["mag"], {"field_counts": [1, 2, 3], "heading_deg": 270.5,
                                       "healthy": True, "calibrated": True})

        for flags in (0b01, 0b10, 0b00):   # healthy but uncalibrated, or not healthy -> relative yaw
            st = TelemetryState(relative_yaw=True)
            self.feed(st, frame(crsf.ATTITUDE, attitude_payload(0, 0, 45)) + mag(flags), 1.0)
            snap = st.snapshot(1.0)
            self.assertEqual(snap["yaw_reference"], "relative", flags)
            self.assertAlmostEqual(snap["yaw_deg"], 45.0, places=1)

    def test_altitude_above_home_and_sea_level_extra(self):
        baro = lambda dm: frame(crsf.BARO_ALTITUDE, (10000 + dm).to_bytes(2, "big") + b"\x00")
        st = TelemetryState()
        self.feed(st, frame(crsf.GPS, gps_payload(28.6, -81.2, 40, 3)), 1.0)
        self.assertIsNone(st.snapshot(1.0)["altitude_msl_m"])           # no fix: no sea-level source
        self.feed(st, frame(crsf.GPS, gps_payload(28.6, -81.2, 40, 10)), 1.0)
        self.assertEqual(st.snapshot(1.0)["altitude_msl_m"], 40)        # GPS only (no barometer)
        self.assertIsNone(st.snapshot(1.0)["altitude_m"])               # height above home needs the barometer

        st = TelemetryState()
        self.feed(st, baro(15), 1.0)
        snap = st.snapshot(1.0)
        self.assertEqual(snap["altitude_m"], 1.5)                       # above home
        self.assertIsNone(snap["altitude_msl_m"])
        self.feed(st, frame(crsf.GPS, gps_payload(28.6, -81.2, 40, 10)), 2.0)
        self.assertEqual(st.snapshot(2.0)["altitude_msl_m"], 40.0)      # offset learned: 40 - 1.5
        self.feed(st, baro(25), 2.5)
        self.assertEqual(st.snapshot(2.5)["altitude_m"], 2.5)
        self.assertEqual(st.snapshot(2.5)["altitude_msl_m"], 41.0)      # follows the barometer
        self.feed(st, frame(crsf.GPS, gps_payload(28.6, -81.2, 45, 10)), 3.0)
        self.assertLess(st.snapshot(3.0)["altitude_msl_m"], 41.5)       # a GPS jump only nudges it
        self.feed(st, frame(crsf.GPS, gps_payload(0, 0, 0, 0)), 4.0)
        self.assertIsNotNone(st.snapshot(4.0)["altitude_msl_m"])        # fix lost: keeps the learned offset

    def test_imu_extra(self):
        st = TelemetryState()
        self.assertIsNone(st.snapshot(1.0)["imu"])
        self.feed(st, sensors(gyro=(0, 0, 25)), 1.0)
        self.assertEqual(st.snapshot(1.0)["imu"], {"accel_g": [0.0, 0.0, 1.0], "gyro_dps": [0.0, 0.0, 2.5]})

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


    def test_floating_battery_input_is_unavailable(self):
        # No pack on the XT60: the divider input floats at a few tens of mV.
        st = TelemetryState()
        self.feed(st, frame(crsf.BATTERY, battery_payload(0.03)), 1.0)
        snap = st.snapshot(1.0)
        self.assertIsNone(snap["battery_v"])
        self.assertIsNone(snap["battery_pct"])

    def test_home_distance_and_armed_time(self):
        st = TelemetryState()
        self.feed(st, frame(crsf.FLIGHT_MODE, b"OK\x00") + frame(crsf.GPS, gps_payload(28.6, -81.2, 0, 10)), 1.0)
        self.assertIsNone(st.snapshot(1.0)["home"])  # home is set at arming, like INAV
        self.feed(st, frame(crsf.FLIGHT_MODE, b"ANGL\x00"), 2.0)
        self.feed(st, frame(crsf.GPS, gps_payload(28.6 + 100 / 111320, -81.2, 10, 10, 18.0, 90.0)), 5.0)
        snap = st.snapshot(5.0)
        self.assertEqual(snap["home"], {"lat": 28.6, "lon": -81.2})
        self.assertAlmostEqual(snap["distance_home_m"], 100.0, delta=1.0)
        self.assertEqual((snap["speed_ms"], snap["course_deg"], snap["armed_time_s"]), (5.0, 90.0, 3.0))
        self.feed(st, frame(crsf.FLIGHT_MODE, b"OK\x00"), 6.0)
        self.assertIsNone(st.snapshot(6.0)["armed_time_s"])


class Synthetic(unittest.TestCase):
    def run_mission(self):
        """Step a SyntheticSource through one full cycle without sleeping."""
        src = SyntheticSource()
        st = TelemetryState(relative_yaw=True, source="synthetic")
        parser = crsf.FrameParser()
        snaps = []
        with mock.patch.object(telemetry_bridge.time, "sleep"), \
             mock.patch.object(telemetry_bridge.time, "monotonic") as clock:
            for i in range(int(src.cycle * 10)):
                now = src.t0 + i / 10
                clock.return_value = now
                for ftype, payload in parser.feed(src.read(256)):
                    st.update(crsf.decode(ftype, payload), now)
                snaps.append(st.snapshot(now))
        return snaps

    def test_synthetic_attitude_is_small_and_changes_gradually(self):
        snaps = self.run_mission()
        self.assertLessEqual(max(abs(s["roll_deg"]) for s in snaps), 0.5)
        self.assertLessEqual(max(abs(s["pitch_deg"]) for s in snaps), 3.4)
        for a, b in zip(snaps, snaps[1:]):
            self.assertLessEqual(abs(a["roll_deg"] - b["roll_deg"]), 0.21)
            self.assertLessEqual(abs(a["pitch_deg"] - b["pitch_deg"]), 0.21)
        self.assertTrue(all(38 <= s["pcb_temp_c"] <= 43 for s in snaps))
        self.assertIsNone(TelemetryState(source="pocket").snapshot(1.0)["pcb_temp_c"])

    def test_mission_exercises_every_field(self):
        snaps = self.run_mission()
        for key in ("armed", "battery_v", "roll_deg", "pitch_deg", "yaw_deg", "altitude_m", "lat", "lon",
                    "fix_valid", "battery_pct", "climb_ms", "speed_ms", "course_deg", "satellites",
                    "home", "distance_home_m", "armed_time_s", "link", "imu", "mag"):
            self.assertTrue(any(s[key] not in (None, 0, False) for s in snaps), key)
        self.assertEqual({s["link_state"] for s in snaps}, {"connected", "degraded", "lost"})
        modes = [s["flight_mode"] for s in snaps]
        self.assertEqual([m for i, m in enumerate(modes) if m and m != modes[i - 1]],
                         ["WAIT", "OK", "ANGL", "AH", "HOLD", "WP", "RTH", "OK"])
        self.assertTrue(any(s["fix_valid"] is False for s in snaps))   # waiting for satellites
        self.assertEqual(max(s["altitude_m"] or 0 for s in snaps), 10)                                  # above home
        self.assertEqual(max(s["altitude_msl_m"] or 0 for s in snaps), 10 + SyntheticSource.HOME_MSL_M)  # sea level
        self.assertGreater(max(s["distance_home_m"] or 0 for s in snaps), 50)  # far corner falls in the dropout
        self.assertTrue(all(s["source"] == "synthetic" for s in snaps))


class ServerSentEvents(unittest.TestCase):
    def test_stream_and_latest(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        hub = telemetry_bridge.start_http("127.0.0.1", port)
        hub.publish(json.dumps({"n": 1}))
        base = f"http://127.0.0.1:{port}"

        with urllib.request.urlopen(base + "/latest", timeout=2) as r:
            self.assertEqual(r.headers["Access-Control-Allow-Origin"], "*")
            self.assertEqual(json.loads(r.read()), {"n": 1})

        with urllib.request.urlopen(base + "/telemetry", timeout=2) as r:
            self.assertTrue(r.headers["Content-Type"].startswith("text/event-stream"))
            self.assertEqual(r.headers["Access-Control-Allow-Origin"], "*")
            self.assertEqual(r.readline(), b"retry: 1000\n")
            r.readline()
            self.assertEqual(r.readline(), b'data: {"n": 1}\n')  # latest value on connect
            r.readline()
            time.sleep(0.05)
            hub.publish(json.dumps({"n": 2}))
            self.assertEqual(r.readline(), b'data: {"n": 2}\n')  # then each new one


class TrackReplay(unittest.TestCase):
    def test_track_frames_decode_to_the_keyframe_and_follow_the_camera(self):
        import tempfile
        keyframe = {"frame": 7, "lat": 28.60039, "lon": -81.198814, "alt_m": 1.2, "heading_deg": 45.0,
                    "pitch_deg": -3.0, "roll_deg": 1.0, "speed_ms": 0.35, "course_deg": 45.0,
                    "armed": True, "mode": "ANGL"}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"keyframes": [keyframe, dict(keyframe, frame=8, lat=28.6005)]}, handle)
        source = telemetry_bridge.TrackSource(handle.name, "http://unused")
        state = TelemetryState(source="replay-track", north_yaw=True)
        parser = crsf.FrameParser()
        with mock.patch.object(telemetry_bridge.time, "sleep"), \
             mock.patch.object(source, "current_frame", return_value=7):
            for ftype, payload in parser.feed(source.read(256)):
                state.update(crsf.decode(ftype, payload), 1.0)
        snap = state.snapshot(1.0)
        self.assertAlmostEqual(snap["lat"], 28.60039, places=5)
        self.assertAlmostEqual(snap["pitch_deg"], -3.0, places=1)  # nose-up contract survives the wire
        self.assertAlmostEqual(snap["yaw_deg"], 45.0, places=1)
        self.assertEqual(snap["yaw_reference"], "north")
        self.assertEqual(snap["altitude_m"], 1.2)      # height above home, from the baro-altitude frame (0.1 m)
        self.assertIsNone(snap["altitude_msl_m"])      # the track has no sea-level altitude
        self.assertTrue(snap["armed"])
        self.assertIsNone(snap["battery_v"])
        with mock.patch.object(telemetry_bridge.time, "sleep"), \
             mock.patch.object(source, "current_frame", return_value=None):
            self.assertEqual(source.read(256), b"")  # no replay running: no telemetry

if __name__ == "__main__":
    unittest.main()
