"""Upload and read back an INAV waypoint mission over a dedicated MSP link.

USB serial (pyserial) or a transparent TCP-to-MSP bridge; never the CRSF mirror.
Receives validated mission JSON on stdin. Does not arm, start, or override RC.
"""
import argparse
import json
import math
import socket
import struct
import sys
import time


def crc8(data):
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc << 1) ^ (0xD5 if crc & 0x80 else 0)) & 255
    return crc


def encode(command, payload=b"", direction=b"<"):
    body = struct.pack("<BHH", 0, command, len(payload)) + payload
    return b"$X" + direction + body + bytes([crc8(body)])


class Msp:
    def __init__(self, connection):
        self.connection = connection

    def read(self, count, deadline):
        result = bytearray()
        while len(result) < count:
            if time.monotonic() >= deadline:
                raise TimeoutError("INAV did not acknowledge the mission; upload is unverified")
            chunk = self.connection.read(count - len(result))
            if chunk:
                result.extend(chunk)
        return bytes(result)

    def request(self, command, payload=b""):
        self.connection.write(encode(command, payload))
        deadline = time.monotonic() + 2
        prefix = b""
        while time.monotonic() < deadline:
            prefix = (prefix + self.read(1, deadline))[-3:]
            if prefix not in (b"$X>", b"$X!"):
                continue
            header = self.read(5, deadline)
            _, returned, length = struct.unpack("<BHH", header)
            if length > 4096:
                raise ValueError("Invalid MSP response length")
            body = self.read(length, deadline)
            check = self.read(1, deadline)[0]
            if crc8(header + body) != check:
                raise ValueError("MSP response checksum mismatch")
            if returned != command:
                prefix = b""
                continue
            if prefix == b"$X!":
                raise ValueError(f"INAV rejected MSP command {command}")
            return body
        raise TimeoutError("INAV response timed out")


def validate(mission):
    if not isinstance(mission, dict) or mission.get("finish") != "hold" or mission.get("altitudeReference") not in ("home", "amsl"):
        raise ValueError("Invalid mission settings")
    points = mission.get("waypoints")
    if not isinstance(points, list) or not 2 <= len(points) <= 60:
        raise ValueError("A mission requires 2–60 waypoints")
    for p in points:
        if not isinstance(p, dict):
            raise ValueError("Invalid waypoint")
        for key in ("latitude", "longitude", "altitudeM", "speedMs"):
            if isinstance(p.get(key), bool) or not isinstance(p.get(key), (int, float)) or not math.isfinite(p[key]):
                raise ValueError("Nonfinite waypoint")
        if not (abs(p["latitude"]) < 85 and abs(p["longitude"]) <= 180 and (1 if mission["altitudeReference"] == "home" else -500) <= p["altitudeM"] <= 10000 and 0.1 <= p["speedMs"] <= 20):
            raise ValueError("Waypoint outside supported bounds")
    return points


def waypoint_payload(point, number, last, absolute):
    return struct.pack("<BBiiihhhB", number, 1, round(point["latitude"] * 1e7), round(point["longitude"] * 1e7), round(point["altitudeM"] * 100), round(point["speedMs"] * 100), 0, int(absolute), 0xA5 if last else 0)


def disarmed(msp, arm_index):
    status = msp.request(101)
    if len(status) < 10 or arm_index >= 32:
        raise ValueError("Could not verify disarmed state")
    if struct.unpack_from("<I", status, 6)[0] & (1 << arm_index):
        raise ValueError("Disarm before uploading; use transmitter mode switch for pilot control")


def upload(msp, mission):
    points = validate(mission)
    if msp.request(2) != b"INAV":
        raise ValueError("The connected flight controller is not INAV")
    boxes = msp.request(119)
    if 0 not in boxes:
        raise ValueError("ARM status is unavailable; refusing upload")
    arm_index = boxes.index(0)
    disarmed(msp, arm_index)
    info = msp.request(20)
    if len(info) < 4 or len(points) > info[1]:
        raise ValueError("Mission exceeds controller waypoint capacity")
    payloads = [waypoint_payload(p, i + 1, i == len(points) - 1, mission["altitudeReference"] == "amsl") for i, p in enumerate(points)]
    for payload in payloads:
        disarmed(msp, arm_index)
        msp.request(209, payload)
    for payload in payloads:
        received = msp.request(118, payload[:1])
        if received != payload:
            raise ValueError(f"Waypoint {payload[0]} read-back mismatch; do not start mission")
    info = msp.request(20)
    if len(info) < 4 or not info[2] or info[3] != len(points):
        raise ValueError("INAV reports an invalid/incomplete mission; do not start it")
    return {"verified": True, "waypoints": len(points), "finish": "hold", "started": False}


class TcpConnection:
    def __init__(self, host, port):
        self.socket = socket.create_connection((host, port), timeout=2)
        self.socket.settimeout(0.1)
    def read(self, count):
        try:
            data = self.socket.recv(count)
            if not data:
                raise ConnectionError("MSP bridge disconnected")
            return data
        except socket.timeout:
            return b""
    def write(self, data):
        self.socket.sendall(data)
    def close(self):
        self.socket.close()


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--serial")
    group.add_argument("--tcp-host")
    parser.add_argument("--tcp-port", type=int)
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()
    connection = None
    try:
        mission = json.load(sys.stdin)
        validate(mission)
        if args.serial:
            import serial
            connection = serial.Serial(args.serial, args.baud, timeout=0.1, write_timeout=2)
            connection.reset_input_buffer()
        else:
            if args.tcp_port is None or not 1 <= args.tcp_port <= 65535:
                raise ValueError("A valid TCP port is required")
            connection = TcpConnection(args.tcp_host, args.tcp_port)
        print(json.dumps(upload(Msp(connection), mission)))
    except Exception as error:
        print(json.dumps({"verified": False, "error": str(error)}))
        return 1
    finally:
        if connection:
            connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
