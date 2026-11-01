import type { Location, Photo } from "./types";

const COUNTRIES = new Set([
  "china",
  "japan",
  "south korea",
  "korea",
  "malaysia",
  "singapore",
  "indonesia",
  "cambodia",
  "thailand",
  "vietnam",
  "taiwan",
  "laos",
]);

function clean(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text || null;
}

function num(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function count(value: unknown): number {
  if (value === null || value === undefined || value === false) return 0;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function emptyLocation(location: Location | null): boolean {
  if (!location) return true;
  return !(
    location.name ||
    location.city ||
    location.region ||
    location.country ||
    location.latitude !== null ||
    location.longitude !== null
  );
}

export function parseLocationText(text: string | null): Location | null {
  const raw = clean(text);
  if (!raw) return null;
  const parts = raw
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length === 1) return { name: parts[0], city: null, region: null, country: null, latitude: null, longitude: null };
  const country = COUNTRIES.has(parts[parts.length - 1].toLowerCase()) ? parts[parts.length - 1] : null;
  const body = country ? parts.slice(0, -1) : parts;
  const name = body[0] ?? null;
  let region = body.length >= 2 ? body[body.length - 1] : null;
  const city = body.length >= 3 ? body[body.length - 2] : null;
  if (region === name) region = null;
  return { name, city, region, country, latitude: null, longitude: null };
}

export function photoDay(photo: Photo): string | null {
  const raw = photo.capturedAt || photo.createdAt;
  if (raw.length < 10) return null;
  const day = raw.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(day) ? day : null;
}

export function hasClockTime(value: string | null): boolean {
  if (!value || !value.includes("T")) return false;
  return !value.endsWith("T00:00:00Z") && !value.endsWith("T00:00:00+00:00");
}

export function parseWhen(value: string | null): number | null {
  if (!hasClockTime(value) || !value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

type ApiRecord = Record<string, unknown>;

export function photoFromApi(raw: ApiRecord): Photo {
  const locRaw = raw.location && typeof raw.location === "object" ? (raw.location as ApiRecord) : null;
  let location: Location | null = null;
  if (locRaw) {
    const position = locRaw.position && typeof locRaw.position === "object" ? (locRaw.position as ApiRecord) : {};
    location = {
      name: clean(locRaw.name),
      city: clean(locRaw.city),
      region: clean(locRaw.region),
      country: clean(locRaw.country),
      latitude: num(locRaw.latitude ?? position.latitude),
      longitude: num(locRaw.longitude ?? position.longitude),
    };
    if (location.name && !location.city && !location.country && location.name.includes(",")) {
      const parsed = parseLocationText(location.name);
      if (parsed) {
        parsed.latitude = location.latitude;
        parsed.longitude = location.longitude;
        location = parsed;
      }
    }
    if (emptyLocation(location)) location = null;
  }
  const tags: string[] = [];
  for (const item of Array.isArray(raw.tags) ? raw.tags : []) {
    if (typeof item === "string" && item.trim()) tags.push(item.trim());
    else if (item && typeof item === "object" && "title" in item && item.title) tags.push(String(item.title).trim());
  }
  const exif = raw.exif && typeof raw.exif === "object" ? (raw.exif as ApiRecord) : {};
  const urlsRaw = raw.urls && typeof raw.urls === "object" ? (raw.urls as ApiRecord) : {};
  const urls: Photo["urls"] = {};
  if (urlsRaw.small) urls.small = String(urlsRaw.small);
  if (urlsRaw.regular) urls.regular = String(urlsRaw.regular);
  const collections: Photo["collections"] = [];
  const collectionSource = raw.current_user_collections ?? raw.collections;
  for (const item of Array.isArray(collectionSource) ? collectionSource : []) {
    if (item && typeof item === "object" && "id" in item && item.id !== undefined && item.id !== null) {
      const record = item as ApiRecord;
      collections.push({ id: String(record.id), title: String(record.title ?? "") });
    }
  }
  const known = "show_on_profile" in raw && raw.show_on_profile !== null && raw.show_on_profile !== undefined;
  return {
    id: String(raw.id),
    slug: String(raw.slug || raw.id),
    createdAt: String(raw.created_at || raw.created || ""),
    width: Number(raw.width ?? raw.w ?? 0) || 0,
    height: Number(raw.height ?? raw.h ?? 0) || 0,
    description: clean("description" in raw ? raw.description : raw.desc),
    altDescription: clean("alt_description" in raw ? raw.alt_description : raw.alt),
    location,
    tags,
    downloads: count(raw.downloads !== undefined && raw.downloads !== null ? raw.downloads : raw.dl),
    likes: Number(raw.likes ?? 0) || 0,
    views: Number(raw.views ?? 0) || 0,
    camera: clean(exif.name) || clean(raw.camera),
    showOnProfile: Boolean(raw.show_on_profile ?? true),
    showOnProfileKnown: known,
    urls,
    collections,
    capturedAt: clean(raw.captured_at),
  };
}
