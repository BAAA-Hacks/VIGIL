/*
 * Redstart (VIGIL) flight controller: WeAct Black Pill V3.1 (STM32F411CEU6)
 * on the Redstart carrier PCB. Pin map: flight-controller/docs/hardware.md.
 *
 * This file is part of INAV, licensed under the GNU GPL v3 or later.
 */

#pragma once

#define TARGET_BOARD_IDENTIFIER "RDST"
#define USBD_PRODUCT_STRING     "REDSTART"

#define LED0                    PC13    // Black Pill on-board LED

// Passive piezo (AST1341MCTRQ) driven directly by TIM4_CH4
#define BEEPER                  PB9
#define BEEPER_PWM_FREQUENCY    4100

// *************** SPI1: ISM330DHCX IMU (Adafruit breakout) ***********
#define USE_SPI
#define USE_SPI_DEVICE_1
#define SPI1_SCK_PIN            PA5
#define SPI1_MISO_PIN           PA6
#define SPI1_MOSI_PIN           PA7

#define USE_IMU_LSM6DXX         // ISM330DHCX accepted by the patched lsm6dxx driver
#define IMU_LSM6DXX_ALIGN       CW0_DEG // set align_board_* from tilt tests
#define LSM6DXX_CS_PIN          PA4
#define LSM6DXX_SPI_BUS         BUS_SPI1
// INT1 (data-ready) is wired to PA1, but INAV polls the gyro; unused for now.

// *************** I2C1: BMP581 baro, future magnetometer *********
#define USE_I2C
#define USE_I2C_DEVICE_1
#define I2C1_SCL                PB6
#define I2C1_SDA                PB7
#define DEFAULT_I2C_BUS         BUS_I2C1

#define USE_BARO
#define BARO_I2C_BUS            BUS_I2C1
#define USE_BARO_BMP581         // patches/0004 (Bosch BMP581, address 0x47 or 0x46)

#define USE_MAG
#define MAG_I2C_BUS             BUS_I2C1
#define USE_MAG_ALL

// *************** UARTs ***********************************************
#define USE_VCP

#define USE_UART1               // GPS (Adafruit Ultimate GPS)
#define UART1_TX_PIN            PA9
#define UART1_RX_PIN            PA10

#define USE_UART2               // ExpressLRS RP1 V2 (CRSF)
#define UART2_TX_PIN            PA2
#define UART2_RX_PIN            PA3

#define SERIAL_PORT_COUNT       3   // VCP, UART1, UART2

#define DEFAULT_RX_TYPE         RX_TYPE_SERIAL
#define SERIALRX_PROVIDER       SERIALRX_CRSF
#define SERIALRX_UART           SERIAL_PORT_USART2

// *************** ADC: battery voltage (100k / 22k divider) ************
#define USE_ADC
#define ADC_INSTANCE            ADC1
#define ADC1_DMA_STREAM         DMA2_Stream0
#define ADC_CHANNEL_1_PIN       PA0     // shared with the Black Pill KEY button
#define VBAT_ADC_CHANNEL        ADC_CHN_1
#define VBAT_SCALE_DEFAULT      555     // (100k + 22k) / 22k x 100; trim vs multimeter

// *************** Outputs *********************************************
#define USE_DSHOT
#define USE_SERIAL_4WAY_BLHELI_INTERFACE

#define DEFAULT_FEATURES        (FEATURE_TX_PROF_SEL | FEATURE_VBAT | FEATURE_TELEMETRY)

#define TARGET_IO_PORTA         0xffff
#define TARGET_IO_PORTB         0xffff
#define TARGET_IO_PORTC         (BIT(13) | BIT(14) | BIT(15))

#define MAX_PWM_OUTPUT_PORTS    4
