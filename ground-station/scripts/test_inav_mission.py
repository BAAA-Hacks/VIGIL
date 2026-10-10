import struct
import unittest
from inav_mission import Msp, crc8, encode, upload, waypoint_payload

MISSION = {"altitudeReference": "home", "finish": "hold", "waypoints": [
    {"latitude": 34.05, "longitude": -118.24, "altitudeM": 10, "speedMs": 2},
    {"latitude": 34.051, "longitude": -118.241, "altitudeM": 10, "speedMs": 2},
]}


class Controller:
    def __init__(self, armed=False, mismatch=False, capacity=60):
        self.armed, self.mismatch, self.capacity = armed, mismatch, capacity
        self.points = {}
        self.buffer = bytearray()
        self.commands = []
    def write(self, packet):
        self.assert_packet(packet)
        command = struct.unpack_from("<H", packet, 4)[0]
        payload = packet[8:-1]
        self.commands.append(command)
        if command == 2: result = b"INAV"
        elif command == 119: result = bytes([1, 0, 28])  # ARM is bit 1, not a hardcoded bit 0.
        elif command == 101: result = bytes(6) + struct.pack("<I", 2 if self.armed else 0)
        elif command == 20: result = bytes([0, self.capacity, bool(self.points), len(self.points)])
        elif command == 209:
            self.points[payload[0]] = payload
            result = b""
        elif command == 118:
            result = self.points[payload[0]]
            if self.mismatch: result = result[:-1] + b"\x00"
        else: raise AssertionError(f"Unexpected command: {command}")
        self.buffer.extend(encode(command, result, b">"))
    def read(self, count):
        # Fragment every response to exercise streaming parsing.
        result = bytes(self.buffer[:min(count, 2)])
        del self.buffer[:len(result)]
        return result
    @staticmethod
    def assert_packet(packet):
        assert packet[:3] == b"$X<"
        assert crc8(packet[3:-1]) == packet[-1]


class Tests(unittest.TestCase):
    def test_upload_verifies_every_point_and_final_hold(self):
        controller = Controller()
        result = upload(Msp(controller), MISSION)
        self.assertTrue(result["verified"])
        self.assertFalse(result["started"])
        self.assertEqual(controller.commands.count(209), 2)
        self.assertEqual(controller.commands.count(118), 2)
        last = struct.unpack("<BBiiihhhB", controller.points[2])
        self.assertEqual(last[1], 1)  # WAYPOINT, never LAND or RTH
        self.assertEqual(last[-1], 0xA5)
        self.assertEqual(last[4], 1000)  # cm
        self.assertEqual(last[5], 200)  # cm/s
        self.assertEqual(controller.points[1][-1], 0)
    def test_armed_controller_receives_no_waypoint_writes(self):
        controller = Controller(armed=True)
        with self.assertRaisesRegex(ValueError, "Disarm"):
            upload(Msp(controller), MISSION)
        self.assertNotIn(209, controller.commands)
    def test_capacity_checked_before_writes(self):
        controller = Controller(capacity=1)
        with self.assertRaisesRegex(ValueError, "capacity"):
            upload(Msp(controller), MISSION)
        self.assertNotIn(209, controller.commands)
    def test_mismatched_readback_never_reports_success(self):
        with self.assertRaisesRegex(ValueError, "mismatch"):
            upload(Msp(Controller(mismatch=True)), MISSION)
    def test_absolute_altitude_flag_and_signed_coordinates(self):
        payload = waypoint_payload(MISSION["waypoints"][0], 1, True, True)
        fields = struct.unpack("<BBiiihhhB", payload)
        self.assertEqual(fields[3], -1182400000)
        self.assertEqual(fields[7], 1)
    def test_corrupt_response_is_rejected(self):
        class Corrupt(Controller):
            def write(self, packet):
                super().write(packet)
                self.buffer[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum"):
            Msp(Corrupt()).request(2)


if __name__ == "__main__":
    unittest.main()
