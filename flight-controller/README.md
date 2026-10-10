# Redstart flight controller

Custom flight-controller firmware for **Redstart**, a 7" search-and-rescue quadcopter (STM32F411 Black Pill, ISM330DHCX, BMP581, Adafruit Ultimate GPS, ExpressLRS/CRSF, PWM ESCs, 4S).

**Firmware:** INAV 7.1.2 with a custom `REDSTART` board target (`target/REDSTART/`) and an ISM330DHCX patch (`patches/`). The INAV source itself isn't in git: `./fc.sh build` downloads it into `inav/`, applies the patches and links the target in.
**Status:** M0: firmware builds; hardware checks pending. **Not flight-ready.**

| Doc | Contents |
|---|---|
| [docs/bringup.md](docs/bringup.md) | Milestone checklists M0–M5 (build/flash commands included) |
| [docs/hardware.md](docs/hardware.md) | Pin map, power, timers, hardware concerns |
| [docs/stack-evaluation.md](docs/stack-evaluation.md) | Why INAV (vs Betaflight/custom), milestone plan |
| [ground/README.md](ground/README.md) | Ground telemetry bridge: Pocket USB → VehicleTelemetry JSON |
| [docs/architecture.md](docs/architecture.md) | Superseded custom-firmware design (reference) |

```
./fc.sh build    # build -> inav/build/inav_7.1.2_REDSTART.hex
./fc.sh flash    # flash over ST-Link (SWD)
./fc.sh all      # both
```

Settings (PIDs, modes, failsafe, alignment, …) are changed in INAV Configurator, not in code. Keep a copy in `config/redstart-cli.txt` (CLI `diff all`).
Code changes: board pins and defaults go in `target/REDSTART/`. Changes to INAV itself (drivers) are made in `inav/` and then saved as a new file in `patches/` (`diff -u`), because `inav/` is never committed.

Flash over ST-Link, not USB DFU: the ROM bootloader also listens on the GPS and receiver UARTs.

