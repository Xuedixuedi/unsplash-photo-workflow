import type { Rules } from "./rules";
import { emptyLocation, hasClockTime, parseWhen, photoDay } from "./photos";
import type { Location, Photo, Place, Suggestion, Trip } from "./types";

function placeLocation(place: Place): Location {
  return {
    name: place.name,
    city: place.city,
    region: place.region,
    country: place.country,
    latitude: place.latitude,
    longitude: place.longitude,
  };
}

function dayOf(trip: Trip, photo: Photo) {
  const day = photoDay(photo);
  if (!day) return null;
  return trip.days.find((item) => item.date === day) ?? null;
}

/**
 * Deterministic location chain for the desk.
 * Local GPS and phone tracks stay in the Python CLI, which can read the files.
 * Order: location already on the photo, the only itinerary place that day,
 * a neighbour with a real clock time, otherwise empty and flagged.
 */
export function locateAll(photos: Photo[], trip: Trip, rules: Rules): Map<string, Suggestion<Location | null>> {
  const results = new Map<string, Suggestion<Location | null>>();
  for (const photo of photos) {
    if (photo.location && !emptyLocation(photo.location)) {
      results.set(photo.id, {
        value: photo.location,
        confidence: 0.92,
        source: "existing",
        flag: "ok",
        reason: "keeping the location already on Unsplash",
      });
      continue;
    }
    const day = dayOf(trip, photo);
    if (day && day.places.length === 1) {
      results.set(photo.id, {
        value: placeLocation(day.places[0]),
        confidence: 0.8,
        source: "itinerary",
        flag: "ok",
        reason: `only place on ${photoDay(photo)} in ${trip.name}`,
      });
    }
  }

  const ordered = [...photos].sort((left, right) => (left.capturedAt || left.createdAt).localeCompare(right.capturedAt || right.createdAt));
  for (const photo of ordered) {
    if (results.has(photo.id)) continue;
    const inherited = fromNeighbour(photo, ordered, results, rules);
    if (inherited) results.set(photo.id, inherited);
  }

  for (const photo of photos) {
    if (results.has(photo.id)) continue;
    const day = dayOf(trip, photo);
    const places = day?.places ?? [];
    if (places.length > 1) {
      const label = places.map((place) => place.name).join(", ");
      results.set(photo.id, {
        value: null,
        confidence: 0.3,
        source: "ambiguous",
        flag: "review",
        reason: `several places on this day (${label}); left empty`,
      });
    } else {
      results.set(photo.id, {
        value: null,
        confidence: 0,
        source: "none",
        flag: "empty",
        reason: "no location source hit",
      });
    }
  }
  return results;
}

function fromNeighbour(
  photo: Photo,
  ordered: Photo[],
  known: Map<string, Suggestion<Location | null>>,
  rules: Rules,
): Suggestion<Location | null> | null {
  const moment = parseWhen(photo.capturedAt);
  if (moment === null || !hasClockTime(photo.capturedAt)) return null;
  let best: Suggestion<Location | null> | null = null;
  let bestGap: number | null = null;
  for (const other of ordered) {
    if (other.id === photo.id || !known.has(other.id)) continue;
    const otherMoment = parseWhen(other.capturedAt);
    if (otherMoment === null) continue;
    const gap = Math.abs(otherMoment - moment) / 1000;
    if (gap > rules.neighbourMaxSeconds) continue;
    const suggestion = known.get(other.id);
    if (!suggestion?.value) continue;
    if (suggestion.source === "neighbour" || suggestion.source === "llm") continue;
    if (bestGap === null || gap < bestGap) {
      best = suggestion;
      bestGap = gap;
    }
  }
  if (!best || bestGap === null) return null;
  const confidence = Math.max(0.5, 0.7 - (bestGap / Math.max(rules.neighbourMaxSeconds, 1)) * 0.2);
  return {
    value: best.value,
    confidence: Math.round(confidence * 100) / 100,
    source: "neighbour",
    flag: "review",
    reason: `inherited from a photo ${Math.round(bestGap)}s away`,
  };
}
