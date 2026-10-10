// Committed demo fixture. next.config.mjs swaps in a local dummy-data.json when present.
import data from "./dummy-data.example.json" with { type: "json" };
export default data;
