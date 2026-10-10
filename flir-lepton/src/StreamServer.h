#pragma once

#include <Arduino.h>
#include <JPEGENC.h>
#include <WebServer.h>
#include <WiFi.h>

#include "LeptonCamera.h"
#include "ThermalProcessor.h"
#include "config.h"

// Wi-Fi AP plus HTTP endpoints. The WebServer task only parses requests and registers long-lived
// clients; a separate stream task owns every client socket, encodes JPEGs and sends frames, so a
// slow client can only delay its own frames, never capture.
class StreamServer {
public:
  StreamServer(LeptonCamera& camera, ThermalProcessor& processor);

  bool begin();

  size_t mjpegClientCount();
  size_t rawClientCount();
  IPAddress apIp() const { return WiFi.softAPIP(); }

private:
  struct Client {
    WiFiClient socket;
    bool active = false;
    uint32_t lastFrameId = 0;  // last frame sent to this client
    uint32_t lastSendMs = 0;   // last successful send, for stall detection
  };

  static void httpTaskEntry(void* arg);
  static void streamTaskEntry(void* arg);
  void httpLoop();
  void streamLoop();

  void handleRoot();
  void handleStream();
  void handleRaw();
  void handleCapture();
  void handleStatus();
  void handleSettings();
  void handleNotFound();

  bool registerClient(Client* clients, size_t count, const WiFiClient& socket);
  size_t countActive(const Client* clients, size_t count);
  void sendSettingsJson();

  bool encodeJpeg(const uint8_t* rawFrame, const ImageSettings& settings);
  void serveMjpeg(const FrameInfo& info, uint32_t nowMs);
  void serveCaptures(const FrameInfo& info);
  void serveRaw(const uint8_t* rawFrame, const FrameInfo& info, uint32_t nowMs);
  void dropClient(Client& client, const char* kind);

  ImageSettings getSettings(uint32_t* versionOut);

  LeptonCamera& camera_;
  ThermalProcessor& processor_;
  WebServer server_;
  TaskHandle_t streamTask_ = nullptr;

  // Client tables, guarded by clientsMutex_ (held by the stream task while sending)
  SemaphoreHandle_t clientsMutex_ = nullptr;
  Client mjpegClients_[MAX_MJPEG_CLIENTS];
  Client rawClients_[MAX_RAW_CLIENTS];
  Client captureClients_[MAX_CAPTURE_CLIENTS];

  // Display settings, guarded by settingsLock_
  portMUX_TYPE settingsLock_ = portMUX_INITIALIZER_UNLOCKED;
  ImageSettings settings_;
  uint32_t settingsVersion_ = 0;

  // Stream task state
  JPEGENC jpegEncoder_;
  uint8_t* jpegBuffer_ = nullptr;
  size_t jpegLength_ = 0;
  uint32_t jpegFrameId_ = 0;
  uint32_t jpegSettingsVersion_ = UINT32_MAX;
  uint8_t* rawRecord_ = nullptr;  // header + little-endian pixels
  uint32_t rawRecordFrameId_ = 0;
};
