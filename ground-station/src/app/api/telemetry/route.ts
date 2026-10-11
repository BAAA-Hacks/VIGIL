import { spawn } from "node:child_process";
import path from "node:path";
import { createInterface } from "node:readline";
import { isVehicleTelemetry } from "../../../lib/vehicleTelemetry";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  const origin = request.headers.get("origin");
  if (origin && origin !== new URL(request.url).origin)
    return new Response("Forbidden", { status: 403 });
  const script = path.resolve(
    process.cwd(),
    "../flight-controller/ground/telemetry_bridge.py",
  );
  // TELEMETRY_SERIAL_PORT (the Pocket's USB serial device) selects live drone telemetry and
  // records the raw CRSF bytes; without it the bridge runs its synthetic mission.
  const port = process.env.TELEMETRY_SERIAL_PORT;
  const recording = path.resolve(
    path.dirname(script),
    "recordings",
    `flight_${new Date().toISOString().replace(/[:.]/g, "-")}.crsf`,
  );
  const source = port
    ? ["--port", port, "--record", recording]
    : ["--synthetic"];
  const encoder = new TextEncoder();
  let stop = () => {};
  const stream = new ReadableStream({
    start(controller) {
      const child = spawn(
        /* turbopackIgnore: true */
        process.env.PYTHON_EXECUTABLE || "python",
        [script, ...source, "--relative-yaw"],
        // stderr is inherited: an unread pipe would fill up and stall the bridge.
        {
          cwd: path.dirname(script),
          windowsHide: true,
          stdio: ["ignore", "pipe", "inherit"],
        },
      );
      const lines = createInterface({ input: child.stdout });
      let closed = false;
      // The stream may already be cancelled by the client; enqueue/close then throw.
      const write = (chunk: string) => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(chunk));
        } catch {
          stop();
        }
      };
      const send = (event: string, data: unknown) =>
        write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
      const heartbeat = setInterval(() => write(": keepalive\n\n"), 10000);
      stop = () => {
        if (closed) return;
        closed = true;
        clearInterval(heartbeat);
        lines.close();
        child.kill();
        request.signal.removeEventListener("abort", stop);
        try {
          controller.close();
        } catch {
          /* Already cancelled by the client. */
        }
      };
      lines.on("line", (line) => {
        try {
          const value: unknown = JSON.parse(line);
          if (isVehicleTelemetry(value)) send("telemetry", value);
        } catch {
          /* Ignore malformed lines; they never enter dashboard state. */
        }
      });
      child.on("error", () => {
        send("bridge-error", {
          error: "Could not start Python telemetry bridge.",
        });
        stop();
      });
      child.on("exit", () => {
        if (!closed) {
          send("bridge-error", { error: "Telemetry bridge stopped." });
          stop();
        }
      });
      request.signal.addEventListener("abort", stop, { once: true });
      if (request.signal.aborted) stop();
    },
    cancel() {
      stop();
    },
  });
  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
