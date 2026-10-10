# Bring-up and validation (INAV 7.1.2, REDSTART target)

Each milestone is a separate gate: **don't start the next one until this one passes on hardware.** Firmware compiling proves nothing about flight readiness.

Rules: **props off for M0 and M1.** Use a smoke stopper (or a current-limited supply) the first time the ESCs see the battery. Props off whenever USB is connected.

---

## M0: Build, flash, connect ✅ firmware builds

```
./fc.sh build    # -> inav/build/inav_7.1.2_REDSTART.hex
./fc.sh flash    # ST-Link (SWD)
```

Open **INAV Configurator 7.1.x** and connect to the Black Pill's USB port (on Arch, your user needs to be in the `uucp` group).

- [ ] Configurator connects and shows target `REDSTART`, version 7.1.2.
- [ ] Setup tab: the gyro and accelerometer icons are active. CLI `status` lists `LSM6DXX` as the gyro/acc.
- [ ] Tilt the board: the 3D model follows. Nose down → model nose down; right side down → model rolls right; turning clockwise seen from above → model yaws clockwise. If not, set `align_board_roll/pitch/yaw` in the CLI and save.
- [ ] Calibrate the accelerometer (six positions) on a level surface.
- [ ] Beeper: you should hear the startup tones at power-up; in M1, toggle the BEEPER mode switch. If it's silent, check PB9 with a scope (it should show ~4.1 kHz while beeping).
- [ ] Battery (with the battery connected, props off): CLI `status` voltage within 0.1 V of a multimeter. Adjust `vbat_scale` (default 555) if needed.

## M1: Radio, motors, failsafe (bench, PROPS OFF)

- [ ] Pocket (EdgeTX, internal ELRS) bound to the RP1. The receiver tab shows CRSF on UART2, channel map AETR. Every stick and switch moves the correct channel in the correct direction.
- [ ] Modes tab: SA = ARM, SB = ANGLE (other positions unlock in M3/M4), SC = BEEPER.
- [ ] Configuration: mixer **Quad X**, ESC protocol **STANDARD** (the ESCs don't accept DShot). Try **ONESHOT125** later; keep it only if all four arm reliably.
- [ ] ESCs play their arming tone after the board boots, and no motor twitches at zero throttle.
- [ ] Motors tab, one motor at a time (smoke stopper on). Record the position and direction:

| Output | Header | Expected position | Expected spin | Observed |
|---|---|---|---|---|
| M1 | J2 (PB1) | rear right | CW | |
| M2 | J3 (PB0) | front right | CCW | |
| M3 | J4 (PB4) | rear left | CCW | |
| M4 | J5 (PB5) | front left | CW | |

  Fix wrong positions by moving ESC signal leads between headers. Fix a wrong direction by swapping any two of that motor's three wires (PWM ESCs have no software reverse).
- [ ] Arming is refused when: the arm switch is already on at boot, throttle isn't low, the board is tilted, or sensors aren't calibrated.
- [ ] Failsafe: armed with props off, switch the Pocket off → failsafe engages within about 1 s and the motors do what the configured procedure says (`LAND`, or `DROP` for the first hops).
- [ ] Save the settings: CLI `diff all` → `config/redstart-cli.txt`.

## M2: First flights, angle mode (MUST-HAVE)

**Before props go on**
- [ ] Battery voltage reads correctly in INAV (low-voltage warnings depend on it). If the pack can't feed the board's XT60, use a flight timer and check the pack voltage after every flight.
- [ ] **Armed tilt test, props OFF, battery on:** arm (angle mode), raise throttle to about 20%, then tilt the drone by hand. The motors on the side tipped *down* must speed up. Check all four directions (nose down → front motors up, right side down → right motors up). If any direction is reversed, disarm and do not fly: board alignment or motor order is wrong.
- [ ] Arm switch disarms instantly at any throttle.
- [ ] Switching the Pocket off while armed → motors stop (failsafe DROP) within about 1 s.

**Props on**
- [ ] Props match motor direction (CW props on CW motors; the leading edge leads in the spin direction) and are tight.
- [ ] Open area, no people within 15 m, you behind the drone, line of sight.

**First hover**
- [ ] Arm, raise throttle slowly until the drone is light on its legs. If it tips or slides hard to one side, **disarm immediately** and check props and motor order.
- [ ] Lift to about 1 m: hold for a few seconds, land. Listen for oscillation (buzzing or wobble); feel the motors after landing (warm is OK, hot is not).
- [ ] Then short hops: holds level when sticks are released, responds smoothly. Tune P/D, then I (Ez Tune in Configurator, 7" frame).

## M3: Altitude hold (BMP581 driver port)

- [ ] Baro detected; altitude rises when the board is lifted.
- [ ] In flight, ANGLE+ALTHOLD with centre throttle holds height within about 1 m.

## M4: GPS position hold (NMEA driver port)

- [ ] GPS fix with ≥ 8 satellites at the field.
- [ ] Fly straight to get a GPS heading, then POSHOLD: letting go holds within a few metres.
- [ ] RTH by switch works before it's enabled as the failsafe procedure.

## M5: Waypoints (stretch)

- [ ] A short mission planned in Configurator flies correctly, with the pilot ready to switch back to POSHOLD/ANGLE.
