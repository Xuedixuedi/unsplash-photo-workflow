"""Assign each photo to one trip collection, or to a date cluster."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from upw.core.rules import Rules
from upw.core.trips import trip_for_day
from upw.models import Photo, Trip


@dataclass
class Assignment:
    title: str
    description: str
    action: str


def assign_collections(photos: list[Photo], trips: list[Trip], rules: Rules) -> dict[str, Assignment]:
    assigned: dict[str, Assignment] = {}
    loose: list[Photo] = []
    for photo in photos:
        trip = trip_for_day(trips, photo.day())
        if trip is None:
            loose.append(photo)
            continue
        assigned[photo.id] = Assignment(
            title=trip.collection_name,
            description=trip.description or trip.name,
            action="add",
        )
    for group in _clusters(loose, rules.cluster_gap_days):
        days: list[date] = []
        for item in group:
            day = item.day()
            if day is not None:
                days.append(day)
        if not days:
            title = "Untitled trip"
            description = "Photos that did not match a trip itinerary."
        else:
            start, end = min(days), max(days)
            title = f"Trip {start.isoformat()}" if start == end else f"Trip {start.isoformat()} to {end.isoformat()}"
            description = f"Grouped by date from {start.isoformat()} to {end.isoformat()}."
        for photo in group:
            assigned[photo.id] = Assignment(title=title, description=description, action="add")
    return assigned


def _clusters(photos: list[Photo], gap_days: int) -> list[list[Photo]]:
    ordered = sorted(photos, key=lambda photo: photo.day() or date.min)
    groups: list[list[Photo]] = []
    current: list[Photo] = []
    for photo in ordered:
        if not current:
            current = [photo]
            continue
        previous = current[-1].day()
        this = photo.day()
        if previous is not None and this is not None and (this - previous).days > gap_days:
            groups.append(current)
            current = [photo]
        else:
            current.append(photo)
    if current:
        groups.append(current)
    return groups
