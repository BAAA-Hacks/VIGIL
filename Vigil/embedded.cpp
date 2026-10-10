// VIGIL: standard XIAO ESP32-S3, ESP-IDF / PlatformIO.
// Paste this whole file into src/main.cpp. No Arduino libraries required.
// Lepton breakout: SCK=D8/GPIO7, MISO=D9/GPIO8, CS=D1/GPIO2.
// SDA=D4/GPIO5, SCL=D5/GPIO6. Confirm breakout power requirements separately.
// Requires Raw16 output, telemetry disabled. CCI configuration and packet CRC
// checking are not implemented in this bring-up version.
#include <cstdint>
#include <cstring>
#include <cstdio>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "driver/spi_master.h"
#include "driver/i2c.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "esp_http_server.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "nvs_flash.h"

// ASSEMBLER_INSERT
// VIEWER_INSERT

static constexpr char SSID[] = "VIGIL-Thermal";
static constexpr char PASSWORD[] = "vigil-demo-35";
static spi_device_handle_t camera;
static FrameAssembler assembler;
static SemaphoreHandle_t frameMutex;
static uint8_t latest[FrameAssembler::Bytes];
static uint8_t outgoing[FrameAssembler::Bytes];
static uint32_t frameId = 0;
static int64_t frameTime = 0;
static constexpr const char* TAG = "VIGIL";

static void capture(void*) {
    // Internal DRAM, 4-byte aligned for DMA.
    alignas(4) static uint8_t rx[164];
    int64_t lastComplete = esp_timer_get_time();
    int64_t lastYield = lastComplete;
    vTaskDelay(pdMS_TO_TICKS(1000));
    for (;;) {
        spi_transaction_t transaction{};
        transaction.length = sizeof(rx) * 8;
        transaction.rx_buffer = rx;
        esp_err_t error = spi_device_polling_transmit(camera, &transaction);
        if (error == ESP_OK && assembler.push(rx)) {
            xSemaphoreTake(frameMutex, portMAX_DELAY);
            memcpy(latest, assembler.frame, sizeof(latest));
            ++frameId;
            frameTime = esp_timer_get_time();
            xSemaphoreGive(frameMutex);
            lastComplete = esp_timer_get_time();
        }
        if (error != ESP_OK || esp_timer_get_time() - lastComplete > 1500000) {
            // Hardware CS stays high while no SPI transactions are issued.
            vTaskDelay(pdMS_TO_TICKS(200));
            assembler.reset();
            lastComplete = esp_timer_get_time();
        }
        if (esp_timer_get_time() - lastYield > 10000) {
            vTaskDelay(1);
            lastYield = esp_timer_get_time();
        }
    }
}

static esp_err_t rootHandler(httpd_req_t* request) {
    httpd_resp_set_type(request, "text/html");
    return httpd_resp_send(request, viewer, HTTPD_RESP_USE_STRLEN);
}
static esp_err_t frameHandler(httpd_req_t* request) {
    uint32_t id;
    int64_t stamp;
    xSemaphoreTake(frameMutex, portMAX_DELAY);
    id = frameId;
    stamp = frameTime;
    if (id) memcpy(outgoing, latest, sizeof(outgoing));
    xSemaphoreGive(frameMutex);
    if (!id || esp_timer_get_time() - stamp > 2000000) {
        httpd_resp_set_status(request, "503 Service Unavailable");
        return httpd_resp_send(request, "No fresh complete Lepton frame", HTTPD_RESP_USE_STRLEN);
    }
    char idText[24], timeText[24];
    snprintf(idText, sizeof(idText), "%lu", static_cast<unsigned long>(id));
    snprintf(timeText, sizeof(timeText), "%llu", static_cast<unsigned long long>(stamp / 1000));
    httpd_resp_set_type(request, "application/octet-stream");
    httpd_resp_set_hdr(request, "Cache-Control", "no-store");
    httpd_resp_set_hdr(request, "X-Frame-Id", idText);
    httpd_resp_set_hdr(request, "X-Timestamp-Ms", timeText);
    httpd_resp_set_hdr(request, "X-Width", "160");
    httpd_resp_set_hdr(request, "X-Height", "120");
    httpd_resp_set_hdr(request, "X-Pixel-Format", "lepton_raw16_be");
    return httpd_resp_send(request, reinterpret_cast<const char*>(outgoing), sizeof(outgoing));
}