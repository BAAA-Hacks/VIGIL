/*
 * Redstart (VIGIL) default configuration.
 *
 * This file is part of INAV, licensed under the GNU GPL v3 or later.
 */

#include <stdint.h>
#include "platform.h"

#include "fc/config.h"
#include "io/serial.h"
#include "sensors/boardalignment.h"

void targetConfiguration(void)
{
    // The IMU breakout is mounted rotated 90 deg CCW (seen from above) relative to the
    // airframe; confirmed by tilt test in Configurator on 2026-10-10.
    boardAlignmentMutable()->yawDeciDegrees = 2700;

    // BZ1 is a passive piezo: it needs the 4.1 kHz PWM tone (TIM4_CH4); DC drive is silent.
    beeperConfigMutable()->pwmMode = true;

    // UART1 -> Adafruit Ultimate GPS (NMEA support arrives in milestone M4)
    serialConfigMutable()->portConfigs[findSerialPortIndexByIdentifier(SERIAL_PORT_USART1)].functionMask = FUNCTION_GPS;
}
