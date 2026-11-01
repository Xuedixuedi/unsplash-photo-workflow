import { applyOne, type UnsplashWriter } from "./apply";
import { getPlan, savePlan } from "./db";
import { DeskError } from "./errors";
import { loadFixturePhotos } from "./fixtures";
import { loadEnv } from "./env";
import { buildPlan } from "./plan";
import { redact } from "./redact";
import { parseTrip } from "./trip-input";
import type { ApplyResult, StoredPlan } from "./types";
import { addPhotoToCollection, createCollection, listCollections, listUserPhotos, updatePhoto } from "./unsplash";

export async function loadPhotos() {
  loadEnv();
  if (process.env.UPW_USE_FIXTURES === "1") return loadFixturePhotos();
  const token = process.env.UNSPLASH_USER_TOKEN || "";
  if (!token) {
    throw new DeskError("Set UNSPLASH_USER_TOKEN, or UPW_USE_FIXTURES=1 to rehearse with the public metadata.");
  }
  return listUserPhotos({
    token,
    username: process.env.UNSPLASH_USERNAME || "liuxuedi",
    apiBase: (process.env.UPW_API_BASE || "https://api.unsplash.com").replace(/\/$/, ""),
  });
}

export async function createPlanFromTrip(value: unknown): Promise<StoredPlan> {
  const trip = parseTrip(value);
  const photos = await loadPhotos();
  const plan: StoredPlan = {
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
    title: trip.collection || trip.name,
    trip,
    photos,
    rows: buildPlan(photos, trip),
    collections: [],
  };
  await savePlan(plan);
  return plan;
}

export async function replaceRows(planId: string, rows: StoredPlan["rows"]): Promise<StoredPlan> {
  const plan = await getPlan(planId);
  if (!plan) throw new DeskError("That review no longer exists.", 404);
  const allowed = new Set(plan.photos.map((photo) => photo.id));
  plan.rows = rows.filter((row) => allowed.has(row.photoId));
  await savePlan(plan);
  return plan;
}

export async function applyStoredPhoto(planId: string, photoId: string): Promise<ApplyResult> {
  loadEnv();
  const plan = await getPlan(planId);
  if (!plan) throw new DeskError("That review no longer exists.", 404);
  const photo = plan.photos.find((item) => item.id === photoId);
  const row = plan.rows.find((item) => item.photoId === photoId);
  if (!photo || !row) throw new DeskError("That photo is not in this review.", 404);
  const known = new Map(plan.collections.map((item) => [item.title.toLowerCase(), item]));
  const fixture = process.env.UPW_USE_FIXTURES === "1";
  let writer: UnsplashWriter | null = null;
  let mode: "live" | "fixture" = "fixture";
  if (!fixture) {
    const token = process.env.UNSPLASH_USER_TOKEN || "";
    if (!token) throw new DeskError("Set UNSPLASH_USER_TOKEN before applying.");
    const config = {
      token,
      username: process.env.UNSPLASH_USERNAME || "liuxuedi",
      apiBase: (process.env.UPW_API_BASE || "https://api.unsplash.com").replace(/\/$/, ""),
    };
    const remote = await listCollections(config);
    for (const item of remote) known.set(item.title.toLowerCase(), item);
    writer = {
      updatePhoto: (id, payload) => updatePhoto(config, id, payload),
      listCollections: () => listCollections(config),
      createCollection: (title, description) => createCollection(config, title, description),
      addPhoto: (collectionId, id) => addPhotoToCollection(config, collectionId, id),
    };
    mode = "live";
  }
  const applied = await applyOne(photo, row, known, writer, mode);
  plan.collections = [...applied.known.values()].filter((item) => item.id !== "dry-run");
  const result = { ...applied.result, error: redact(applied.result.error) };
  const index = plan.rows.findIndex((item) => item.photoId === photoId);
  plan.rows[index] = { ...row, lastStatus: result.status, lastError: result.error };
  await savePlan(plan);
  return result;
}
