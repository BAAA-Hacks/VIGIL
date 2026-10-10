# Redstart hardware map

Source: `/home/adkat/Projects/redstart/redstart.kicad_sch` + `redstart.kicad_pcb` (repo commit `5218f28`, KiCad 10.0.7). I exported the netlist with `kicad-cli sch export netlist`, read the PCB pad nets from `.kicad_pcb`, and ran ERC and DRC with schematic parity.

> **These repo KiCad files are older than the fabricated board.** The owner reports that the built PCB is fully connected. Re-check this map against the latest design files before relying on it. The firmware's single source of truth for pins is the INAV target, `target/REDSTART/target.h` and `target.c`.

## Components found

| Ref | Part | Notes |
|---|---|---|
| U1 | WeAct Black Pill V3.1, STM32F411CEU6 | 25 MHz HSE → 96 MHz SYSCLK (STM32duino variant), USB-C, SWD header |
| U4 | Adafruit ISM330DHCX breakout | SPI1 (as wired on the PCB) |
| U3 | Adafruit BMP581 breakout | I2C1 |
| U2 | Adafruit Ultimate GPS (MTK3339) | USART1 + PPS |
| J6 | JST-PH 4-pin | ELRS receiver (RadioMaster RP1 V2), CRSF on USART2 |
| J2–J5 | 1x3 2.54 mm headers | ESC signal: GND / NC / signal |
| J1 | XT60 | Battery in |
| U5 | MP1584EN buck module | +BATT → +5V |
| R1/R2/C1 | 100k / 22k / 100 nF | Battery divider → PA0 |
| BZ1 | AST1341MCTRQ | Piezo buzzer, directly on PB9 |
| U6 + R4 | FZ2812-5050 + 330R | WS2812-type RGB LED on PB8 |
| D1 + R3 | LED + 1k | 3.3 V power LED (not MCU-controlled) |
| TP1–TP5 | Test points | GND, BATT, 5V, 3V3, VBAT_SENSE |

## Pin map

| Function | MCU pin | Peripheral | Connected to | Confidence |
|---|---|---|---|---|
| IMU SCK | PA5 | SPI1_SCK | U4 SCL/SCK | PCB (schematic copy stale) |
| IMU MISO | PA6 | SPI1_MISO | U4 DO | PCB |
| IMU MOSI | PA7 | SPI1_MOSI | U4 SDA/SDI | PCB |
| IMU CS | PA4 | GPIO | U4 CS | PCB |
| IMU INT1 | PA1 | EXTI1 | U4 I1 (I2 unused) | PCB |
| Baro SCL | PB6 | I2C1_SCL | U3 SCL | confirmed |
| Baro SDA | PB7 | I2C1_SDA | U3 SDA | confirmed |
| GPS → MCU | PA10 | USART1_RX | U2 TX | confirmed |
| MCU → GPS | PA9 | USART1_TX | U2 RX | confirmed |
| GPS PPS | PA8 | TIM1_CH1 | U2 PPS | confirmed |
| MCU → RX | PA2 | USART2_TX | J6 pin 2 (receiver RX) | confirmed |
| RX → MCU | PA3 | USART2_RX | J6 pin 3 (receiver TX) | confirmed |
| Motor 1 | PB1 | TIM3_CH4 | J2 pin 3 | confirmed |
| Motor 2 | PB0 | TIM3_CH3 | J3 pin 3 | confirmed |
| Motor 3 | PB4 | TIM3_CH1 | J4 pin 3 | confirmed |
| Motor 4 | PB5 | TIM3_CH2 | J5 pin 3 | confirmed |
| VBAT sense | PA0 | ADC1_IN0 | R1/R2 divider | confirmed |
| Buzzer | PB9 | TIM4_CH4 | BZ1 + (− to GND) | confirmed |
| RGB LED | PB8 | TIM4_CH3 | R4 → U6 DIN | confirmed |
| Status LED | PC13 | GPIO, active low | Black Pill on-board LED | board-known |
| SWD | PA13 / PA14 | — | Black Pill SWD header | board-known |

**Free:** PB10, PB12–PB15 (SPI2), PA15, PB3, PC14, PC15. PA11/PA12 are USB (debug console). USART6 can only use PA11/PA12, so there's no spare UART unless USB is given up.

## Power

XT60 → +BATT → MP1584EN → **+5V** (Black Pill 5V pins, J6 receiver power) → Black Pill LDO → **+3.3V** (GPS VIN, BMP581, ISM330DHCX, FZ2812, power LED). ESCs are powered off-board; the motor headers carry no power.

> **2026-10-10:** the MP1584EN buck (U5) burnt out and has been removed. The owner provides the +5V supply separately. Battery sensing is unaffected (the divider is fed straight from the XT60).

## Battery divider

