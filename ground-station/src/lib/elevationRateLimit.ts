import { createRequestGate } from "./requestGate";
// Keep one gate through development reloads, shared by every elevation request.
const shared = globalThis as typeof globalThis & {
  vigilElevationGate?: ReturnType<typeof createRequestGate>;
};
export const elevationRequestGate = (shared.vigilElevationGate ??=
  createRequestGate(5100));
