# Flight-control stack evaluation (VIGIL brief, Agent 4 task 2)

**Question:** can Redstart run mature flight-control firmware instead of a custom stack?
**Date:** 2026-10-10. Sources: Betaflight `master` and `betaflight/config` on GitHub, INAV wiki.

## Candidates

| Stack | Runs on F411? | ISM330DHCX | BMP581 | Verdict |
|---|---|---|---|---|
| **Betaflight** | Yes: `src/platform/STM32/target/STM32F411` in master, many F411 boards in the config repo | **No** (closest: `lsm6dso` driver, which checks WHO_AM_I = 0x6C; ours is 0x6B) | **Yes** (`barometer_bmp5xx.c`, I2C 0x47/0x46) | **Recommended** with a small patch |
| INAV | Only up to INAV 7 (F411 dropped from INAV 8) | not checked | not checked | Old branch; only worth it later for waypoints |
| ArduPilot | No: copter firmware needs more than 512 KB flash (from memory, not checked) | — | — | Not viable on this MCU |
| Custom (current repo) | Yes | Own driver | Own driver | Works, but all the flight-critical code is ours to write and tune |

## The ISM330DHCX gap

Betaflight's LSM6DSO init writes registers that sit at the same addresses with the same bit encodings on the ISM330DHCX. The ISM330DHCX side below is from my knowledge of the ST datasheet; re-check it against the PDF before flashing.

| Register | Betaflight value | ISM330DHCX |
|---|---|---|
| WHO_AM_I 0x0F | expects 0x6C | **0x6B**: the only blocking difference |
| INT1_CTRL 0x0D | 0x02 (gyro DRDY on INT1) | same |
| CTRL1_XL 0x10 | 0x74 (833 Hz, ±16 g) | same encoding |
| CTRL2_G 0x11 | 0xAC (6.66 kHz, ±2000 dps) | same encoding |
| CTRL3_C/CTRL4_C/CTRL6_C | BDU, auto-inc, I2C disable, LPF1 | same layout |
| CTRL9_XL bit 1 | "I3C disable" = 1 | "DEVICE_CONF", which ST recommends setting to 1 → compatible |
| Data 0x22–0x2D, scales | 70 mdps/LSB, 0.488 mg/LSB | same |

**Patch:** accept 0x6B in `lsm6dsoDetect()` (or add a `USE_ACCGYRO_ISM330DHCX` variant). It's about 10 lines. Validate it the same way as custom Stage 2: tilt and rotation signs, gyro noise, accel ≈ 1 g.

## Draft Betaflight board config (`configs/REDSTART/config.h`)

Pins come from `docs/hardware.md`. Items marked ⚠ need checking at build time.

```c
#define FC_TARGET_MCU     STM32F411
#define BOARD_NAME        REDSTART
#define MANUFACTURER_ID   CUST
#define SYSTEM_HSE_MHZ    25                 // Black Pill crystal ⚠ check F411 PLL setup accepts 25

#define USE_GYRO
#define USE_ACC
#define USE_ACCGYRO_LSM6DSO                  // + ISM330DHCX chip-ID patch
#define GYRO_1_SPI_INSTANCE SPI1
#define GYRO_1_CS_PIN        PA4
#define GYRO_1_EXTI_PIN      PA1
#define GYRO_1_ALIGN         CW0_DEG         // ⚠ set from tilt tests (U4 is placed at 180°)
#define SPI1_SCK_PIN         PA5
#define SPI1_SDI_PIN         PA6
#define SPI1_SDO_PIN         PA7

#define USE_BARO
#define USE_BARO_BMP5XX                      // ⚠ confirm exact define name
#define BARO_I2C_INSTANCE    I2CDEV_1
#define I2C1_SCL_PIN         PB6
#define I2C1_SDA_PIN         PB7
#define MAG_I2C_INSTANCE     I2CDEV_1        // future magnetometer on the same bus

#define UART1_TX_PIN         PA9             // GPS
#define UART1_RX_PIN         PA10
#define UART2_TX_PIN         PA2             // ELRS / CRSF
#define UART2_RX_PIN         PA3

#define MOTOR1_PIN           PB1
#define MOTOR2_PIN           PB0
#define MOTOR3_PIN           PB4
#define MOTOR4_PIN           PB5
#define BEEPER_PIN           PB9
#define BEEPER_PWM_HZ        4100            // passive piezo
#define LED_STRIP_PIN        PB8
#define LED0_PIN             PC13
#define ADC_VBAT_PIN         PA0
#define DEFAULT_VOLTAGE_METER_SOURCE VOLTAGE_METER_ADC
#define DEFAULT_VOLTAGE_METER_SCALE  55      // 10 * (100k+22k)/22k ≈ 55.5 ⚠ trim vs multimeter

#define TIMER_PIN_MAPPING \
    TIMER_PIN_MAP( 0, PB1, 2, 0) /* TIM3_CH4 */ \
    TIMER_PIN_MAP( 1, PB0, 2, 0) /* TIM3_CH3 */ \
    TIMER_PIN_MAP( 2, PB4, 1, 0) /* TIM3_CH1 */ \
    TIMER_PIN_MAP( 3, PB5, 1, 0) /* TIM3_CH2 */ \
    TIMER_PIN_MAP( 4, PB9, 1, -1) /* TIM4_CH4 beeper */ \
    TIMER_PIN_MAP( 5, PB8, 1, 0) /* TIM4_CH3 LED strip */
    // ⚠ occurrence indices to be checked against Betaflight's F411 timer table

#define DEFAULT_DSHOT_BURST  DSHOT_DMAR_ON   // all motors on TIM3 → one TIM3_UP DMA stream
```

