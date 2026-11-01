"""Local capture time and GPS.

Unsplash does not return GPS. Many DSLR and mirrorless cameras do not record it
either. Coordinates come from the original file, or from a phone export / GPX /
Google Timeline track matched by timestamp.
The camera clock can sit ahead or behind the phone; `camera_clock_offset_seconds`
is added to the camera timestamp before matching.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from upw.models import Location

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".tif", ".tiff", ".heic", ".webp", ".png"}


@dataclass
class LocalCapture:
    captured_at: str | None = None
    location: Location | None = None
    path: str | None = None


@dataclass
class TrackPoint:
    captured_at: datetime
    latitude: float
    longitude: float


class OriginalIndex:
    """Map Unsplash photo ids to local camera files."""

    def __init__(self, directory: Path, *, timezone_name: str, offset_seconds: int) -> None:
        self.directory = directory
        self.timezone_name = timezone_name
        self.offset_seconds = offset_seconds
        self.by_photo_id: dict[str, LocalCapture] = {}
        if directory.exists():
            self._scan()

    def _scan(self) -> None:
        manifest = self.directory / "manifest.csv"
        named: dict[str, Path] = {}
        if manifest.exists():
            for line in manifest.read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.lower().startswith("photo_id"):
                    continue
                photo_id, _, filename = line.partition(",")
                path = self.directory / filename.strip()
                if photo_id.strip() and path.exists():
                    named[photo_id.strip()] = path
        for path in sorted(self.directory.iterdir()):
            if not path.is_file() or path.suffix.lower() not in _IMAGE_SUFFIXES:
                continue
            if path.stem not in named:
                named.setdefault(path.stem, path)
        for photo_id, path in named.items():
            self.by_photo_id[photo_id] = read_image_capture(
                path,
                timezone_name=self.timezone_name,
                offset_seconds=self.offset_seconds,
            )

    def image_path(self, photo_id: str) -> Path | None:
        record = self.by_photo_id.get(photo_id)
        if record is None or not record.path:
            return None
        return Path(record.path)


def read_image_capture(path: Path, *, timezone_name: str, offset_seconds: int) -> LocalCapture:
    try:
        import exifread
    except ImportError:  # pragma: no cover
        return LocalCapture(path=str(path))
    with path.open("rb") as handle:
        tags = exifread.process_file(handle, details=False)
    return LocalCapture(
        captured_at=_exif_time(tags, timezone_name=timezone_name, offset_seconds=offset_seconds),
        location=_exif_gps(tags),
        path=str(path),
    )


def _exif_time(tags: dict[str, object], *, timezone_name: str, offset_seconds: int) -> str | None:
    raw = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
    if raw is None:
        return None
    text = str(raw).strip()
    try:
        naive = datetime.strptime(text, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    aware = naive.replace(tzinfo=ZoneInfo(timezone_name)) + timedelta(seconds=offset_seconds)
    return aware.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ratio(value: object) -> float:
    num = getattr(value, "num", None)
    den = getattr(value, "den", None)
    if num is not None and den:
        return float(num) / float(den)
    text = str(value)
    if "/" in text:
        left, right = text.split("/", 1)
        return float(left) / float(right)
    return float(text)


def _dms(values: object, ref: str) -> float | None:
    raw = getattr(values, "values", values)
    if not isinstance(raw, (list, tuple)):
        return None
    parts = list(raw)
    if len(parts) < 3:
        return None
    degrees = _ratio(parts[0]) + _ratio(parts[1]) / 60 + _ratio(parts[2]) / 3600
    if ref.upper() in {"S", "W"}:
        degrees = -degrees
    return degrees


def _exif_gps(tags: dict[str, object]) -> Location | None:
    lat_ref = str(tags.get("GPS GPSLatitudeRef") or "")
    lon_ref = str(tags.get("GPS GPSLongitudeRef") or "")
    lat = tags.get("GPS GPSLatitude")
    lon = tags.get("GPS GPSLongitude")
    if lat is None or lon is None:
        return None
    latitude = _dms(lat, lat_ref)
    longitude = _dms(lon, lon_ref)
    if latitude is None or longitude is None:
        return None
    return Location(latitude=latitude, longitude=longitude)


def load_track(path: Path) -> list[TrackPoint]:
    """Load a GPX file, a Google Timeline JSON export, or a directory of phone photos."""
    if path.is_dir():
        points: list[TrackPoint] = []
        for image in sorted(path.iterdir()):
            if image.suffix.lower() not in _IMAGE_SUFFIXES:
                continue
            record = read_image_capture(image, timezone_name="UTC", offset_seconds=0)
            if record.captured_at and record.location and record.location.latitude is not None:
                when = datetime.fromisoformat(record.captured_at.replace("Z", "+00:00"))
                points.append(
                    TrackPoint(
                        captured_at=when,
                        latitude=float(record.location.latitude),
                        longitude=float(record.location.longitude or 0),
                    )
                )
        return points
    suffix = path.suffix.lower()
    if suffix == ".gpx":
        return _load_gpx(path)
    if suffix == ".json":
        return _load_timeline_json(path)
    return []


def _load_gpx(path: Path) -> list[TrackPoint]:
    root = ET.parse(path).getroot()
    points: list[TrackPoint] = []
    for element in root.iter():
        if not element.tag.endswith(("trkpt", "rtept", "wpt")):
            continue
        lat = element.attrib.get("lat")
        lon = element.attrib.get("lon")
        stamp = None
        for child in element:
            if child.tag.endswith("time") and child.text:
                stamp = child.text.strip()
        if lat is None or lon is None or not stamp:
            continue
        points.append(
            TrackPoint(
                captured_at=_parse_iso(stamp),
                latitude=float(lat),
                longitude=float(lon),
            )
        )
    return points


def _load_timeline_json(path: Path) -> list[TrackPoint]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[object]
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("locations"), list):
        rows = payload["locations"]
    elif isinstance(payload, dict) and isinstance(payload.get("points"), list):
        rows = payload["points"]
    else:
        rows = []
    points: list[TrackPoint] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parsed = _timeline_point(row)
        if parsed is not None:
            points.append(parsed)
    return points


def _timeline_point(row: dict[str, object]) -> TrackPoint | None:
    if "latitudeE7" in row and "longitudeE7" in row:
        latitude = float(row["latitudeE7"]) / 1e7  # type: ignore[arg-type]
        longitude = float(row["longitudeE7"]) / 1e7  # type: ignore[arg-type]
    elif "latitude" in row and "longitude" in row:
        latitude = float(row["latitude"])  # type: ignore[arg-type]
        longitude = float(row["longitude"])  # type: ignore[arg-type]
    elif "lat" in row and "lon" in row:
        latitude = float(row["lat"])  # type: ignore[arg-type]
        longitude = float(row["lon"])  # type: ignore[arg-type]
    else:
        return None
    stamp = row.get("time") or row.get("timestamp") or row.get("timestampMs") or row.get("timestamp_ms")
    if stamp is None:
        return None
    return TrackPoint(captured_at=_parse_any_time(stamp), latitude=latitude, longitude=longitude)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _parse_any_time(value: object) -> datetime:
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        millis = int(value)
        if millis < 10_000_000_000:
            millis *= 1000
        return datetime.fromtimestamp(millis / 1000, tz=UTC)
    return _parse_iso(str(value))


def match_track(
    captured_at: str | None,
    points: list[TrackPoint],
    *,
    max_seconds: int,
) -> TrackPoint | None:
    if not captured_at or not points:
        return None
    try:
        moment = _parse_iso(captured_at)
    except ValueError:
        return None
    best: TrackPoint | None = None
    best_delta: float | None = None
    for point in points:
        delta = abs((point.captured_at - moment).total_seconds())
        if delta <= max_seconds and (best_delta is None or delta < best_delta):
            best = point
            best_delta = delta
    return best
