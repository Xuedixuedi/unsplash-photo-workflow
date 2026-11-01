import type { Place } from "./types";

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

type NominatimAddress = Record<string, string | undefined>;

export type NominatimHit = {
  name?: string;
  display_name?: string;
  lat?: string;
  lon?: string;
  address?: NominatimAddress;
  error?: string;
};

let lastRequest = 0;
const cache = new Map<string, Place[]>();

export function locationFromNominatim(data: NominatimHit): Place | null {
  if (data.error) return null;
  const address = data.address ?? {};
  const name =
    address.tourism ||
    address.attraction ||
    address.peak ||
    address.water ||
    address.natural ||
    address.historic ||
    data.name ||
    (data.display_name || "").split(",")[0]?.trim() ||
    "";
  if (!name.trim()) return null;
  const latitude = data.lat ? Number(data.lat) : null;
  const longitude = data.lon ? Number(data.lon) : null;
  return {
    name: name.trim(),
    city: address.city || address.town || address.village || address.municipality || address.county || null,
    region: address.state || null,
    country: address.country || null,
    latitude: latitude !== null && Number.isFinite(latitude) ? latitude : null,
    longitude: longitude !== null && Number.isFinite(longitude) ? longitude : null,
  };
}

export async function searchPlaces(query: string, fetchImpl: FetchLike = fetch): Promise<Place[]> {
  const text = query.trim();
  if (text.length < 2) return [];
  const key = text.toLowerCase();
  const cached = cache.get(key);
  if (cached) return cached;
  const userAgent = process.env.NOMINATIM_USER_AGENT || "unsplash-photo-workflow/0.1 (https://github.com/Xuedixuedi/unsplash-photo-workflow)";
  if (userAgent.length < 8) throw new Error("NOMINATIM_USER_AGENT is too short.");
  const wait = 1000 - (Date.now() - lastRequest);
  if (lastRequest && wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
  lastRequest = Date.now();
  const base = (process.env.UPW_NOMINATIM_BASE || "https://nominatim.openstreetmap.org").replace(/\/$/, "");
  const url = new URL(`${base}/search`);
  url.searchParams.set("q", text);
  url.searchParams.set("format", "jsonv2");
  url.searchParams.set("addressdetails", "1");
  url.searchParams.set("limit", "5");
  const response = await fetchImpl(url.toString(), { headers: { "user-agent": userAgent, accept: "application/json" } });
  if (!response.ok) throw new Error(`Nominatim returned ${response.status}.`);
  const payload = (await response.json()) as NominatimHit[];
  const places = (Array.isArray(payload) ? payload : []).map(locationFromNominatim).filter((place): place is Place => place !== null);
  cache.set(key, places);
  return places;
}

export function resetNominatimForTests(): void {
  lastRequest = 0;
  cache.clear();
}