The layout is very close to the existing `MATEKF411` config (gyro on SPI1 with PA4 CS / PA1 EXTI, UART1/UART2 on the same pins), which is a good sign.

## What Betaflight gives us, mapped to the brief

| Brief task | Betaflight | Custom |
|---|---|---|
| 3. Debug, IMU, baro, battery | Configurator GUI (sensors tab, 3D model for axis checks) | Stages 1–2 to write |
| 4. CRSF + signal loss | Built in; receiver tab; tested failsafe stages | Stage 3 to write |
| 5. ESC order/direction, arming, throttle limit, failsafe | Motors tab (props off), DShot direction commands, arming-prevention flags, throttle limit | Stages 4 and 8 to write |
| 6. Stable attitude control | Mature filters/PID/angle mode with flight-proven defaults | Stages 5–7 to write and tune |
| 7. VehicleTelemetry | CRSF telemetry downlink (battery, attitude, baro alt, GPS, link stats) and MSP | To write |

## Costs and risks of Betaflight

- **Maintaining a fork:** a small patch on top of Betaflight plus our config. Getting the source needs a clone or tarball of `betaflight/betaflight`.
- **Toolchain:** Betaflight's `make arm_sdk_install` downloads its own ARM GCC. Build with `make CONFIG=REDSTART CONFIG_DIR=<our dir>`.
- **Flashing:** still use ST-Link (the DFU bootloader-hijack issue applies to every firmware). Configurator connects over USB CDC for setup.
- **Licence:** GPL-3.0. A distributed fork must stay GPL. Fine for a hackathon, but tell the team.
- **Stretch goals:** Betaflight has GPS Rescue but no waypoint missions. Predefined paths would need INAV 7 (last F411 release) or a companion computer. That's after the MVP anyway.
- **Unverified items** are marked ⚠ above; all of them get settled at the first build and on the bench.

## Constraints added 2026-10-10

- **No companion computer** and no system modifications of that kind, so MSP-override autonomy is out.
- **Radio:** RadioMaster Pocket (EdgeTX, internal ELRS) → RP1 V2 receiver over CRSF.

## Path automation: INAV 7.1.2 checked against our hardware

INAV 7 is the last release for the F411 and the only firmware-only option with native waypoint missions (planned in INAV Configurator's Mission Control over USB before flight).

| Item | INAV 7.1.2 | Work needed |
|---|---|---|
| ISM330DHCX | `accgyro_lsm6dxx.c` accepts only 0x6C (LSM6DSO) and 0x6A (LSM6DSL) | Chip-ID patch, same as Betaflight |
| BMP581 | **No driver** (bmp085/280/388, dps310, spl06, ms56xx, …) | Port Betaflight's `bmp5xx` driver |
| Adafruit GPS (MTK3339, NMEA) | **NMEA support removed in INAV 7.0** (UBLOX/UBLOX7 only) | Re-add an NMEA parser, **or** fit a u-blox module |
| Magnetometer | Not fitted. 7.1 reportedly allows compass-less navigation, but a compass is strongly recommended | — |
| Board target | Old-style `target.h`/`target.c` | New target dir |
| Maintenance | Frozen: no fixes for F411 after 7.x | — |

Betaflight, by contrast, **supports NMEA** (protocol options UBLOX / NMEA / MSP) and has a BMP5xx driver. Its only gap is the IMU chip ID.

## Recommendation (revised 2026-10-10): one codebase, INAV 7.1.2, grown in milestones

The hardware is fixed, and switching firmware mid-project means a second bring-up, tune and bench validation. So we pick the stack that can grow into the stretch goal without a restart. That's **INAV 7.1.2**, the only firmware-only route to waypoint missions on an F411. It adds capability one driver at a time, and every milestone leaves a working, flyable drone.

Facts this rests on:
- **No compass needed:** the INAV 7.1 notes say a compass "is no longer mandatory for multirotor navigation". The limitation is that navigation modes "will not be operational UNTIL a GPS heading is first obtained" by flying in a straight line. Drift is worse than with a compass.
- **NMEA:** INAV 6.1.1 still had `src/main/io/gps_nmea.c`, so restoring NMEA is a port forward within the same codebase.
- **BMP581:** Betaflight's `barometer_bmp5xx.c` exists and only needs porting.

| Milestone | Firmware work | Gives us | Brief gate |
|---|---|---|---|
| M0 | REDSTART target + ISM330DHCX chip-ID patch | Configurator connects; sensors tab; set the board alignment by tilt tests | task 3 |
| M1 | config only | CRSF from the Pocket/RP1, failsafe, DShot props-off motor order/direction, arming checks | tasks 4–5 |
| M2 | tuning only | **Stable manual angle-mode flight: the flight MVP** | gate 3 |
| M3 | port BMP581 driver | Altitude hold | — |
| M4 | port NMEA GPS | GPS fix, position hold, failsafe return-to-home, GPS in telemetry | — |
| M5 | config/missions | Waypoint missions planned in Configurator (stretch) | gate 5 |

M0–M2 cost about the same as the Betaflight route (one small patch plus a target). The extra porting only starts after the drone flies. If hackathon time runs out after M2, we still have the MVP.

**Trade-offs we accept**
- INAV's multirotor attitude control is less refined than Betaflight's. That's fine for a 7" camera platform; we're not racing.
- The F411 branch is frozen (no upstream fixes).
- Compass-less navigation: get a GPS heading before engaging nav modes; expect more position drift. To change nav modes in INAV 7.1 Configurator, enable a fake compass temporarily (known Configurator issue).
- GPL-3.0 applies to our fork.

The Betaflight board-config draft above still documents the pin and timer mapping, which carries over to the INAV target.
