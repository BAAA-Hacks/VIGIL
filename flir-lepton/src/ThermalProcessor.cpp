#include "ThermalProcessor.h"

#include <esp_heap_caps.h>

static const char* TAG = "processor";

static inline uint16_t rawPixel(const uint8_t* rawFrame, size_t index) {
  return ((uint16_t)rawFrame[2 * index] << 8) | rawFrame[2 * index + 1];
}

// JPEGENC reads whole 16x16 MCUs, so pad past the last row (120 isn't a multiple of 16).
static constexpr size_t OUTPUT_BYTES = (FRAME_PIXELS + 16 * FRAME_WIDTH) * 3;

bool ThermalProcessor::begin() {
  output_ = static_cast<uint8_t*>(heap_caps_calloc(1, OUTPUT_BYTES, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (output_ == nullptr) {
    output_ = static_cast<uint8_t*>(heap_caps_calloc(1, OUTPUT_BYTES, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
  }
  if (output_ == nullptr) {
    ESP_LOGE(TAG, "output buffer allocation failed");
    return false;
  }
  buildLuts();
  return true;
}

// Linear interpolation between RGB control points, stored as BGR
static void buildGradient(uint8_t lut[256][3], const uint8_t stops[][3], size_t stopCount) {
  for (int i = 0; i < 256; i++) {
    float position = i * (stopCount - 1) / 255.0f;
    size_t low = (size_t)position;
    if (low >= stopCount - 1) {
      low = stopCount - 2;
    }
    float fraction = position - low;
    for (int channel = 0; channel < 3; channel++) {
      float value = stops[low][channel] + (stops[low + 1][channel] - stops[low][channel]) * fraction;
      lut[i][2 - channel] = (uint8_t)(value + 0.5f);
    }
  }
}

void ThermalProcessor::buildLuts() {
  static const uint8_t IRON_STOPS[][3] = {
      {0, 0, 0}, {32, 0, 96}, {112, 0, 150}, {180, 30, 120}, {225, 75, 40},
      {245, 135, 0}, {255, 195, 30}, {255, 240, 150}, {255, 255, 255},
  };
  static const uint8_t RAINBOW_STOPS[][3] = {
      {0, 0, 128}, {0, 0, 255}, {0, 160, 255}, {0, 255, 160}, {120, 255, 0},
      {255, 230, 0}, {255, 120, 0}, {255, 0, 0}, {255, 255, 255},
  };
  buildGradient(ironLut_, IRON_STOPS, sizeof(IRON_STOPS) / sizeof(IRON_STOPS[0]));
  buildGradient(rainbowLut_, RAINBOW_STOPS, sizeof(RAINBOW_STOPS) / sizeof(RAINBOW_STOPS[0]));
}

void ThermalProcessor::findRange(const uint8_t* rawFrame, uint16_t* minOut, uint16_t* maxOut) {
  uint16_t minValue = 0xffff, maxValue = 0;
  for (size_t i = 0; i < FRAME_PIXELS; i++) {
    uint16_t value = rawPixel(rawFrame, i);
    if (value < minValue) minValue = value;
    if (value > maxValue) maxValue = value;
  }
  *minOut = minValue;
  *maxOut = maxValue;
}

ThermalProcessor::Image ThermalProcessor::process(const uint8_t* rawFrame, const ImageSettings& settings) {
  Image image;
  findRange(rawFrame, &image.rawMin, &image.rawMax);

  bool swapAxes = settings.rotation == 90 || settings.rotation == 270;
  image.width = swapAxes ? FRAME_HEIGHT : FRAME_WIDTH;
  image.height = swapAxes ? FRAME_WIDTH : FRAME_HEIGHT;
  image.pixels = output_;

  const uint8_t(*lut)[3] = nullptr;
  if (settings.palette == Palette::Iron) {
    lut = ironLut_;
  } else if (settings.palette == Palette::Rainbow) {
    lut = rainbowLut_;
  }
  image.bytesPerPixel = lut ? 3 : 1;

  // Linear stretch so rawMin -> 0 and rawMax -> 255; a flat frame maps to black.
  uint32_t range = image.rawMax - image.rawMin;

  for (int sy = 0; sy < FRAME_HEIGHT; sy++) {
    for (int sx = 0; sx < FRAME_WIDTH; sx++) {
      int x = settings.mirror ? FRAME_WIDTH - 1 - sx : sx;
      int dx, dy;
      switch (settings.rotation) {
        case 90: dx = FRAME_HEIGHT - 1 - sy; dy = x; break;
        case 180: dx = FRAME_WIDTH - 1 - x; dy = FRAME_HEIGHT - 1 - sy; break;
        case 270: dx = sy; dy = FRAME_WIDTH - 1 - x; break;
        default: dx = x; dy = sy; break;
      }
      uint32_t value = rawPixel(rawFrame, sy * FRAME_WIDTH + sx) - image.rawMin;
      uint8_t level = range ? (uint8_t)(value * 255 / range) : 0;
      size_t outIndex = (size_t)dy * image.width + dx;
      if (lut) {
        uint8_t* out = output_ + outIndex * 3;
        out[0] = lut[level][0];
        out[1] = lut[level][1];
        out[2] = lut[level][2];
      } else {
        output_[outIndex] = level;
      }
    }
  }
  return image;
}

const char* ThermalProcessor::paletteName(Palette palette) {
  switch (palette) {
    case Palette::Iron: return "iron";
    case Palette::Rainbow: return "rainbow";
    default: return "gray";
  }
}

bool ThermalProcessor::parsePalette(const String& name, Palette* paletteOut) {
  if (name == "gray" || name == "grey") {
    *paletteOut = Palette::Gray;
  } else if (name == "iron") {
    *paletteOut = Palette::Iron;
  } else if (name == "rainbow") {
    *paletteOut = Palette::Rainbow;
  } else {
    return false;
  }
  return true;
}
