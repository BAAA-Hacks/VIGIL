#include "StreamServer.h"

#include <esp_heap_caps.h>
#include <lwip/sockets.h>

#include "WebPage.h"

static const char* TAG = "server";

static const char MJPEG_RESPONSE_HEADER[] =
    "HTTP/1.1 200 OK\r\n"
    "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
    "Cache-Control: no-store\r\n"
    "Access-Control-Allow-Origin: *\r\n"
    "Connection: close\r\n\r\n";

static const char RAW_RESPONSE_HEADER[] =
    "HTTP/1.1 200 OK\r\n"
    "Content-Type: application/octet-stream\r\n"
    "Cache-Control: no-store\r\n"
    "Access-Control-Allow-Origin: *\r\n"
    "X-Record-Format: LEP1\r\n"
    "Connection: close\r\n\r\n";

static void* allocPreferPsram(size_t bytes) {
  void* buffer = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  return buffer ? buffer : heap_caps_malloc(bytes, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
}

// Sends everything or fails within timeoutMs. WiFiClient::write can retry for ~10 s on a stalled
// socket, so this uses non-blocking sends with an overall deadline instead.
static bool sendAll(WiFiClient& client, const void* data, size_t length, uint32_t timeoutMs) {
  int fd = client.fd();
  if (fd < 0) {
    return false;
  }
  const uint8_t* cursor = static_cast<const uint8_t*>(data);
  uint32_t startMs = millis();
  while (length > 0) {
    int sent = send(fd, cursor, length, MSG_DONTWAIT);
    if (sent > 0) {
      cursor += sent;
      length -= sent;
      continue;
    }
    if (sent < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
      return false;
    }
    uint32_t elapsedMs = millis() - startMs;
    if (elapsedMs >= timeoutMs) {
      return false;
    }
    fd_set writeSet;
    FD_ZERO(&writeSet);
    FD_SET(fd, &writeSet);
    uint32_t waitMs = min<uint32_t>(timeoutMs - elapsedMs, 50);
    timeval timeout = {0, (suseconds_t)(waitMs * 1000)};
    select(fd + 1, nullptr, &writeSet, nullptr, &timeout);
  }
  return true;
}

static bool sendAll(WiFiClient& client, const char* text, uint32_t timeoutMs) {
  return sendAll(client, text, strlen(text), timeoutMs);
}

// True if the socket can accept data right now
static bool isWritable(WiFiClient& client) {
  int fd = client.fd();
  if (fd < 0) {
    return false;
  }
  fd_set writeSet;
  FD_ZERO(&writeSet);
  FD_SET(fd, &writeSet);
  timeval timeout = {0, 0};
  return select(fd + 1, nullptr, &writeSet, nullptr, &timeout) > 0;
}

static inline void putU16(uint8_t* out, uint16_t value) {
  out[0] = value & 0xff;
  out[1] = value >> 8;
}

static inline void putU32(uint8_t* out, uint32_t value) {
  for (int i = 0; i < 4; i++) {
    out[i] = (value >> (8 * i)) & 0xff;
  }
}

StreamServer::StreamServer(LeptonCamera& camera, ThermalProcessor& processor)
    : camera_(camera), processor_(processor), server_(HTTP_PORT) {}

bool StreamServer::begin() {
  jpegBuffer_ = static_cast<uint8_t*>(allocPreferPsram(JPEG_BUFFER_SIZE));
  rawRecord_ = static_cast<uint8_t*>(allocPreferPsram(RAW_RECORD_BYTES));
  clientsMutex_ = xSemaphoreCreateMutex();
  if (jpegBuffer_ == nullptr || rawRecord_ == nullptr || clientsMutex_ == nullptr) {
    ESP_LOGE(TAG, "stream buffer allocation failed");
    return false;
  }

  WiFi.persistent(false);
  WiFi.mode(WIFI_AP);
  if (!WiFi.softAPConfig(AP_IP, AP_IP, AP_NETMASK)) {
    ESP_LOGE(TAG, "softAPConfig failed");
    return false;
  }
  if (!WiFi.softAP(AP_SSID, AP_PASSWORD, AP_CHANNEL, 0, AP_MAX_STATIONS)) {
    ESP_LOGE(TAG, "softAP failed");
    return false;
  }
  WiFi.setSleep(false);
  ESP_LOGI(TAG, "AP '%s' up at %s", AP_SSID, WiFi.softAPIP().toString().c_str());

  server_.enableCORS(true);
  server_.on("/", HTTP_GET, [this]() { handleRoot(); });
  server_.on("/stream", HTTP_GET, [this]() { handleStream(); });
  server_.on("/raw", HTTP_GET, [this]() { handleRaw(); });
  server_.on("/capture", HTTP_GET, [this]() { handleCapture(); });
  server_.on("/status", HTTP_GET, [this]() { handleStatus(); });
  server_.on("/settings", HTTP_GET, [this]() { handleSettings(); });
  server_.onNotFound([this]() { handleNotFound(); });
  server_.begin();

  if (xTaskCreatePinnedToCore(streamTaskEntry, "stream", STREAM_STACK, this, STREAM_PRIORITY, &streamTask_,
                              NET_CORE) != pdPASS ||
      xTaskCreatePinnedToCore(httpTaskEntry, "http", HTTP_STACK, this, HTTP_PRIORITY, nullptr, NET_CORE) !=
          pdPASS) {
    ESP_LOGE(TAG, "server task creation failed");
    return false;
  }
  ESP_LOGI(TAG, "HTTP server on port %u", HTTP_PORT);
  return true;
}

void StreamServer::httpTaskEntry(void* arg) {
  static_cast<StreamServer*>(arg)->httpLoop();
}

void StreamServer::streamTaskEntry(void* arg) {
  static_cast<StreamServer*>(arg)->streamLoop();
}

void StreamServer::httpLoop() {
  while (true) {
    server_.handleClient();
    vTaskDelay(1);
  }
}

/* HTTP handlers (http task) */

void StreamServer::handleRoot() {
  server_.send_P(200, "text/html", WEB_PAGE);
}

bool StreamServer::registerClient(Client* clients, size_t count, const WiFiClient& socket) {
  bool registered = false;
  xSemaphoreTake(clientsMutex_, portMAX_DELAY);
  for (size_t i = 0; i < count; i++) {
    if (!clients[i].active) {
      clients[i].socket = socket;
      clients[i].active = true;
      clients[i].lastFrameId = 0;
      clients[i].lastSendMs = millis();
      registered = true;
      break;
    }
  }
  xSemaphoreGive(clientsMutex_);
  if (registered) {
    xTaskNotifyGive(streamTask_);  // serve the current frame right away
  }
  return registered;
}

size_t StreamServer::countActive(const Client* clients, size_t count) {
  size_t active = 0;
  for (size_t i = 0; i < count; i++) {
    active += clients[i].active ? 1 : 0;
  }
  return active;
}

size_t StreamServer::mjpegClientCount() {
  xSemaphoreTake(clientsMutex_, portMAX_DELAY);
  size_t count = countActive(mjpegClients_, MAX_MJPEG_CLIENTS);
  xSemaphoreGive(clientsMutex_);
  return count;
}

size_t StreamServer::rawClientCount() {
  xSemaphoreTake(clientsMutex_, portMAX_DELAY);
  size_t count = countActive(rawClients_, MAX_RAW_CLIENTS);
  xSemaphoreGive(clientsMutex_);
  return count;
}

void StreamServer::handleStream() {
  WiFiClient socket = server_.client();
  // Check for a free slot first so a refused client still gets a proper HTTP error.
  if (mjpegClientCount() >= MAX_MJPEG_CLIENTS) {
    server_.send(503, "text/plain", "Too many stream clients\n");
    return;
  }
  socket.setNoDelay(true);
  if (!sendAll(socket, MJPEG_RESPONSE_HEADER, CLIENT_WRITE_TIMEOUT_MS)) {
    return;
  }
  // Only the stream task writes to the socket from here on.
  if (registerClient(mjpegClients_, MAX_MJPEG_CLIENTS, socket)) {
    ESP_LOGI(TAG, "MJPEG client %s connected", socket.remoteIP().toString().c_str());
  } else {
    socket.stop();
  }
}

void StreamServer::handleRaw() {
  WiFiClient socket = server_.client();
  if (rawClientCount() >= MAX_RAW_CLIENTS) {
    server_.send(503, "text/plain", "Too many raw clients\n");
    return;
  }
  socket.setNoDelay(true);
  if (!sendAll(socket, RAW_RESPONSE_HEADER, CLIENT_WRITE_TIMEOUT_MS)) {
    return;
  }
  if (registerClient(rawClients_, MAX_RAW_CLIENTS, socket)) {
    ESP_LOGI(TAG, "raw client %s connected", socket.remoteIP().toString().c_str());
  } else {
    socket.stop();
  }
}

void StreamServer::handleCapture() {
  if (camera_.latestFrameId() == 0) {
    server_.send(503, "text/plain", "No frame captured yet\n");
    return;
  }
  // The stream task answers with the latest complete frame, encoded with the current settings.
  if (!registerClient(captureClients_, MAX_CAPTURE_CLIENTS, server_.client())) {
    server_.send(503, "text/plain", "Busy, retry\n");
  }
}

void StreamServer::handleStatus() {
  LeptonCamera::Stats stats = camera_.getStats();
  char json[512];
  snprintf(json, sizeof(json),
           "{\"cameraInit\":%s,\"cameraState\":\"%s\",\"framesCaptured\":%u,\"framesInvalid\":%u,"
           "\"resyncs\":%u,\"outOfPhase\":%u,\"resets\":%u,\"fps\":%.2f,\"freeHeap\":%u,\"freePsram\":%u,"
           "\"streamClients\":%u,\"rawClients\":%u,\"apIp\":\"%s\",\"uptimeMs\":%u}",
           stats.initialized ? "true" : "false", LeptonCamera::stateName(stats.state), stats.framesCaptured,
           stats.framesInvalid, stats.resyncs, stats.outOfPhase, stats.resets, stats.fps,
           (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getFreePsram(), (unsigned)mjpegClientCount(),
           (unsigned)rawClientCount(), WiFi.softAPIP().toString().c_str(), (unsigned)millis());
  server_.sendHeader("Cache-Control", "no-store");
  server_.send(200, "application/json", json);
}

ImageSettings StreamServer::getSettings(uint32_t* versionOut) {
  portENTER_CRITICAL(&settingsLock_);
  ImageSettings settings = settings_;
  if (versionOut) {
    *versionOut = settingsVersion_;
  }
  portEXIT_CRITICAL(&settingsLock_);
  return settings;
}

void StreamServer::sendSettingsJson() {
  ImageSettings settings = getSettings(nullptr);
  char json[128];
  snprintf(json, sizeof(json), "{\"palette\":\"%s\",\"rotation\":%u,\"mirror\":%s}",
           ThermalProcessor::paletteName(settings.palette), settings.rotation, settings.mirror ? "true" : "false");
  server_.sendHeader("Cache-Control", "no-store");
  server_.send(200, "application/json", json);
}

void StreamServer::handleSettings() {
  ImageSettings updated = getSettings(nullptr);
  if (server_.hasArg("palette") && !ThermalProcessor::parsePalette(server_.arg("palette"), &updated.palette)) {
    server_.send(400, "text/plain", "palette must be gray, iron or rainbow\n");
    return;
  }
  if (server_.hasArg("rotation")) {
    long rotation = server_.arg("rotation").toInt();
    if (rotation != 0 && rotation != 90 && rotation != 180 && rotation != 270) {
      server_.send(400, "text/plain", "rotation must be 0, 90, 180 or 270\n");
      return;
    }
    updated.rotation = rotation;
  }
  if (server_.hasArg("mirror")) {
    String mirror = server_.arg("mirror");
    updated.mirror = mirror == "1" || mirror == "true";
  }

  portENTER_CRITICAL(&settingsLock_);
  settings_ = updated;
  settingsVersion_++;
  portEXIT_CRITICAL(&settingsLock_);
  sendSettingsJson();
}

void StreamServer::handleNotFound() {
  server_.send(404, "text/plain", "Not found. Endpoints: / /stream /raw /capture /status /settings\n");
}

/* Stream task: owns all registered client sockets */

void StreamServer::streamLoop() {
  const uint8_t* rawFrame = nullptr;
  FrameInfo info;
  while (true) {
    // Woken by new clients; otherwise poll for frames (they arrive every ~115 ms).
    ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(5));
    camera_.acquireLatest(&rawFrame, &info);
    if (rawFrame == nullptr) {
      continue;
    }

    uint32_t nowMs = millis();
    xSemaphoreTake(clientsMutex_, portMAX_DELAY);
    bool needJpeg = false;
    for (auto& client : mjpegClients_) {
      needJpeg |= client.active && client.lastFrameId != info.frameId;
    }
    for (auto& client : captureClients_) {
      needJpeg |= client.active;
    }

    if (needJpeg) {
      uint32_t settingsVersion;
      ImageSettings settings = getSettings(&settingsVersion);
      if (jpegFrameId_ != info.frameId || jpegSettingsVersion_ != settingsVersion) {
        if (encodeJpeg(rawFrame, settings)) {
          jpegFrameId_ = info.frameId;
          jpegSettingsVersion_ = settingsVersion;
        } else {
          jpegLength_ = 0;
        }
      }
      if (jpegLength_ > 0) {
        serveMjpeg(info, nowMs);
        serveCaptures(info);
      }
    }
    serveRaw(rawFrame, info, nowMs);
    xSemaphoreGive(clientsMutex_);
  }
}

bool StreamServer::encodeJpeg(const uint8_t* rawFrame, const ImageSettings& settings) {
  ThermalProcessor::Image image = processor_.process(rawFrame, settings);
  bool color = image.bytesPerPixel == 3;

  JPEGENCODE encoder;
  int rc = jpegEncoder_.open(jpegBuffer_, JPEG_BUFFER_SIZE);
  if (rc == JPEGE_SUCCESS) {
    rc = jpegEncoder_.encodeBegin(&encoder, image.width, image.height,
                                  color ? JPEGE_PIXEL_RGB888 : JPEGE_PIXEL_GRAYSCALE,
                                  color ? JPEGE_SUBSAMPLE_420 : JPEGE_SUBSAMPLE_444, JPEGE_Q_HIGH);
  }
  if (rc == JPEGE_SUCCESS) {
    rc = jpegEncoder_.addFrame(&encoder, const_cast<uint8_t*>(image.pixels), image.width * image.bytesPerPixel);
  }
  if (rc != JPEGE_SUCCESS) {
    ESP_LOGE(TAG, "JPEG encode failed: %d", rc);
    jpegEncoder_.close();
    return false;
  }
  jpegLength_ = jpegEncoder_.close();
  return jpegLength_ > 0;
}

void StreamServer::dropClient(Client& client, const char* kind) {
  ESP_LOGI(TAG, "%s client disconnected", kind);
  client.socket.stop();
  client.socket = WiFiClient();
  client.active = false;
}

void StreamServer::serveMjpeg(const FrameInfo& info, uint32_t nowMs) {
  char partHeader[160];
  int partHeaderLength = snprintf(partHeader, sizeof(partHeader),
                                  "--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n"
                                  "X-Frame-Id: %u\r\nX-Timestamp-Ms: %u\r\n\r\n",
                                  (unsigned)jpegLength_, info.frameId, info.timestampMs);
  for (auto& client : mjpegClients_) {
    if (!client.active || client.lastFrameId == info.frameId) {
      continue;
    }
    if (!client.socket.connected()) {
      dropClient(client, "MJPEG");
      continue;
    }
    // A client that can't take data right now skips this frame instead of holding up the others.
    if (!isWritable(client.socket)) {
      if (nowMs - client.lastSendMs > CLIENT_STALL_DROP_MS) {
        dropClient(client, "MJPEG (stalled)");
      }
      continue;
    }
    // A partial part would corrupt the multipart stream, so any failure drops the client.
    if (!sendAll(client.socket, partHeader, partHeaderLength, CLIENT_WRITE_TIMEOUT_MS) ||
        !sendAll(client.socket, jpegBuffer_, jpegLength_, CLIENT_WRITE_TIMEOUT_MS) ||
        !sendAll(client.socket, "\r\n", 2, CLIENT_WRITE_TIMEOUT_MS)) {
      dropClient(client, "MJPEG");
      continue;
    }
    client.lastFrameId = info.frameId;
    client.lastSendMs = millis();
  }
}

void StreamServer::serveCaptures(const FrameInfo& info) {
  char header[320];
  int headerLength = snprintf(header, sizeof(header),
                              "HTTP/1.1 200 OK\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n"
                              "Content-Disposition: inline; filename=lepton-%u.jpg\r\n"
                              "Cache-Control: no-store\r\nAccess-Control-Allow-Origin: *\r\n"
                              "Access-Control-Expose-Headers: X-Frame-Id, X-Timestamp-Ms\r\n"
                              "X-Frame-Id: %u\r\nX-Timestamp-Ms: %u\r\nConnection: close\r\n\r\n",
                              (unsigned)jpegLength_, info.frameId, info.frameId, info.timestampMs);
  for (auto& client : captureClients_) {
    if (!client.active) {
      continue;
    }
    if (sendAll(client.socket, header, headerLength, CLIENT_WRITE_TIMEOUT_MS)) {
      sendAll(client.socket, jpegBuffer_, jpegLength_, CLIENT_WRITE_TIMEOUT_MS);
    }
    client.socket.stop();
    client.socket = WiFiClient();
    client.active = false;
  }
}

void StreamServer::serveRaw(const uint8_t* rawFrame, const FrameInfo& info, uint32_t nowMs) {
  bool anyPending = false;
  for (auto& client : rawClients_) {
    anyPending |= client.active && client.lastFrameId != info.frameId;
  }
  if (!anyPending) {
    return;
  }

  if (rawRecordFrameId_ != info.frameId) {
    // Header: "LEP1" | frameId | timestampMs | width | height | rawMin | rawMax | flags (all LE)
    uint16_t rawMin, rawMax;
    ThermalProcessor::findRange(rawFrame, &rawMin, &rawMax);
    memcpy(rawRecord_, "LEP1", 4);
    putU32(rawRecord_ + 4, info.frameId);
    putU32(rawRecord_ + 8, info.timestampMs);
    putU16(rawRecord_ + 12, FRAME_WIDTH);
    putU16(rawRecord_ + 14, FRAME_HEIGHT);
    putU16(rawRecord_ + 16, rawMin);
    putU16(rawRecord_ + 18, rawMax);
    putU32(rawRecord_ + 20, 1);  // bit0: TLinear enabled (values are kelvin * 100 at default resolution)
    // VoSPI words are big-endian; the record carries little-endian uint16.
    uint8_t* pixels = rawRecord_ + RAW_HEADER_BYTES;
    for (size_t i = 0; i < FRAME_PIXELS; i++) {
      pixels[2 * i] = rawFrame[2 * i + 1];
      pixels[2 * i + 1] = rawFrame[2 * i];
    }
    rawRecordFrameId_ = info.frameId;
  }

  for (auto& client : rawClients_) {
    if (!client.active || client.lastFrameId == info.frameId) {
      continue;
    }
    if (!client.socket.connected()) {
      dropClient(client, "raw");
      continue;
    }
    if (!isWritable(client.socket)) {
      if (nowMs - client.lastSendMs > CLIENT_STALL_DROP_MS) {
        dropClient(client, "raw (stalled)");
      }
      continue;
    }
    if (!sendAll(client.socket, rawRecord_, RAW_RECORD_BYTES, CLIENT_WRITE_TIMEOUT_MS)) {
      dropClient(client, "raw");
      continue;
    }
    client.lastFrameId = info.frameId;
    client.lastSendMs = millis();
  }
}
