import { readOffline } from "../../../lib/offlineStore";
export const runtime = "nodejs";
export async function GET() {
  const saved = await readOffline("mission.json");
  return saved
    ? new Response(new Uint8Array(saved), {
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store",
        },
      })
    : Response.json(null);
}
