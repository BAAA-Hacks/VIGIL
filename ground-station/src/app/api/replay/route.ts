/** Replay control. Only ./replay.sh's fake camera answers /control; the real Lepton has no
 * such endpoint, so `available` is false during live use and the website hides the control. */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const control = () =>
  `http://127.0.0.1:${process.env.FAKE_CAMERA_PORT || 8090}/control`;

async function camera(init?: RequestInit) {
  try {
    const response = await fetch(control(), {
      ...init,
      signal: AbortSignal.timeout(500),
      cache: "no-store",
    });
    const state = await response.json();
    if (!response.ok || state?.replay !== true) return { available: false };
    return { available: true, paused: state.paused === true };
  } catch {
    return { available: false };
  }
}

export async function GET() {
  return Response.json(await camera());
}

export async function POST(request: Request) {
  // Same-site browser requests only. Compare with the Host header: in dev, request.url can name
  // a different hostname (localhost vs 127.0.0.1) than the page the browser loaded.
  const origin = request.headers.get("origin");
  let sameSite = false;
  try {
    sameSite =
      origin !== null && new URL(origin).host === request.headers.get("host");
  } catch {
    /* malformed Origin */
  }
  if (!sameSite) return Response.json({ error: "Forbidden" }, { status: 403 });
  let paused: unknown;
  try {
    paused = (await request.json())?.paused;
  } catch {
    /* handled below */
  }
  if (typeof paused !== "boolean")
    return Response.json(
      { error: "Expected { paused: boolean }" },
      { status: 400 },
    );
  const state = await camera({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paused }),
  });
  return Response.json(state, { status: state.available ? 200 : 503 });
}
