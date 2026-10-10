/*
 * Redstart (VIGIL) timer map. All four motors are on TIM3.
 *
 * This file is part of INAV, licensed under the GNU GPL v3 or later.
 */

#include <stdbool.h>
#include <platform.h>
#include "drivers/bus.h"
#include "drivers/io.h"
#include "drivers/pwm_mapping.h"
#include "drivers/timer.h"

timerHardware_t timerHardware[] = {
    DEF_TIM(TIM3, CH4, PB1, TIM_USE_OUTPUT_AUTO, 0, 0), // M1  J2
    DEF_TIM(TIM3, CH3, PB0, TIM_USE_OUTPUT_AUTO, 0, 0), // M2  J3
    DEF_TIM(TIM3, CH1, PB4, TIM_USE_OUTPUT_AUTO, 0, 0), // M3  J4
    DEF_TIM(TIM3, CH2, PB5, TIM_USE_OUTPUT_AUTO, 0, 0), // M4  J5

    DEF_TIM(TIM4, CH4, PB9, TIM_USE_BEEPER, 0, 0),      // piezo beeper
};

const int timerHardwareCount = sizeof(timerHardware) / sizeof(timerHardware[0]);
