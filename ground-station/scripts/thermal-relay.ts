import { createServer } from "node:http";
import { pathToFileURL } from "node:url";
import { Server } from "socket.io";
import {
  thermalFrame,
  thermalDetections,
} from "../src/lib/thermalTransport.ts";

/** Local relay; never rebroadcast arbitrary Socket.IO events. */
export function createThermalRelay(
  options: {
    origins?: string[];
    namespace?: string;
    frameEvent?: string;
    detectionEvent?: string;
  } = {},
) {
  const origins = options.origins ?? [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
  ];
  const http = createServer((req, res) => {
    res.writeHead(req.url === "/health" ? 200 : 404, {
      "Content-Type": "application/json",
    });
    res.end(JSON.stringify({ service: "vigil-thermal-relay" }));
  });
  const io = new Server(http, {
    serveClient: false,
    maxHttpBufferSize: 1_100_000,
    cors: { origin: origins },
    allowRequest: (req, done) =>
      done(null, !req.headers.origin || origins.includes(req.headers.origin)),
  });
  const namespace = io.of(options.namespace ?? "/");
  const frameEvent = options.frameEvent ?? "vigil:frame";
  const detectionEvent = options.detectionEvent ?? "vigil:detection";
  let publisher: string | null = null;
  namespace.on("connection", (socket) => {
    const forward = (event: string, raw: unknown, valid: boolean) => {
      if (!valid || (publisher !== null && publisher !== socket.id)) return;
      publisher = socket.id;
      socket.broadcast.emit(event, raw);
    };
    socket.on(frameEvent, (raw: unknown) =>
      forward(frameEvent, raw, thermalFrame(raw) !== null),
    );
    socket.on(detectionEvent, (raw: unknown) =>
      forward(detectionEvent, raw, thermalDetections(raw) !== null),
    );
    socket.on("disconnect", () => {
      if (publisher === socket.id) publisher = null;
    });
  });
  return { http, io };
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  const port = Number(process.env.THERMAL_RELAY_PORT || 5000);
  if (!Number.isInteger(port) || port < 1 || port > 65535)
    throw new Error("Invalid thermal relay port");
  const host = process.env.THERMAL_RELAY_HOST || "127.0.0.1";
  const relay = createThermalRelay({
    origins: process.env.THERMAL_RELAY_ORIGINS?.split(",").map((value) =>
      value.trim(),
    ),
    namespace: process.env.NEXT_PUBLIC_THERMAL_SOCKET_NAMESPACE,
    frameEvent: process.env.NEXT_PUBLIC_THERMAL_FRAME_EVENT,
    detectionEvent: process.env.NEXT_PUBLIC_THERMAL_DETECTION_EVENT,
  });
  relay.http.on("error", (error) => {
    console.error(error.message);
    process.exitCode = 1;
    relay.io.close();
  });
  relay.http.listen(port, host, () =>
    console.log(`Thermal relay listening on http://${host}:${port}`),
  );
  for (const signal of ["SIGINT", "SIGTERM"] as const)
    process.on(signal, () => relay.io.close(() => process.exit(0)));
}