- Ratio = 22k / (100k + 22k) = **0.1803**, i.e. ×5.545.
- 4S full (16.8 V) → 3.03 V at PA0. Full scale (3.3 V ref) = **18.3 V**. OK for 4S, **not for 5S/6S**.
- Source impedance 18 kΩ with 100 nF (τ ≈ 1.8 ms): use a long ADC sample time; the reading is effectively low-passed.
- Trim `VBAT_SCALE_TRIM` in `config.h` against a multimeter (resistor tolerance plus the LDO's actual 3.3 V).

## Timers and DMA plan

| Use | Timer / DMA | Notes |
|---|---|---|
| DShot300 ×4 | TIM3 CH1–4, **burst DMA on TIM3_UP = DMA1 Stream2 Ch5** | TIM3 clock 96 MHz (APB1 48 MHz ×2). Bit = 320 ticks, T0H = 120, T1H = 240. One stream for all motors, which avoids the CH2 (S5) / CH3 (S7) per-channel streams. |
| CRSF | USART2 (APB1), 420000 baud | Interrupt-driven HardwareSerial, 256-byte RX buffer. USART IRQ priority above the control loop. |
| GPS | USART1 | 9600 default, PMTK to 38400 / 10 Hz later |
| GPS PPS | TIM1_CH1 input capture (later) | |
| Buzzer | TIM4_CH4 PWM ~4.1 kHz (HardwareTimer) | |
| RGB LED | TIM4_CH3 + DMA1 Stream7 Ch2 (deferred) | Conflicts with a TIM4 buzzer frequency; revisit later |
| Arduino-reserved | TIM10 (tone), TIM11 (servo) | Don't use `tone()`/`Servo`/`analogWrite` on motor pins |

## Concerns

### Critical
1. **Stale schematic for the IMU.** In the repo copy, U4 has no wires at all (ERC: 21 unconnected pins), while the PCB wires it to SPI1/IMU_CS/IMU_INT/3.3V/GND (DRC parity: 8 net conflicts). The owner says the built board is fully connected. **Don't run "Update PCB from Schematic" on these files**, because it would strip the IMU nets. Sync the repo to the real design.
2. **ROM bootloader hijack.** In BOOT0/DFU mode the F411's system bootloader also listens on USART1 (PA10 = GPS TX) and USART2 (PA3 = receiver TX), so traffic there can make USB DFU fail. **Flash over ST-Link (SWD)**, which is the project default.

### Medium
3. **Unrouted on the PCB (repo copy):** TP4 (+3.3V) and TP3 (+5V) test points aren't connected, and **C4 (10 µF on +5V) has no footprint**, so it isn't on the board. Measure the rails at the Black Pill pins.
4. **PA0 = Black Pill KEY button.** Pressing KEY pulls VBAT_SENSE to 0 V (harmless through 100k). Firmware: no pull-ups on PA0; debounce battery alarms.
5. **Buzzer drive.** The AST1341MCTRQ appears to be an externally driven piezo (~4.1 kHz, ~8 mA, rated 90 dB at 12 V). That comes from a distributor listing; **I haven't confirmed it against the datasheet.** At 3.3 V GPIO drive it will be fairly quiet, which is weak for locating a downed drone. Consider a transistor/5 V driver in a later revision.
6. **FZ2812 at 3.3 V** is below the usual WS2812 VDD range, so colours may be wrong. It's low priority.
7. **ELRS cable.** The receiver's TX must go to **J6 pin 3** and its RX to **J6 pin 2**.
8. **No current sensor, no blackbox storage, no ESC telemetry line.**
9. **USB + battery together:** I haven't checked whether the Black Pill's VBUS has back-feed protection. Rule: **props off whenever USB is connected.** Firmware will refuse to arm while the USB console is open unless built with `-DALLOW_ARM_WITH_USB=1`.

### Not on this board (per the VIGIL brief)
- **FLIR Lepton:** not in the schematic netlist. SPI1 is the IMU's, and the F411 shouldn't carry VoSPI video alongside the control loop, so the thermal camera belongs on the Embedded subsystem's own processor and link.
- **Magnetometer:** proposed, not fitted. Simplest option: share I2C1 (PB6/PB7) with the BMP581, mounted away from the ESC and battery wiring.
- **Telemetry link to ground:** the only confirmed link is ExpressLRS (CRSF telemetry downlink to the radio). USB is bench-only. VehicleTelemetry fields without a sensor (yaw without a mag, GPS before Stage 10) must be reported as unavailable.

### Unknowns (resolved on hardware)
- ~~IMU axes vs. the airframe's nose~~ **Resolved 2026-10-10:** the IMU is rotated 90° CCW (seen from above), so `align_board_yaw = 2700`. This is the default in `REDSTART/config.c`.
- Motor position and spin direction for each header. Default is the Betaflight Quad-X convention: M1 rear-right CW, M2 front-right CCW, M3 rear-left CCW, M4 front-left CW ("props in"). Verify in Stage 4.
- BMP581 address (0x47 default, 0x46 with the SDO jumper). Whether the GPS coin cell is fitted.
