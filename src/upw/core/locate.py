"""Location fallback chain. Stop at the first source that hits."""

from __future__ import annotations

from typing import Protocol

from upw.adapters.exif import TrackPoint, match_track
from upw.adapters.llm import JsonCompleter, choose_place
from upw.core.rules import Rules
from upw.core.trips import trip_for_day
from upw.models import FieldSuggestion, Location, Photo, Trip, parse_when


class GeoLookup(Protocol):
    def reverse(self, latitude: float, longitude: float) -> Location | None: ...

    def forward(self, query: str) -> Location | None: ...


def locate_batch(
    photos: list[Photo],
    trips: list[Trip],
    phone_points: list[TrackPoint],
    geocoder: GeoLookup | None,
    llm: JsonCompleter | None,
    rules: Rules,
    images: dict[str, bytes] | None = None,
) -> dict[str, FieldSuggestion]:
    images = images or {}
    results: dict[str, FieldSuggestion] = {}
    for photo in photos:
        found = _local_or_existing(photo, phone_points, geocoder, rules)
        if found is not None:
            results[photo.id] = found
    for photo in photos:
        if photo.id in results:
            continue
        single = _single_place(photo, trips)
        if single is not None:
            results[photo.id] = single
    ordered = sorted(photos, key=lambda photo: photo.when())
    for photo in ordered:
        if photo.id in results:
            continue
        inherited = _from_neighbour(photo, ordered, results, rules)
        if inherited is not None:
            results[photo.id] = inherited
    for photo in photos:
        if photo.id in results:
            continue
        results[photo.id] = _llm_or_empty(photo, trips, llm, images.get(photo.id))
    return results


def _local_or_existing(
    photo: Photo,
    phone_points: list[TrackPoint],
    geocoder: GeoLookup | None,
    rules: Rules,
) -> FieldSuggestion | None:
    exif_location = photo.exif_location
    if exif_location is not None and exif_location.latitude is not None and exif_location.longitude is not None:
        named = _with_name(exif_location, geocoder)
        return FieldSuggestion(named, 0.97, "exif", "ok", "GPS from the local original")
    match = match_track(
        photo.captured_at,
        phone_points,
        max_seconds=rules.phone_match_max_seconds,
    )
    if match is not None:
        named = _with_name(
            Location(latitude=match.latitude, longitude=match.longitude),
            geocoder,
        )
        return FieldSuggestion(named, 0.9, "phone", "ok", "matched a phone or timeline point")
    if photo.location is not None and not photo.location.is_empty():
        return FieldSuggestion(
            photo.location,
            0.92,
            "existing",
            "ok",
            "keeping the location already on Unsplash",
        )
    return None


def _with_name(location: Location, geocoder: GeoLookup | None) -> Location:
    if location.name or geocoder is None or location.latitude is None or location.longitude is None:
        return location
    looked = geocoder.reverse(location.latitude, location.longitude)
    if looked is None:
        return location
    looked.latitude = location.latitude
    looked.longitude = location.longitude
    return looked


def _from_neighbour(
    photo: Photo,
    ordered: list[Photo],
    known: dict[str, FieldSuggestion],
    rules: Rules,
) -> FieldSuggestion | None:
    moment = parse_when(photo.captured_at)
    if moment is None:
        return None
    best: FieldSuggestion | None = None
    best_gap: float | None = None
    for other in ordered:
        if other.id == photo.id or other.id not in known:
            continue
        other_moment = parse_when(other.captured_at)
        if other_moment is None:
            continue
        gap = abs((other_moment - moment).total_seconds())
        if gap > rules.neighbour_max_seconds:
            continue
        suggestion = known[other.id]
        if not isinstance(suggestion.value, Location):
            continue
        if suggestion.source in {"neighbour", "llm"}:
            continue
        if best_gap is None or gap < best_gap:
            best = suggestion
            best_gap = gap
    if best is None or best_gap is None:
        return None
    confidence = max(0.5, 0.7 - (best_gap / max(rules.neighbour_max_seconds, 1)) * 0.2)
    return FieldSuggestion(
        best.value,
        round(confidence, 2),
        "neighbour",
        "review",
        f"inherited from a photo {int(best_gap)}s away",
    )


def _single_place(photo: Photo, trips: list[Trip]) -> FieldSuggestion | None:
    trip = trip_for_day(trips, photo.day())
    day = trip.on(photo.day()) if trip is not None else None
    if trip is None or day is None or len(day.places) != 1:
        return None
    return FieldSuggestion(
        day.places[0].as_location(),
        0.8,
        "itinerary",
        "ok",
        f"only place on {photo.day()} in {trip.name}",
    )


def _llm_or_empty(
    photo: Photo,
    trips: list[Trip],
    llm: JsonCompleter | None,
    image: bytes | None,
) -> FieldSuggestion:
    trip = trip_for_day(trips, photo.day())
    day = trip.on(photo.day()) if trip is not None else None
    places = day.places if day is not None else []
    if len(places) > 1 and llm is not None and image is not None:
        names = [place.name for place in places]
        chosen = choose_place(llm, photo_id=photo.id, names=names, image=image)
        if chosen:
            place = next(place for place in places if place.name == chosen)
            return FieldSuggestion(
                place.as_location(),
                0.55,
                "llm",
                "review",
                "model chose one itinerary place for that day",
            )
    if places:
        label = ", ".join(place.name for place in places)
        return FieldSuggestion(
            None,
            0.3,
            "ambiguous",
            "review",
            f"several places on this day ({label}); left empty",
        )
    return FieldSuggestion(None, 0.0, "none", "empty", "no location source hit")
