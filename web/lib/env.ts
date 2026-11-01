import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

let loaded = false;

function applyFile(file: string): void {
  if (!existsSync(file)) return;
  for (const line of readFileSync(file, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
    const index = trimmed.indexOf("=");
    const key = trimmed.slice(0, index).trim();
    let value = trimmed.slice(index + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (process.env[key] === undefined) process.env[key] = value;
  }
}

/** Load the repo root `.env` and then `web/.env*`. Existing process values win. */
export function loadEnv(): void {
  if (loaded) return;
  loaded = true;
  const root = process.cwd();
  for (const file of [
    path.join(root, "..", ".env"),
    path.join(root, ".env"),
    path.join(root, ".env.local"),
  ]) {
    applyFile(file);
  }
}

export function resetEnvForTests(): void {
  loaded = false;
}
