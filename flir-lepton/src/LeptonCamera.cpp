#include "LeptonCamera.h"

#include <esp_heap_caps.h>

static const char* TAG = "camera";

LeptonCamera::LeptonCamera()
    : spi_(FSPI), lepton_(Wire, spi_, PIN_LEPTON_CS, PIN_LEPTON_RESET) {}

const char* LeptonCamera::stateName(State state) {
  switch (state) {
    case State::Off: return "off";
    case State::Booting: return "booting";
    case State::Configuring: return "configuring";
    case State::Streaming: return "streaming";
    case State::Error: return "error";
  }
  return "unknown";
}

bool LeptonCamera::begin() {
  // Raw frames stay in internal RAM: the capture loop writes them at SPI speed.
  for (auto& buffer : buffers_) {
    buffer = static_cast<uint8_t*>(heap_caps_calloc(1, FRAME_BYTES, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    if (buffer == nullptr) {
      ESP_LOGE(TAG, "frame buffer allocation failed");
      return false;
    }
  }

  spi_.begin(PIN_SPI_SCK, PIN_SPI_MISO, -1, -1);
  lepton_.setSpiClock(SPI_CLOCK_HZ);
  lepton_.setStartWait(SEGMENT_START_WAIT_US);
  pinMode(PIN_LEPTON_VSYNC, INPUT);

  if (xTaskCreatePinnedToCore(taskEntry, "capture", CAPTURE_STACK, this, CAPTURE_PRIORITY, &task_,
                              CAPTURE_CORE) != pdPASS) {
    ESP_LOGE(TAG, "capture task creation failed");
    return false;
  }
  if (USE_VSYNC) {
    attachInterruptArg(PIN_LEPTON_VSYNC, onVsync, this, RISING);
  }
  return true;
}

void IRAM_ATTR LeptonCamera::onVsync(void* arg) {
  auto* self = static_cast<LeptonCamera*>(arg);
  BaseType_t higherPriorityWoken = pdFALSE;
  vTaskNotifyGiveFromISR(self->task_, &higherPriorityWoken);
  if (higherPriorityWoken) {
    portYIELD_FROM_ISR();
  }
}

void LeptonCamera::taskEntry(void* arg) {
  static_cast<LeptonCamera*>(arg)->captureLoop();
}

bool LeptonCamera::bringUp() {
  state_ = State::Booting;
  ESP_LOGI(TAG, "resetting Lepton");
  lepton_.begin();

  uint32_t startMs = millis();
  while (!lepton_.isReady()) {
    if (millis() - startMs > CAMERA_READY_TIMEOUT_MS) {
      ESP_LOGE(TAG, "Lepton not ready after %u ms (check I2C wiring and breakout power)", CAMERA_READY_TIMEOUT_MS);
      return false;
    }
    vTaskDelay(pdMS_TO_TICKS(250));
  }
  ESP_LOGI(TAG, "Lepton ready after %u ms", (unsigned)(millis() - startMs));

  const uint8_t* version = lepton_.getFlirSoftwareVerison();
  ESP_LOGI(TAG, "serial %llu, part '%s', software %02x %02x %02x %02x %02x %02x", lepton_.getFlirSerial(),
           lepton_.getFlirPartNum(), version[0], version[1], version[2], version[3], version[4], version[5]);

  state_ = State::Configuring;
  if (USE_VSYNC && !lepton_.enableVsync()) {
    ESP_LOGE(TAG, "enabling VSYNC failed");
    return false;
  }
  // AGC off, TLinear on: 16-bit raw output, contrast is done in software.
  if (!lepton_.setVideoMode(FlirLepton::kTLinear)) {
    ESP_LOGE(TAG, "setting video mode failed");
    return false;
  }
  if (!lepton_.setVideoFormat(FlirLepton::kGrey14)) {
    ESP_LOGE(TAG, "setting video format failed");
    return false;
  }
  if (lepton_.getFrameWidth() != FRAME_WIDTH || lepton_.getFrameHeight() != FRAME_HEIGHT) {
    ESP_LOGE(TAG, "unexpected frame size %ux%u", lepton_.getFrameWidth(), lepton_.getFrameHeight());
    return false;
  }
  ESP_LOGI(TAG, "configured: Raw14/TLinear, VSYNC %s, SPI %u Hz", USE_VSYNC ? "on" : "off", SPI_CLOCK_HZ);
  return true;
}

void LeptonCamera::captureLoop() {
  while (true) {
    if (!bringUp()) {
      state_ = State::Error;
      vTaskDelay(pdMS_TO_TICKS(CAMERA_RETRY_DELAY_MS));
      continue;
    }
    initialized_ = true;
    state_ = State::Streaming;
    ulTaskNotifyTake(pdTRUE, 0);  // drop VSYNC pulses that arrived during configuration

    uint32_t lastFrameMs = millis();
    while (true) {
      if (USE_VSYNC && ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(VSYNC_WAIT_MS)) == 0) {
        vsyncTimeouts_++;
      }

      // Snapshot the driver's counters so expected early returns aren't counted as invalid frames
      FlirLepton::VoSpiStats before = lepton_.getVoSpiStats();
      bool written = false;
      bool complete = lepton_.readVoSpi(FRAME_BYTES, buffers_[back_], &written);
      const FlirLepton::VoSpiStats& voSpi = lepton_.getVoSpiStats();
      resyncs_ = voSpi.resyncs;
      outOfPhase_ = voSpi.outOfPhase;
      packets_ = voSpi.packets;
      discardPackets_ = voSpi.discardPackets;
      discardSegments_ = voSpi.discardSegments;
      lastHeader_ = ((uint32_t)voSpi.lastHeader[0] << 24) | ((uint32_t)voSpi.lastHeader[1] << 16) |
                    ((uint32_t)voSpi.lastHeader[2] << 8) | voSpi.lastHeader[3];

      uint32_t nowMs = millis();
      if (complete) {
        publishFrame();
        updateFps(nowMs);
        lastFrameMs = nowMs;
      } else if (written && voSpi.outOfPhase == before.outOfPhase &&
                 voSpi.discardSegments == before.discardSegments) {
        framesInvalid_++;
      }

      if (nowMs - lastFrameMs > CAMERA_NO_FRAME_RESET_MS) {
        ESP_LOGW(TAG, "no frame for %u ms, resetting camera", CAMERA_NO_FRAME_RESET_MS);
        resets_++;
        fps_ = 0.0f;
        break;
      }
      if (USE_VSYNC) {
        // Pulses that arrived during the read are stale; sleep until the next edge.
        ulTaskNotifyTake(pdTRUE, 0);
      } else {
        vTaskDelay(1);
      }
    }
  }
}

void LeptonCamera::publishFrame() {
  uint32_t frameId = latestFrameId_.load() + 1;
  portENTER_CRITICAL(&lock_);
  std::swap(back_, latest_);
  latestFresh_ = true;
  latestInfo_.frameId = frameId;
  latestInfo_.timestampMs = millis();
  portEXIT_CRITICAL(&lock_);
  latestFrameId_ = frameId;
}

bool LeptonCamera::acquireLatest(const uint8_t** frame, FrameInfo* info) {
  portENTER_CRITICAL(&lock_);
  if (!latestFresh_) {
    portEXIT_CRITICAL(&lock_);
    return false;
  }
  std::swap(read_, latest_);
  latestFresh_ = false;
  *info = latestInfo_;
  uint8_t readIndex = read_;
  portEXIT_CRITICAL(&lock_);
  *frame = buffers_[readIndex];
  return true;
}

void LeptonCamera::updateFps(uint32_t nowMs) {
  frameTimes_[frameTimeHead_] = nowMs;
  frameTimeHead_ = (frameTimeHead_ + 1) % FPS_WINDOW;
  if (frameTimeCount_ < FPS_WINDOW) {
    frameTimeCount_++;
  }
  // Average over the frames from the last ~2 s
  size_t used = 1;
  uint32_t oldest = nowMs;
  for (size_t i = 1; i < frameTimeCount_; i++) {
    uint32_t t = frameTimes_[(frameTimeHead_ + FPS_WINDOW - 1 - i) % FPS_WINDOW];
    if (nowMs - t > 2000) {
      break;
    }
    oldest = t;
    used++;
  }
  fps_ = (used > 1 && nowMs > oldest) ? (used - 1) * 1000.0f / (nowMs - oldest) : 0.0f;
}

LeptonCamera::Stats LeptonCamera::getStats() {
  Stats stats;
  stats.state = state_;
  stats.initialized = initialized_;
  stats.framesCaptured = latestFrameId_;
  stats.framesInvalid = framesInvalid_;
  stats.resyncs = resyncs_;
  stats.outOfPhase = outOfPhase_;
  stats.resets = resets_;
  stats.vsyncTimeouts = vsyncTimeouts_;
  stats.fps = fps_;
  stats.packets = packets_;
  stats.discardPackets = discardPackets_;
  stats.discardSegments = discardSegments_;
  uint32_t header = lastHeader_;
  for (int i = 0; i < 4; i++) {
    stats.lastHeader[i] = header >> (24 - 8 * i);
  }

  // Report 0 rather than a stale rate once frames stop arriving
  portENTER_CRITICAL(&lock_);
  uint32_t lastMs = latestInfo_.timestampMs;
  portEXIT_CRITICAL(&lock_);
  if (stats.framesCaptured == 0 || millis() - lastMs > 2000) {
    stats.fps = 0.0f;
  }
  return stats;
}
