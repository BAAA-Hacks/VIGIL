#pragma once

#include <Arduino.h>
#include <IPAddress.h>

// Pins (Seeed XIAO ESP32-S3 GPIO numbers; Dx labels from the variant's pins_arduino.h)
constexpr int PIN_I2C_SDA = 5;      // D4
constexpr int PIN_I2C_SCL = 6;      // D5
constexpr int PIN_SPI_SCK = 7;      // D8
constexpr int PIN_SPI_MISO = 8;     // D9
constexpr int PIN_LEPTON_CS = 4;    // D3
constexpr int PIN_LEPTON_VSYNC = 3; // D2 (strapping pin, only sampled at reset)
constexpr int PIN_LEPTON_RESET = 2; // D1, RESET_L (active low)

constexpr uint32_t I2C_CLOCK_HZ = 400000;
// The Lepton accepts up to 20 MHz on VoSPI. These pins go through the GPIO matrix, so
// drop to 16 MHz if the serial log shows frequent resyncs.
constexpr uint32_t SPI_CLOCK_HZ = 20000000;

// Wait for the Lepton's VSYNC pulse before reading a segment. Set to false to poll instead.
constexpr bool USE_VSYNC = true;
constexpr uint32_t VSYNC_WAIT_MS = 20;  // fall back to polling if no pulse arrives in time
// After VSYNC (or each poll), keep reading discard packets this long for a segment to start.
// Segments arrive every ~9.4 ms; the first packets after the VSYNC edge are still discards.
constexpr uint32_t SEGMENT_START_WAIT_US = 5000;

// Camera bring-up and recovery
constexpr uint32_t CAMERA_READY_TIMEOUT_MS = 15000;  // boot + first FFC
constexpr uint32_t CAMERA_NO_FRAME_RESET_MS = 3000;  // hardware reset after this long without a frame
constexpr uint32_t CAMERA_RETRY_DELAY_MS = 2000;

// Frame geometry (Lepton 3.5, Raw14/TLinear)
constexpr int FRAME_WIDTH = 160;
constexpr int FRAME_HEIGHT = 120;
constexpr size_t FRAME_PIXELS = FRAME_WIDTH * FRAME_HEIGHT;
constexpr size_t FRAME_BYTES = FRAME_PIXELS * 2;

// Wi-Fi access point
// SSID and password live in the untracked secrets.h (copy secrets.example.h; password >= 8 chars).
#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Missing include/secrets.h: copy include/secrets.example.h to include/secrets.h and set the password"
#endif
constexpr uint8_t AP_CHANNEL = 6;
constexpr uint8_t AP_MAX_STATIONS = 4;
const IPAddress AP_IP(192, 168, 4, 1);
const IPAddress AP_NETMASK(255, 255, 255, 0);
constexpr uint16_t HTTP_PORT = 80;

// Streaming
constexpr size_t MAX_MJPEG_CLIENTS = 3;
constexpr size_t MAX_RAW_CLIENTS = 1;
constexpr size_t MAX_CAPTURE_CLIENTS = 2;  // concurrent /capture requests waiting for a frame
constexpr size_t JPEG_BUFFER_SIZE = 48 * 1024;
constexpr uint32_t CLIENT_WRITE_TIMEOUT_MS = 2000;  // give up on one frame/part after this long
constexpr uint32_t CLIENT_STALL_DROP_MS = 5000;     // drop a client that has accepted nothing for this long
constexpr size_t RAW_HEADER_BYTES = 24;
constexpr size_t RAW_RECORD_BYTES = RAW_HEADER_BYTES + FRAME_BYTES;

// Tasks: capture alone on core 1 at high priority; Wi-Fi, HTTP and encoding on core 0.
constexpr BaseType_t CAPTURE_CORE = 1;
constexpr UBaseType_t CAPTURE_PRIORITY = configMAX_PRIORITIES - 2;
constexpr uint32_t CAPTURE_STACK = 6144;
constexpr BaseType_t NET_CORE = 0;
constexpr UBaseType_t STREAM_PRIORITY = 3;
constexpr uint32_t STREAM_STACK = 8192;
constexpr UBaseType_t HTTP_PRIORITY = 2;
constexpr uint32_t HTTP_STACK = 8192;

constexpr uint32_t DIAG_INTERVAL_MS = 1000;
