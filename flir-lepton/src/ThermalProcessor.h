#pragma once

#include <Arduino.h>

#include "config.h"

enum class Palette : uint8_t { Gray, Iron, Rainbow };

struct ImageSettings {
  Palette palette = Palette::Gray;
  uint16_t rotation = 0;  // degrees clockwise: 0, 90, 180, 270
  bool mirror = false;    // horizontal flip, applied before rotation
};

// Turns raw 16-bit Lepton frames into 8-bit display images: per-frame min/max contrast stretch,
// optional false colour, rotation and mirroring. The output buffer is allocated once.
class ThermalProcessor {
public:
  struct Image {
    const uint8_t* pixels;  // grayscale, or BGR888 (JPEGENC's RGB888 byte order)
    int width;
    int height;
    int bytesPerPixel;  // 1 or 3
    uint16_t rawMin;
    uint16_t rawMax;
  };

  bool begin();
  Image process(const uint8_t* rawFrame, const ImageSettings& settings);

  // Min and max of a raw big-endian frame
  static void findRange(const uint8_t* rawFrame, uint16_t* minOut, uint16_t* maxOut);

  static const char* paletteName(Palette palette);
  static bool parsePalette(const String& name, Palette* paletteOut);

private:
  void buildLuts();

  uint8_t* output_ = nullptr;      // FRAME_PIXELS * 3 plus MCU padding
  uint8_t ironLut_[256][3];        // BGR
  uint8_t rainbowLut_[256][3];     // BGR
};
