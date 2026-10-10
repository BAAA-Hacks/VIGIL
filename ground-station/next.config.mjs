import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.dirname(fileURLToPath(import.meta.url));
// A gitignored src/data/dummy-data.json overrides the committed example fixture.
const localFixture = existsSync(path.join(root, "src/data/dummy-data.json"));
export default {
  turbopack: {
    root,
    ...(localFixture && {
      resolveAlias: { "./dummy-data.example.json": "./src/data/dummy-data.json" },
    }),
  },
};
