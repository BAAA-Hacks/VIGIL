# Firmware architecture (superseded)

> **Superseded on 2026-10-10:** Redstart flies **INAV 7.1.2** with a custom `REDSTART` target (see `docs/stack-evaluation.md` and `docs/bringup.md`). This page describes the custom-firmware design we considered first. It's kept for reference only.

## Framework

**PlatformIO + STM32duino (Arduino core for STM32), bare-metal, no RTOS.**

- STM32duino gives USB CDC, HardwareSerial, SPI and Wire with little setup, and ships the full ST HAL/LL. The timing-critical pieces (DShot DMA, NVIC priorities, DWT cycle timing, EXTI) use HAL/LL or registers directly, so the Arduino layer never sits in the flight-critical path.
- No Adafruit sensor libraries (blocking BusIO, I2C-centric, slow). Each sensor gets a small register-level driver.
- No RTOS: one interrupt-driven fast path plus a cooperative slow loop is easier to reason about and to make deterministic.

## Timing model

```
IMU INT1 (PA1, 1666 Hz) ──► EXTI ISR  [fast path, must finish < ~150 µs]
                              read gyro+accel (SPI1) → rotate/bias → filter
                              → attitude → (angle loop) → rate PID → mixer
                              → DShot frame (TIM3 burst DMA)

loop()  [slow path, cooperative, nothing here can stall the fast path]
   CRSF parse (every pass) · arming/failsafe (500 Hz) · battery (50 Hz)
   baro (50 Hz) · console/telemetry · buzzer/LED · GPS (later)
```

- **NVIC priority:** USART1/2 (bytes every 24 µs at 420 kbaud) > control EXTI > USB and the rest.
- **Shared state:** small structs copied under a brief `noInterrupts()`: `loop()` → ISR (setpoints, armed, mode) and ISR → `loop()` (attitude, gyro, timing stats).
- **Cross-watchdogs:** the ISR disarms if `loop()`'s heartbeat is older than 100 ms. `loop()` flags an IMU fault and disarms if no samples arrive for 10 ms. The hardware IWDG comes in Stage 8.

## Modules

```
include/board.h      pins/peripherals (single source of truth)
include/config.h     tunables (rates, gains, failsafe timings, motor remap, IMU rotation, battery trim)
src/main.cpp         setup(), loop() scheduler, ISR wiring
src/drivers/         ism330dhcx · bmp581 · crsf_uart · dshot · battery_adc · buzzer · gps_nmea
src/tasks/           console/telemetry · status LED/buzzer patterns
lib/fc_core/         hardware-free logic, unit-tested on the PC (pio test -e native):
                     filters · battery · crsf_parser · pid · mixer_quadx · attitude (Mahony)
                     · arming (state machine) · rotation
```

The rule for `lib/fc_core`: no Arduino or HAL includes. Anything that decides what the motors do should be testable without hardware.

## Safety design

- **Boot:** DISARMED. Motor pins are driven LOW as the first action in `setup()`. Once DShot runs, it continuously sends 0 (motor stop). There's no throttle calibration path (DShot doesn't need one).
- **Arming requires all of:** an arm-switch off→on transition seen *after* boot, low throttle, a fresh RC link (< 100 ms), IMU healthy and gyro calibration done (still for 1 s), tilt < 25°, a battery detected (3S/4S) that isn't critical, the control loop at rate, the USB console closed (unless the bench flag is set), and motor-test mode off.
- **Disarm:** arm switch off (immediate, in any state), IMU fault, stale `loop()` heartbeat.
- **RC failsafe:** no valid frame for 100 ms → stage 1: level the quad and hold throttle at a configured value for `FS_STAGE1_MS` → stage 2: **disarm** (motors stop).
- **Motor test (console):** disarmed only, needs an explicit props-off confirmation, throttle capped, 2 s auto-timeout.

## Flight modes

1. **Angle** (self-levelling; used for first flights): stick → target angle → P loop → rate setpoint.
2. **Acro/rate:** stick → rate setpoint directly.

Both feed the same rate PID → Quad-X mixer.
