import { readFileSync } from "node:fs";
import path from "node:path";

import { photoFromApi } from "./photos";
import type { Photo } from "./types";

export function fixtureFile(): string {
  const candidates = [
    path.join(process.cwd(), "fixtures", "photos.json"),
    path.join(process.cwd(), "..", "fixtures", "photos.json"),
  ];
  for (const candidate of candidates) {
    try {
      readFileSync(candidate);
      return candidate;
    } catch {
      continue;
    }
  }
  throw new Error("fixtures/photos.json is not available. Fixture mode is for a local checkout.");
}

export function loadFixturePhotos(): Photo[] {
  const raw = JSON.parse(readFileSync(fixtureFile(), "utf8")) as Record<string, unknown>[];
  return raw.map((item) => photoFromApi(item));
}
