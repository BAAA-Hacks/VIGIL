import {
  readOffline,
  writeOffline,
} from "../../../../../../../lib/offlineStore";

export const runtime = "nodejs";
const services = {
  topographic: "World_Topo_Map",
  satellite: "World_Imagery",
  street: "World_Street_Map",
} as const;
export async function GET(
  _request: Request,
  context: {
    params: Promise<{ layer: string; z: string; x: string; y: string }>;
  },
) {
  const { layer, z: zs, x: xs, y: ys } = await context.params;
  const z = Number(zs),
    x = Number(xs),
    y = Number(ys);
  if (
    !Object.hasOwn(services, layer) ||
    ![z, x, y].every(Number.isInteger) ||
    z < 0 ||
    z > 19 ||
    x < 0 ||
    y < 0 ||
    x >= 2 ** z ||
    y >= 2 ** z
  )
    return new Response("Invalid tile", { status: 400 });
  const key = `tiles/${layer}/${z}/${x}/${y}`;
  const cached = await readOffline(key);
  let bytes: Uint8Array | null = cached;
  if (!bytes) {
    try {
      const response = await fetch(
        `https://server.arcgisonline.com/ArcGIS/rest/services/${services[layer as keyof typeof services]}/MapServer/tile/${z}/${y}/${x}`,
        { signal: AbortSignal.timeout(5000) },
      );
      if (
        !response.ok ||
        !response.headers.get("content-type")?.startsWith("image/")
      )
        throw new Error("Tile unavailable");
      bytes = new Uint8Array(await response.arrayBuffer());
      await writeOffline(key, bytes);
    } catch {
      return new Response("Tile not saved for offline use", {
        status: 503,
        headers: { "Cache-Control": "no-store" },
      });
    }
  }
  const png = bytes[0] === 137 && bytes[1] === 80;
  return new Response(new Uint8Array(bytes), {
    headers: {
      "Content-Type": png ? "image/png" : "image/jpeg",
      "Cache-Control": "public, max-age=31536000, immutable",
      "X-Vigil-Offline": cached ? "saved" : "downloaded",
    },
  });
}
