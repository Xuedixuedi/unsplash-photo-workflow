"use client";

import { useEffect, useState } from "react";

import type { Place } from "@/lib/types";

export function PlaceSearch({ id, onPick }: { id: string; onPick: (place: Place) => void }) {
  const [query, setQuery] = useState("");
  const [places, setPlaces] = useState<Place[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const text = query.trim();
    if (text.length < 2) return;
    const controller = new AbortController();
    const handle = setTimeout(async () => {
      try {
        const response = await fetch(`/api/places?q=${encodeURIComponent(text)}`, { signal: controller.signal });
        const data = (await response.json()) as { places?: Place[]; error?: string };
        if (!response.ok) throw new Error(data.error || "Place search failed.");
        setPlaces(data.places ?? []);
        setError("");
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        setError(caught instanceof Error ? caught.message : "Place search failed.");
      }
    }, 300);
    return () => {
      clearTimeout(handle);
      controller.abort();
    };
  }, [query]);

  return (
    <div>
      <label htmlFor={id}>Find a place</label>
      <input
        id={id}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Five Flower Lake"
        autoComplete="off"
      />
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}
      {places.length ? (
        <div className="suggestions" role="list">
          {places.map((place) => (
            <button
              key={`${place.name}-${place.latitude}-${place.longitude}`}
              type="button"
              onClick={() => {
                onPick(place);
                setQuery("");
                setPlaces([]);
              }}
            >
              {[place.name, place.city, place.country].filter(Boolean).join(", ")}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
