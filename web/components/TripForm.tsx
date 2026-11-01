"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { EXAMPLE_TRIP } from "@/lib/example-trip";
import { TEMPLATE_NAMES } from "@/lib/rules";
import type { Place, Trip, TripDay } from "@/lib/types";

import { PlaceSearch } from "./PlaceSearch";

const EMPTY_DAY: TripDay = { date: "", tags: [], places: [] };

export function TripForm() {
  const router = useRouter();
  const [trip, setTrip] = useState<Trip>({
    name: "",
    collection: "",
    description: "",
    template: "mountain-autumn",
    tags: [],
    days: [{ ...EMPTY_DAY }],
  });
  const [tagText, setTagText] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  function setDay(index: number, day: TripDay) {
    setTrip((current) => ({
      ...current,
      days: current.days.map((item, itemIndex) => (itemIndex === index ? day : item)),
    }));
  }

  async function start() {
    setPending(true);
    setError("");
    const payload: Trip = { ...trip, tags: splitTags(tagText) };
    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ trip: payload }),
      });
      const data = (await response.json()) as { id?: string; error?: string };
      if (!response.ok || !data.id) {
        setError(data.error || "The analysis did not start.");
        setPending(false);
        return;
      }
      router.push(`/review/${data.id}`);
    } catch {
      setError("Could not reach the desk.");
      setPending(false);
    }
  }

  return (
    <section className="sheet">
      <div className="button-row">
        <button
          type="button"
          className="secondary"
          onClick={() => {
            setTrip(EXAMPLE_TRIP);
            setTagText(EXAMPLE_TRIP.tags.join(", "));
          }}
        >
          Use the Jiuzhaigou example
        </button>
      </div>
      <div className="grid-2">
        <div>
          <label htmlFor="trip-name">Trip name</label>
          <input id="trip-name" value={trip.name} onChange={(event) => setTrip({ ...trip, name: event.target.value })} />
        </div>
        <div>
          <label htmlFor="collection">Collection</label>
          <input
            id="collection"
            value={trip.collection}
            onChange={(event) => setTrip({ ...trip, collection: event.target.value })}
          />
        </div>
      </div>
      <label htmlFor="description">Description</label>
      <textarea
        id="description"
        value={trip.description}
        onChange={(event) => setTrip({ ...trip, description: event.target.value })}
      />
      <div className="grid-2">
        <div>
          <label htmlFor="template">Tag template</label>
          <select
            id="template"
            value={trip.template ?? ""}
            onChange={(event) => setTrip({ ...trip, template: event.target.value || null })}
          >
            <option value="">None</option>
            {TEMPLATE_NAMES.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="trip-tags">Trip tags</label>
          <input id="trip-tags" value={tagText} onChange={(event) => setTagText(event.target.value)} placeholder="autumn, lake" />
        </div>
      </div>
      {trip.days.map((day, index) => (
        <div className="day" key={`${day.date}-${index}`}>
          <div className="day-head">
            <strong>Day {index + 1}</strong>
            {trip.days.length > 1 ? (
              <button
                type="button"
                className="text-button"
                onClick={() => setTrip({ ...trip, days: trip.days.filter((_, itemIndex) => itemIndex !== index) })}
              >
                Remove day
              </button>
            ) : null}
          </div>
          <div className="grid-2">
            <div>
              <label htmlFor={`date-${index}`}>Date</label>
              <input
                id={`date-${index}`}
                type="date"
                value={day.date}
                onChange={(event) => setDay(index, { ...day, date: event.target.value })}
              />
            </div>
            <div>
              <label htmlFor={`day-tags-${index}`}>Day tags</label>
              <input
                id={`day-tags-${index}`}
                key={`${index}-${day.tags.join("|")}`}
                defaultValue={day.tags.join(", ")}
                onBlur={(event) => setDay(index, { ...day, tags: splitTags(event.target.value) })}
              />
            </div>
          </div>
          <PlaceSearch
            id={`place-${index}`}
            onPick={(place) => setDay(index, { ...day, places: [...day.places, place] })}
          />
          {day.places.map((place, placeIndex) => (
            <PlaceRow
              key={`${place.name}-${placeIndex}`}
              place={place}
              idPrefix={`${index}-${placeIndex}`}
              onChange={(next) =>
                setDay(index, {
                  ...day,
                  places: day.places.map((item, itemIndex) => (itemIndex === placeIndex ? next : item)),
                })
              }
              onRemove={() =>
                setDay(index, { ...day, places: day.places.filter((_, itemIndex) => itemIndex !== placeIndex) })
              }
            />
          ))}
        </div>
      ))}
      <div className="button-row">
        <button type="button" className="secondary" onClick={() => setTrip({ ...trip, days: [...trip.days, { ...EMPTY_DAY }] })}>
          Add a day
        </button>
        <button type="button" onClick={start} disabled={pending}>
          {pending ? "Reading the library…" : "Start analysis"}
        </button>
      </div>
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

function splitTags(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function PlaceRow({
  place,
  idPrefix,
  onChange,
  onRemove,
}: {
  place: Place;
  idPrefix: string;
  onChange: (place: Place) => void;
  onRemove: () => void;
}) {
  return (
    <div className="day">
      <div className="place-head">
        <span className="frame-id">{place.name}</span>
        <button type="button" className="text-button" onClick={onRemove}>
          Remove place
        </button>
      </div>
      <div className="grid-3">
        <div>
          <label htmlFor={`place-name-${idPrefix}`}>Name</label>
          <input id={`place-name-${idPrefix}`} value={place.name} onChange={(event) => onChange({ ...place, name: event.target.value })} />
        </div>
        <div>
          <label htmlFor={`place-city-${idPrefix}`}>City</label>
          <input id={`place-city-${idPrefix}`} value={place.city ?? ""} onChange={(event) => onChange({ ...place, city: event.target.value || null })} />
        </div>
        <div>
          <label htmlFor={`place-region-${idPrefix}`}>Region</label>
          <input
            id={`place-region-${idPrefix}`}
            value={place.region ?? ""}
            onChange={(event) => onChange({ ...place, region: event.target.value || null })}
          />
        </div>
        <div>
          <label htmlFor={`place-country-${idPrefix}`}>Country</label>
          <input
            id={`place-country-${idPrefix}`}
            value={place.country ?? ""}
            onChange={(event) => onChange({ ...place, country: event.target.value || null })}
          />
        </div>
      </div>
    </div>
  );
}
