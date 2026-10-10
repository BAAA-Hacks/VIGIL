# Shape missions

The map's right toolbar offers circle, square, triangle, and line in that order. Drag an icon onto the map, or click it to place a shape at the map center. Select a shape and drag its center handle to move it or its corner handle to resize it. The Size input is an alternative to resizing by mouse. Size means circle radius, square half-side, triangle circumradius, or line half-length, in metres.

Shapes generate 10, 4, 3, and 2 distinct waypoints respectively. Shapes are visited in insertion order and points are numbered in flight order. These are perimeter/line routes, not area-covering lawnmower searches. There is no duplicate closing waypoint: the route stops at its final numbered point. A final INAV WAYPOINT with the last flag causes indefinite position hold on a multirotor. It does not land or return home. GPS/navigation readiness and INAV failsafe behaviour remain flight-controller responsibilities.

Editing prepares a draft. **Send to INAV** replaces the controller's mission only when explicitly clicked; editing does not transmit live steering commands. Upload checks INAV identity, disarmed status, waypoint capacity, acknowledgments, every point's read-back, and final mission validity/count. It does not arm, enable NAV WP, save to nonvolatile memory, or start flight. A failed upload may leave a partial mission in RAM: do not activate NAV WP until a fresh upload has been verified.

## Connection configuration

The existing RadioMaster/ELRS CRSF telemetry mirror is receive-only and is not the mission upload transport. Set one of the following in `ground-station/.env.local` and restart Next.js:

```dotenv
# Direct USB/UART MSP serial connection to INAV; replace with the actual device.
INAV_MSP_SERIAL_PORT=COM5
INAV_MSP_BAUD=115200
```

or:

```dotenv
# A transparent TCP-to-MSP bridge connected to an INAV MSP-enabled port.
# Replace with the actual bridge address and port.
INAV_MSP_TCP_HOST=192.168.1.20
INAV_MSP_TCP_PORT=5760
```

USB serial requires `pyserial` in the Python environment used by the app. TCP uses the Python standard library. `PYTHON_EXECUTABLE` optionally selects that Python runtime. Do not point the uploader at the transmitter's CRSF mirror or a thermal video endpoint. Close INAV Configurator before using the same serial port. Only one process may own it.

Without a configured connection, the app disables Send and still allows XML export for INAV Configurator Mission Control. Configured does not mean connected: success is shown only after read-back verification. The connection's actual device/address has not been supplied or hardware-tested in this task.

## Pilot takeover

For a multirotor, configure a transmitter switch so one position activates NAV WP and another leaves all autonomous navigation modes and restores the intended pilot-controlled mode, such as ANGLE. Confirm its channel/range mapping in INAV and test the transition before enabling missions. This needs to work independently of the laptop and upload link. The app requires acknowledgment that this transmitter switch has been tested before allowing upload; the checkbox cannot configure or verify the actual radio.

The uploader does not send MSP RC override, modify mode ranges, or disable the pilot's RC link. There is no dashboard takeover button claiming to switch flight modes: the receive-only ELRS bridge cannot implement one. Actual takeover has not been verified on hardware, and the required switch/channel is still pending user input.

## Altitude

Altitude is entered explicitly per mission and applies to all points. The default reference is **above home**; AMSL is an option using INAV's absolute-altitude bit. Neither is height above local terrain. No automatic terrain-following or obstacle avoidance is provided. The 10 m default is a relative-altitude planning value, not a terrain clearance guarantee. All coordinates are WGS84. MSP encodes degrees × 10^7, altitude in centimetres, and speed in centimetres/second. XML uses integer metres and may round fractional altitudes.

## Sources

- [INAV MSP navigation messages](https://inavflight.github.io/docs/advanced-features/msp-navigation-messages/): waypoint fields, units, final waypoint hold, read-back, MSPv2 encoding.
- [INAV 7.1.2 flight-controller MSP implementation](https://github.com/iNavFlight/inav/blob/7.1.2/src/main/fc/fc_msp.c): status, waypoint capacity and mission validity responses.

Tests exercise shape geometry and an emulated MSP controller, including fragmented responses, armed-state rejection, checksum errors, capacity limits, and failed read-back. They do not prove flight behaviour or transmitter takeover on the aircraft.
