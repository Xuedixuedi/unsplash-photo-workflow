import { DeskError } from "./errors";
import { photoFromApi } from "./photos";
import { redact } from "./redact";
import type { Photo, PhotoUpdate } from "./types";

export type UnsplashConfig = {
  token: string;
  username: string;
  apiBase: string;
  fetchImpl?: typeof fetch;
};

async function request(config: UnsplashConfig, path: string, init: RequestInit = {}): Promise<Response> {
  const fetchImpl = config.fetchImpl ?? fetch;
  const headers = new Headers(init.headers);
  headers.set("authorization", `Bearer ${config.token}`);
  headers.set("accept-version", "v1");
  const response = await fetchImpl(`${config.apiBase}${path}`, { ...init, headers });
  if (response.status === 401) {
    throw new DeskError("Unsplash rejected the user token. Run `upw auth` and refresh UNSPLASH_USER_TOKEN.", 401);
  }
  if (response.status === 429 || response.status === 403) {
    const body = await response.text();
    if (response.status === 429 || body.toLowerCase().includes("rate limit")) {
      throw new DeskError("Unsplash rate limit reached. Wait for the hourly window, then apply the remaining photos.", 429);
    }
    throw new DeskError(redact(body || `Unsplash returned ${response.status}.`), response.status);
  }
  if (!response.ok) {
    const body = await response.text();
    throw new DeskError(redact(body || `Unsplash returned ${response.status}.`), response.status);
  }
  return response;
}

export async function listUserPhotos(config: UnsplashConfig): Promise<Photo[]> {
  const photos: Photo[] = [];
  for (let page = 1; page <= 100; page += 1) {
    const response = await request(
      config,
      `/users/${encodeURIComponent(config.username)}/photos?page=${page}&per_page=30&order_by=latest`,
    );
    const batch = (await response.json()) as unknown[];
    if (!Array.isArray(batch) || batch.length === 0) break;
    for (const item of batch) {
      if (item && typeof item === "object") photos.push(photoFromApi(item as Record<string, unknown>));
    }
    if (batch.length < 30) break;
  }
  return photos;
}

export function encodeUpdate(payload: PhotoUpdate): string {
  const params = new URLSearchParams();
  if (payload.description !== undefined) params.set("description", payload.description);
  if (payload.showOnProfile !== undefined) params.set("show_on_profile", payload.showOnProfile ? "true" : "false");
  for (const tag of payload.tags ?? []) params.append("tags[]", tag);
  if (payload.location) {
    const { location } = payload;
    if (location.name) params.set("location[name]", location.name);
    if (location.city) params.set("location[city]", location.city);
    if (location.country) params.set("location[country]", location.country);
    if (location.latitude !== null) params.set("location[latitude]", location.latitude.toFixed(6));
    if (location.longitude !== null) params.set("location[longitude]", location.longitude.toFixed(6));
  }
  return params.toString();
}

export async function updatePhoto(config: UnsplashConfig, photoId: string, payload: PhotoUpdate): Promise<void> {
  await request(config, `/photos/${encodeURIComponent(photoId)}`, {
    method: "PUT",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: encodeUpdate(payload),
  });
}

export async function listCollections(config: UnsplashConfig): Promise<{ id: string; title: string }[]> {
  const found: { id: string; title: string }[] = [];
  for (let page = 1; page <= 50; page += 1) {
    const response = await request(
      config,
      `/users/${encodeURIComponent(config.username)}/collections?page=${page}&per_page=30`,
    );
    const batch = (await response.json()) as { id?: string | number; title?: string }[];
    if (!Array.isArray(batch) || batch.length === 0) break;
    for (const item of batch) {
      if (item && item.id !== undefined) found.push({ id: String(item.id), title: String(item.title || "") });
    }
    if (batch.length < 30) break;
  }
  return found;
}

export async function createCollection(config: UnsplashConfig, title: string, description: string): Promise<{ id: string; title: string }> {
  const body = new URLSearchParams({ title, description, private: "false" });
  const response = await request(config, "/collections", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  const payload = (await response.json()) as { id?: string | number; title?: string };
  return { id: String(payload.id), title: String(payload.title || title) };
}

export async function addPhotoToCollection(config: UnsplashConfig, collectionId: string, photoId: string): Promise<void> {
  const body = new URLSearchParams({ photo_id: photoId });
  try {
    await request(config, `/collections/${encodeURIComponent(collectionId)}/add`, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message.toLowerCase() : "";
    if (message.includes("already")) return;
    throw error;
  }
}
