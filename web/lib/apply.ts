import { emptyLocation } from "./photos";
import type { ApplyResult, Location, Photo, PhotoUpdate, ReviewRow } from "./types";

export type CollectionRecord = { id: string; title: string };

export type UnsplashWriter = {
  updatePhoto: (photoId: string, payload: PhotoUpdate) => Promise<void>;
  listCollections: () => Promise<CollectionRecord[]>;
  createCollection: (title: string, description: string) => Promise<CollectionRecord>;
  addPhoto: (collectionId: string, photoId: string) => Promise<void>;
};

function text(value: string | null | undefined): string {
  return (value || "").trim().toLowerCase();
}

function coordsEqual(left: number | null, right: number | null): boolean {
  if (left === null && right === null) return true;
  if (left === null || right === null) return false;
  return Math.abs(left - right) < 1e-5;
}

export function locationsEqual(left: Location | null, right: Location | null): boolean {
  if (!left || emptyLocation(left)) return !right || emptyLocation(right);
  if (!right || emptyLocation(right)) return false;
  if (text(left.name) !== text(right.name) || text(left.city) !== text(right.city) || text(left.country) !== text(right.country)) {
    return false;
  }
  return coordsEqual(left.latitude, right.latitude) && coordsEqual(left.longitude, right.longitude);
}

export function tagsEqual(left: string[], right: string[]): boolean {
  return left.map((tag) => tag.toLowerCase()).join("\0") === right.map((tag) => tag.toLowerCase()).join("\0");
}

export function updatePayload(photo: Photo, row: ReviewRow): PhotoUpdate {
  const payload: PhotoUpdate = {};
  if (row.location && !locationsEqual(photo.location, row.location)) {
    payload.location = {
      name: row.location.name,
      city: row.location.city,
      country: row.location.country,
      latitude: row.location.latitude,
      longitude: row.location.longitude,
    };
  }
  if (row.tags.length && !tagsEqual(photo.tags, row.tags)) payload.tags = row.tags;
  const description = row.description.trim();
  if (description && description !== (photo.description || "").trim()) payload.description = description;
  if (photo.showOnProfileKnown) {
    if (row.showOnProfile !== photo.showOnProfile) payload.showOnProfile = row.showOnProfile;
  } else if (row.showOnProfile === false) {
    payload.showOnProfile = false;
  }
  return payload;
}

export async function applyOne(
  photo: Photo,
  row: ReviewRow,
  known: Map<string, CollectionRecord>,
  writer: UnsplashWriter | null,
  mode: "live" | "fixture",
): Promise<{ result: ApplyResult; known: Map<string, CollectionRecord> }> {
  if (!row.include) {
    return { known, result: { photoId: photo.id, status: "skipped", operations: ["held"], error: "Not selected for apply.", mode } };
  }
  const payload = updatePayload(photo, row);
  const operations: string[] = [];
  if (Object.keys(payload).length) operations.push("update");
  const collectionOp = collectionOperation(photo, row, known);
  if (collectionOp) operations.push(collectionOp);
  if (operations.length === 0) {
    return { known, result: { photoId: photo.id, status: "skipped", operations: ["unchanged"], error: "", mode } };
  }
  if (writer === null) {
    if (collectionOp === "create_collection") {
      known.set(row.collectionTitle.trim().toLowerCase(), { id: "dry-run", title: row.collectionTitle.trim() });
    }
    return { known, result: { photoId: photo.id, status: "dry-run", operations, error: "", mode } };
  }
  try {
    if (Object.keys(payload).length) await writer.updatePhoto(photo.id, payload);
    if (collectionOp) {
      const collection = await ensureCollection(row, known, writer);
      const already = photo.collections.some((item) => item.title.toLowerCase() === collection.title.toLowerCase());
      if (!already) await writer.addPhoto(collection.id, photo.id);
    }
    return { known, result: { photoId: photo.id, status: "updated", operations, error: "", mode } };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unsplash rejected the update.";
    return { known, result: { photoId: photo.id, status: "failed", operations, error: message, mode } };
  }
}

function collectionOperation(photo: Photo, row: ReviewRow, known: Map<string, CollectionRecord>): string {
  const title = row.collectionTitle.trim();
  if (!title) return "";
  if (photo.collections.some((item) => item.title.toLowerCase() === title.toLowerCase())) return "";
  return known.has(title.toLowerCase()) ? "add_to_collection" : "create_collection";
}

async function ensureCollection(row: ReviewRow, known: Map<string, CollectionRecord>, writer: UnsplashWriter): Promise<CollectionRecord> {
  const title = row.collectionTitle.trim();
  const found = known.get(title.toLowerCase());
  if (found) return found;
  const created = await writer.createCollection(title, row.collectionDescription);
  known.set(title.toLowerCase(), created);
  return created;
}
