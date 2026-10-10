import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const root = path.join(process.cwd(), ".vigil-offline");
export async function readOffline(key: string): Promise<Buffer | null> {
  try {
    return await readFile(path.join(root, key));
  } catch {
    return null;
  }
}
export async function writeOffline(key: string, data: string | Uint8Array) {
  const file = path.join(root, key);
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, data);
}
