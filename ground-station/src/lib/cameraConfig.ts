export const CAMERA_CONFIG = {
  model: "FLIR Lepton 3.5",
  widthPx: 160,
  heightPx: 120,
  // Manufacturer nominal FOVs; use calibrated intrinsics/distortion for projection.
  horizontalFovDeg: 57,
  diagonalFovDeg: 71,
  calibrationRequired: true,
  mountDownFromHorizontalDeg: 20,
  facing: "forward",
  fNumber: 1.1,
  altitudeReference: "home",
  headingReference: "relative-unresolved",
} as const;
