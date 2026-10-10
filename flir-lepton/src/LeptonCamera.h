#pragma once

#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>
#include <atomic>

#include "config.h"
#include "lepton.h"

// Metadata attached to every complete frame. frameId is the capture sequence number (starts at 1),
// timestampMs is millis() when the last segment arrived.
struct FrameInfo {
  uint32_t frameId = 0;
  uint32_t timestampMs = 0;
};

// Owns the Lepton: bring-up, VoSPI capture on a dedicated high-priority task, recovery, and a
// triple buffer that hands complete frames to a single consumer without ever blocking capture.
class LeptonCamera {
public:
  enum class State : uint8_t {
    Off,          // begin() not called
    Booting,      // reset released, waiting for the camera to report ready
    Configuring,  // sending VSYNC / video mode / format commands
    Streaming,    // reading VoSPI
    Error,        // init failed, retrying after a delay
  };

  struct Stats {
    State state;
    bool initialized;      // camera has been configured at least once
    uint32_t framesCaptured;
    uint32_t framesInvalid;  // reads that aborted after data started arriving
    uint32_t resyncs;        // VoSPI 185 ms resyncs
    uint32_t outOfPhase;     // reads that began mid-frame (dropped quietly)
    uint32_t resets;         // hardware resets after the camera stalled
    uint32_t vsyncTimeouts;  // waits for VSYNC that fell back to polling
    uint32_t packets;        // VoSPI packet headers read
    uint32_t discardPackets; // of which discard packets
    uint32_t discardSegments;
    uint8_t lastHeader[4];   // most recent packet header
    float fps;
  };

  LeptonCamera();

  // Starts the buses, allocates the frame buffers and launches the capture task.
  bool begin();

  // Single consumer only: if a frame newer than the last one acquired is ready, swaps it in and
  // returns true. The returned pointer holds FRAME_BYTES of big-endian 16-bit pixels and stays
  // valid until the next successful acquireLatest().
  bool acquireLatest(const uint8_t** frame, FrameInfo* info);

  uint32_t latestFrameId() const { return latestFrameId_.load(); }
  Stats getStats();

  const char* getPartNumber() { return lepton_.getFlirPartNum(); }
  uint64_t getSerial() { return lepton_.getFlirSerial(); }

  static const char* stateName(State state);

private:
  static void taskEntry(void* arg);
  static void IRAM_ATTR onVsync(void* arg);
  void captureLoop();
  bool bringUp();
  void publishFrame();
  void updateFps(uint32_t nowMs);

  SPIClass spi_;
  FlirLepton lepton_;
  TaskHandle_t task_ = nullptr;

  // Triple buffer: capture writes back_, latest_ holds the newest complete frame, the consumer
  // reads read_. Indices are swapped under lock_; latestFresh_ means latest_ hasn't been taken yet.
  uint8_t* buffers_[3] = {nullptr, nullptr, nullptr};
  uint8_t back_ = 0, latest_ = 1, read_ = 2;
  bool latestFresh_ = false;
  FrameInfo latestInfo_;
  portMUX_TYPE lock_ = portMUX_INITIALIZER_UNLOCKED;

  std::atomic<State> state_{State::Off};
  std::atomic<bool> initialized_{false};
  std::atomic<uint32_t> latestFrameId_{0};
  std::atomic<uint32_t> framesInvalid_{0};
  std::atomic<uint32_t> resets_{0};
  std::atomic<uint32_t> vsyncTimeouts_{0};
  std::atomic<uint32_t> resyncs_{0};
  std::atomic<uint32_t> outOfPhase_{0};
  std::atomic<uint32_t> packets_{0};
  std::atomic<uint32_t> discardPackets_{0};
  std::atomic<uint32_t> discardSegments_{0};
  std::atomic<uint32_t> lastHeader_{0};

  // FPS over a sliding window of frame completion times
  static constexpr size_t FPS_WINDOW = 32;
  uint32_t frameTimes_[FPS_WINDOW] = {0};
  size_t frameTimeHead_ = 0;
  size_t frameTimeCount_ = 0;
  std::atomic<float> fps_{0.0f};
};
