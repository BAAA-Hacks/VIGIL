import { spawn } from "node:child_process";
import path from "node:path";
import { isPathMission, type PathMission } from "../../../lib/missionPath";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
let uploading = false;

function connectionArgs(): string[] | null {
  if (process.env.INAV_MSP_SERIAL_PORT)
    return [
      "--serial",
      process.env.INAV_MSP_SERIAL_PORT,
      "--baud",
      process.env.INAV_MSP_BAUD || "115200",
    ];
  if (process.env.INAV_MSP_TCP_HOST && process.env.INAV_MSP_TCP_PORT)
    return [
      "--tcp-host",
      process.env.INAV_MSP_TCP_HOST,
      "--tcp-port",
      process.env.INAV_MSP_TCP_PORT,
    ];
  return null;
}

export function GET() {
  return Response.json({ configured: connectionArgs() !== null, uploading });
}

function upload(mission: PathMission, args: string[], signal: AbortSignal) {
  return new Promise<{ verified: boolean; waypoints?: number; error?: string }>(
    (resolve, reject) => {
      const child = spawn(
        /* turbopackIgnore: true */ process.env.PYTHON_EXECUTABLE || "python",
        [path.join(process.cwd(), "scripts/inav_mission.py"), ...args],
        { windowsHide: true, stdio: ["pipe", "pipe", "pipe"] },
      );
      let stdout = "",
        stderr = "";
      const stop = () => {
        child.kill();
      };
      const timeout = setTimeout(stop, 120000);
      signal.addEventListener("abort", stop, { once: true });
      if (signal.aborted) stop();
      const cleanup = () => {
        clearTimeout(timeout);
        signal.removeEventListener("abort", stop);
      };
      child.stdout.on("data", (chunk) => {
        stdout += chunk.toString();
        if (stdout.length > 16384) stop();
      });
      child.stderr.on("data", (chunk) => {
        stderr = (stderr + chunk.toString()).slice(-4096);
      });
      child.stdin.on("error", () => {
        /* Close/error reports the failed upload. */
      });
      child.on("error", (error) => {
        cleanup();
        reject(error);
      });
      child.on("close", (code) => {
        cleanup();
        try {
          const result = JSON.parse(stdout);
          if (
            code !== 0 ||
            result.verified !== true ||
            result.waypoints !== mission.waypoints.length
          )
            reject(
              new Error(
                result.error ||
                  "Upload was not verified; do not start the mission",
              ),
            );
          else resolve(result);
        } catch (error) {
          reject(
            error instanceof SyntaxError
              ? new Error(
                  stderr || "Mission bridge stopped; upload is unverified",
                )
              : error,
          );
        }
      });
      child.stdin.end(JSON.stringify(mission));
    },
  );
}

export async function POST(request: Request) {
  if (
    request.headers.get("origin") !== new URL(request.url).origin ||
    !request.headers.get("content-type")?.startsWith("application/json")
  )
    return Response.json({ error: "Forbidden" }, { status: 403 });
  if (uploading)
    return Response.json(
      { error: "A mission upload is already in progress" },
      { status: 409 },
    );
  const args = connectionArgs();
  if (!args)
    return Response.json(
      {
        error:
          "Configure a dedicated INAV MSP connection. The ELRS telemetry mirror cannot upload missions.",
      },
      { status: 503 },
    );
  let value;
  try {
    const raw = await request.text();
    if (raw.length > 32768) throw new Error();
    value = JSON.parse(raw);
  } catch {
    return Response.json({ error: "Invalid mission request" }, { status: 400 });
  }
  if (!isPathMission(value?.mission) || value.takeoverConfirmed !== true)
    return Response.json(
      {
        error:
          "Valid waypoints and a tested transmitter takeover switch are required",
      },
      { status: 400 },
    );
  // Check again after reading the body: two requests can otherwise acquire the link.
  if (uploading)
    return Response.json(
      { error: "A mission upload is already in progress" },
      { status: 409 },
    );
  uploading = true;
  try {
    return Response.json(await upload(value.mission, args, request.signal));
  } catch (error) {
    return Response.json(
      {
        verified: false,
        error: error instanceof Error ? error.message : "Mission upload failed",
      },
      { status: 502 },
    );
  } finally {
    uploading = false;
  }
}
