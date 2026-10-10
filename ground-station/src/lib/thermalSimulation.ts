import type { ThermalPalette } from "../types/vigil";
const WIDTH = 320;
const HEIGHT = 240;
function isPersonPixel(x: number, y: number): boolean {
  const head = ((x - 158) / 9) ** 2 + ((y - 81) / 12) ** 2 < 1;
  const body = ((x - 158) / 14) ** 2 + ((y - 119) / 27) ** 2 < 1;
  const legs =
    y > 133 &&
    y < 185 &&
    (Math.abs(x - (151 - (y - 133) * 0.09)) < 5 ||
      Math.abs(x - (164 + (y - 133) * 0.1)) < 5);
  const arms =
    y > 103 && y < 140 && (Math.abs(x - 139) < 4 || Math.abs(x - 177) < 4);
  return head || body || legs || arms;
}
function colorize(
  value: number,
  palette: ThermalPalette,
): [number, number, number] {
  if (palette === "white") return [value, value, value];
  const normalized = value / 255;
  return [
    Math.min(255, normalized * 510),
    Math.max(0, (normalized - 0.32) * 375),
    Math.max(0, 110 - normalized * 170),
  ];
}
export function drawThermalScene(
  canvas: HTMLCanvasElement,
  palette: ThermalPalette,
  hasPerson: boolean,
): void {
  const context = canvas.getContext("2d");
  if (!context) return;
  const pixels = context.createImageData(WIDTH, HEIGHT);
  // A fixed seed keeps the demo scene reproducible across renders.
  let seed = 42;
  const random = () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  for (let y = 0; y < HEIGHT; y++) {
    for (let x = 0; x < WIDTH; x++) {
      let value =
        25 + 16 * Math.sin(x / 28) + 12 * Math.cos(y / 21) + random() * 22;
      if (y > 158) value += 15;
      if ((x > 18 && x < 75 && y < 174) || (x > 238 && x < 277 && y < 142))
        value -= 16;
      if (hasPerson && isPersonPixel(x, y)) value = 210 + random() * 40;
      value = Math.max(0, Math.min(255, value));
      const [red, green, blue] = colorize(value, palette);
      const i = (y * WIDTH + x) * 4;
      pixels.data[i] = red;
      pixels.data[i + 1] = green;
      pixels.data[i + 2] = blue;
      pixels.data[i + 3] = 255;
    }
  }
  context.putImageData(pixels, 0, 0);
}
