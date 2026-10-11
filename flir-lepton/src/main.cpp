// FLIR Lepton 3.5 thermal camera streamer for the Seeed XIAO ESP32-S3.
// Captures VoSPI frames on core 1 and serves them from a standalone Wi-Fi AP on core 0.

#include <Arduino.h>
#include <Wire.h>

#include "LeptonCamera.h"
#include "StreamServer.h"
#include "ThermalProcessor.h"
#include "config.h"

static const char* TAG = "main";

LeptonCamera camera;
ThermalProcessor processor;
StreamServer server(camera, processor);

static void diagTask(void*);

static bool scanForLepton() {
  Wire.beginTransmission(0x2a);
  return Wire.endTransmission() == 0;
}

void setup() {
  Serial.begin(115200);
  delay(1500);  // give USB-CDC time to enumerate so the boot log is visible

  ESP_LOGI(TAG, "Lepton streamer starting, chip %s rev %d, %u MHz", ESP.getChipModel(), ESP.getChipRevision(),
           ESP.getCpuFreqMHz());
  if (psramFound()) {
    ESP_LOGI(TAG, "PSRAM: %u bytes", (unsigned)ESP.getPsramSize());
  } else {
    ESP_LOGW(TAG, "no PSRAM found, using internal RAM only");
  }

  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, I2C_CLOCK_HZ);
  // The Lepton holds I2C until it has booted, so a miss here right after power-up is not fatal.
  ESP_LOGI(TAG, "I2C scan: Lepton (0x2A) %s", scanForLepton() ? "found" : "not responding yet");

  if (!processor.begin()) {
    ESP_LOGE(TAG, "thermal processor init failed");
  }
  if (!camera.begin()) {
    ESP_LOGE(TAG, "camera init failed");
  }
  if (!server.begin()) {
    ESP_LOGE(TAG, "server init failed");
  }
  xTaskCreatePinnedToCore(diagTask, "diag", 4096, nullptr, 1, nullptr, NET_CORE);
  ESP_LOGI(TAG, "join Wi-Fi '%s' and open http://%s/", AP_SSID, AP_IP.toString().c_str());
}

// 1 Hz status line. Runs on core 0 so the capture task on core 1 can't starve it.
static void diagTask(void*) {
  uint32_t lastFrames = 0;
  while (true) {
    LeptonCamera::Stats stats = camera.getStats();
    ESP_LOGI(TAG, "%s fps=%.2f frames=%u (+%u) invalid=%u resyncs=%u outOfPhase=%u resets=%u vsyncTimeouts=%u "
             "packets=%u discardPkts=%u discardSegs=%u hdr=%02x%02x%02x%02x heap=%u psram=%u stations=%u mjpeg=%u raw=%u",
             LeptonCamera::stateName(stats.state), stats.fps, stats.framesCaptured, stats.framesCaptured - lastFrames,
             stats.framesInvalid, stats.resyncs, stats.outOfPhase, stats.resets, stats.vsyncTimeouts, stats.packets,
             stats.discardPackets, stats.discardSegments, stats.lastHeader[0], stats.lastHeader[1], stats.lastHeader[2],
             stats.lastHeader[3],
             (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getFreePsram(), WiFi.softAPgetStationNum(),
             (unsigned)server.mjpegClientCount(), (unsigned)server.rawClientCount());
    lastFrames = stats.framesCaptured;
    vTaskDelay(pdMS_TO_TICKS(DIAG_INTERVAL_MS));
  }
}

void loop() {
  vTaskDelete(nullptr);  // all work happens in the capture, stream, http and diag tasks
}
