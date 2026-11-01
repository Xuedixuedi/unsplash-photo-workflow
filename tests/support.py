"""Shared factories for unit tests."""

from __future__ import annotations

from pathlib import Path

from upw.models import Location, Photo, Place, Trip, TripDay


def photo(**overrides: object) -> Photo:
    raw: dict[str, object] = {
        "id": "p1",
        "slug": "p1",
        "created_at": "2026-10-31T02:00:00Z",
        "tags": ["Travel Photography"],
        "downloads": 0,
        "likes": 0,
        "views": 0,
        "width": 1000,
        "height": 800,
    }
    raw.update(overrides)
    return Photo(
        id=str(raw["id"]),
        slug=str(raw.get("slug") or raw["id"]),
        created_at=str(raw.get("created_at") or ""),
        width=int(raw.get("width") or 0),
        height=int(raw.get("height") or 0),
        description=raw.get("description") if isinstance(raw.get("description"), str) else None,
        location=raw.get("location") if isinstance(raw.get("location"), Location) else None,
        tags=list(raw.get("tags") or []),  # type: ignore[arg-type]
        downloads=int(raw.get("downloads") or 0),
        likes=int(raw.get("likes") or 0),
        views=int(raw.get("views") or 0),
        show_on_profile=bool(raw.get("show_on_profile", True)),
        show_on_profile_known=bool(raw.get("show_on_profile_known", False)),
        captured_at=raw.get("captured_at") if isinstance(raw.get("captured_at"), str) else None,
        exif_location=raw.get("exif_location") if isinstance(raw.get("exif_location"), Location) else None,
        collections=list(raw.get("collections") or []),  # type: ignore[arg-type]
    )


def trip_one(day: str = "2026-10-31", name: str = "Five Flower Lake") -> Trip:
    from datetime import date

    return Trip(
        name="Jiuzhaigou",
        collection_name="Jiuzhaigou Autumn 2026",
        description="Autumn lakes.",
        template="mountain-autumn",
        tags=["jiuzhaigou"],
        days=[
            TripDay(
                day=date.fromisoformat(day),
                tags=["colorful lakes"],
                places=[Place(name=name, city="Jiuzhaigou County", region="Ngawa", country="China")],
            )
        ],
    )


def write_jpeg(path: Path, *, lat: float | None, lon: float | None, when: str) -> None:
    import piexif
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 24), (20, 40, 60)).save(path, format="JPEG")

    def dms(value: float) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
        absolute = abs(value)
        degrees = int(absolute)
        minutes_float = (absolute - degrees) * 60
        minutes = int(minutes_float)
        seconds = int(round((minutes_float - minutes) * 60 * 1000))
        return ((degrees, 1), (minutes, 1), (seconds, 1000))

    gps: dict[int, object] = {}
    if lat is not None and lon is not None:
        gps[piexif.GPSIFD.GPSLatitudeRef] = b"N" if lat >= 0 else b"S"
        gps[piexif.GPSIFD.GPSLatitude] = dms(lat)
        gps[piexif.GPSIFD.GPSLongitudeRef] = b"E" if lon >= 0 else b"W"
        gps[piexif.GPSIFD.GPSLongitude] = dms(lon)
    payload = {"Exif": {piexif.ExifIFD.DateTimeOriginal: when.encode("ascii")}, "GPS": gps}
    piexif.insert(piexif.dump(payload), str(path))
