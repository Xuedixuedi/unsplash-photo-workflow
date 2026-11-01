import type { Place, Trip, TripDay } from "./types";

export class TripInputError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TripInputError";
  }
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new TripInputError("Trip must be an object.");
  return value as Record<string, unknown>;
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function optional(value: unknown): string | null {
  const cleaned = text(value);
  return cleaned || null;
}

function coordinate(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(text(value));
  return Number.isFinite(parsed) ? parsed : null;
}

function place(value: unknown): Place {
  const raw = record(value);
  const name = text(raw.name);
  if (!name) throw new TripInputError("A place is missing its name.");
  return {
    name,
    city: optional(raw.city),
    region: optional(raw.region),
    country: optional(raw.country),
    latitude: coordinate(raw.latitude),
    longitude: coordinate(raw.longitude),
  };
}

function tags(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => text(item)).filter(Boolean);
  return text(value)
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function parseTrip(value: unknown): Trip {
  const raw = record(value);
  const name = text(raw.name);
  if (!name) throw new TripInputError("The trip needs a name.");
  const daysRaw = Array.isArray(raw.days) ? raw.days : [];
  if (daysRaw.length === 0) throw new TripInputError("Add at least one day.");
  const days: TripDay[] = daysRaw.map((item) => {
    const day = record(item);
    const date = text(day.date);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new TripInputError("Each day needs a date as YYYY-MM-DD.");
    const places = Array.isArray(day.places) ? day.places.filter((placeItem) => {
      if (!placeItem || typeof placeItem !== "object") return false;
      return text((placeItem as Record<string, unknown>).name).length > 0;
    }).map(place) : [];
    return { date, tags: tags(day.tags), places };
  });
  return {
    name,
    collection: text(raw.collection) || name,
    description: text(raw.description),
    template: optional(raw.template),
    tags: tags(raw.tags),
    days,
  };
}
