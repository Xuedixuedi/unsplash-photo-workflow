"""Load trip itineraries from YAML."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from upw.errors import UpwError
from upw.models import Place, Trip, TripDay


def load_trips(directory: Path) -> list[Trip]:
    if not directory.exists():
        return []
    trips: list[Trip] = []
    for path in sorted(directory.glob("*.yaml")):
        trips.append(load_trip(path))
    return trips


def load_trip(path: Path) -> Trip:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise UpwError(f"{path.name} is not a trip mapping.")
    name = str(raw.get("name") or path.stem)
    collection = str(raw.get("collection") or raw.get("collection_name") or name)
    days: list[TripDay] = []
    for item in raw.get("days") or []:
        if not isinstance(item, dict) or not item.get("date"):
            raise UpwError(f"{path.name} has a day without a date.")
        places = [_place(place) for place in item.get("places") or [] if isinstance(place, dict)]
        days.append(
            TripDay(
                day=date.fromisoformat(str(item["date"])),
                places=places,
                tags=[str(tag) for tag in item.get("tags") or []],
            )
        )
    return Trip(
        name=name,
        collection_name=collection,
        description=str(raw.get("description") or ""),
        template=str(raw["template"]) if raw.get("template") else None,
        tags=[str(tag) for tag in raw.get("tags") or []],
        days=days,
        source=str(path),
    )


def _place(raw: dict[str, object]) -> Place:
    name = str(raw.get("name") or "").strip()
    if not name:
        raise UpwError("A trip place is missing its name.")

    def optional(key: str) -> str | None:
        value = raw.get(key)
        text = str(value).strip() if value is not None else ""
        return text or None

    def coord(key: str) -> float | None:
        value = raw.get(key)
        if value is None or value == "":
            return None
        return float(value)  # type: ignore[arg-type]

    return Place(
        name=name,
        city=optional("city"),
        region=optional("region"),
        country=optional("country"),
        latitude=coord("latitude"),
        longitude=coord("longitude"),
    )


def trip_for_day(trips: list[Trip], day: date | None) -> Trip | None:
    if day is None:
        return None
    for trip in trips:
        if trip.on(day) is not None:
            return trip
    return None
