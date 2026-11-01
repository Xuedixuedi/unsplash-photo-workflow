"""Shared data objects for photos, trips, and review plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

# Last segment of a comma-separated Unsplash location string.
_COUNTRIES = {
    "china",
    "japan",
    "south korea",
    "korea",
    "malaysia",
    "singapore",
    "indonesia",
    "cambodia",
    "thailand",
    "vietnam",
    "taiwan",
    "laos",
}


def _count(value: Any) -> int:
    if value is None or value is False:
        return 0
    return int(value)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Location:
    name: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    def is_empty(self) -> bool:
        return not any(
            [
                self.name,
                self.city,
                self.region,
                self.country,
                self.latitude is not None,
                self.longitude is not None,
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "city": self.city,
            "region": self.region,
            "country": self.country,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> Location | None:
        if not raw:
            return None
        loc = cls(
            name=_clean(raw.get("name")),
            city=_clean(raw.get("city")),
            region=_clean(raw.get("region")),
            country=_clean(raw.get("country")),
            latitude=_num(raw.get("latitude")),
            longitude=_num(raw.get("longitude")),
        )
        return None if loc.is_empty() else loc


def parse_location_text(text: str | None) -> Location | None:
    """Split a single Unsplash display string into name, city, region, and country."""
    raw = _clean(text)
    if raw is None:
        return None
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) == 1:
        return Location(name=parts[0])
    country = parts[-1] if parts[-1].casefold() in _COUNTRIES else None
    body = parts[:-1] if country else parts
    name = body[0] if body else None
    region = body[-1] if len(body) >= 2 else None
    city = body[-2] if len(body) >= 3 else None
    if region == name:
        region = None
    return Location(name=name, city=city, region=region, country=country)


@dataclass
class CollectionRef:
    id: str
    title: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "title": self.title}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CollectionRef:
        return cls(id=str(raw.get("id", "")), title=str(raw.get("title") or ""))


@dataclass
class Photo:
    id: str
    slug: str = ""
    created_at: str = ""
    width: int = 0
    height: int = 0
    description: str | None = None
    alt_description: str | None = None
    location: Location | None = None
    tags: list[str] = field(default_factory=list)
    downloads: int = 0
    likes: int = 0
    views: int = 0
    camera: str | None = None
    show_on_profile: bool = True
    show_on_profile_known: bool = False
    urls: dict[str, str] = field(default_factory=dict)
    collections: list[CollectionRef] = field(default_factory=list)
    captured_at: str | None = None
    exif_location: Location | None = None

    def when(self) -> str:
        return self.captured_at or self.created_at

    def day(self) -> date | None:
        raw = self.when()
        if len(raw) < 10:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "slug": self.slug,
            "created_at": self.created_at,
            "width": self.width,
            "height": self.height,
            "description": self.description,
            "alt_description": self.alt_description,
            "location": None if self.location is None else self.location.to_dict(),
            "tags": list(self.tags),
            "downloads": self.downloads,
            "likes": self.likes,
            "views": self.views,
            "camera": self.camera,
            "show_on_profile": self.show_on_profile,
            "show_on_profile_known": self.show_on_profile_known,
            "urls": dict(self.urls),
            "collections": [item.to_dict() for item in self.collections],
            "captured_at": self.captured_at,
            "exif_location": None if self.exif_location is None else self.exif_location.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Photo:
        collections = [CollectionRef.from_dict(item) for item in raw.get("collections") or []]
        return cls(
            id=str(raw["id"]),
            slug=str(raw.get("slug") or raw.get("id") or ""),
            created_at=str(raw.get("created_at") or ""),
            width=int(raw.get("width") or 0),
            height=int(raw.get("height") or 0),
            description=_clean(raw.get("description")),
            alt_description=_clean(raw.get("alt_description")),
            location=Location.from_dict(raw.get("location")),
            tags=[str(tag) for tag in raw.get("tags") or []],
            downloads=int(raw.get("downloads") or 0),
            likes=int(raw.get("likes") or 0),
            views=int(raw.get("views") or 0),
            camera=_clean(raw.get("camera")),
            show_on_profile=bool(raw.get("show_on_profile", True)),
            show_on_profile_known=bool(raw.get("show_on_profile_known", False)),
            urls={str(key): str(value) for key, value in (raw.get("urls") or {}).items()},
            collections=collections,
            captured_at=_clean(raw.get("captured_at")),
            exif_location=Location.from_dict(raw.get("exif_location")),
        )


def photo_from_api(raw: dict[str, Any]) -> Photo:
    """Convert an Unsplash photo resource into our model."""
    loc_raw = raw.get("location") if isinstance(raw.get("location"), dict) else None
    location: Location | None = None
    if loc_raw:
        position = loc_raw.get("position") if isinstance(loc_raw.get("position"), dict) else {}
        location = Location(
            name=_clean(loc_raw.get("name")),
            city=_clean(loc_raw.get("city")),
            region=_clean(loc_raw.get("region")),
            country=_clean(loc_raw.get("country")),
            latitude=_num(loc_raw.get("latitude", position.get("latitude"))),
            longitude=_num(loc_raw.get("longitude", position.get("longitude"))),
        )
        if location.name and not location.city and not location.country and "," in location.name:
            parsed = parse_location_text(location.name)
            if parsed is not None:
                parsed.latitude = location.latitude
                parsed.longitude = location.longitude
                location = parsed
        if location.is_empty():
            location = None
    tags: list[str] = []
    for item in raw.get("tags") or []:
        if isinstance(item, str) and item.strip():
            tags.append(item.strip())
        elif isinstance(item, dict) and item.get("title"):
            tags.append(str(item["title"]).strip())
    exif_raw = raw.get("exif")
    exif: dict[str, Any] = exif_raw if isinstance(exif_raw, dict) else {}
    camera = _clean(exif.get("name")) or _clean(raw.get("camera"))
    urls_value = raw.get("urls")
    urls_raw: dict[str, Any] = urls_value if isinstance(urls_value, dict) else {}
    urls = {str(key): str(value) for key, value in urls_raw.items() if value}
    known = "show_on_profile" in raw and raw.get("show_on_profile") is not None
    collections: list[CollectionRef] = []
    for item in raw.get("current_user_collections") or raw.get("collections") or []:
        if isinstance(item, dict) and item.get("id") is not None:
            collections.append(CollectionRef(id=str(item["id"]), title=str(item.get("title") or "")))
    created = str(raw.get("created_at") or raw.get("created") or "")
    return Photo(
        id=str(raw["id"]),
        slug=str(raw.get("slug") or raw["id"]),
        created_at=created,
        width=int(raw.get("width") or raw.get("w") or 0),
        height=int(raw.get("height") or raw.get("h") or 0),
        description=_clean(raw.get("description") if "description" in raw else raw.get("desc")),
        alt_description=_clean(raw.get("alt_description") if "alt_description" in raw else raw.get("alt")),
        location=location,
        tags=tags,
        downloads=_count(raw.get("downloads") if raw.get("downloads") is not None else raw.get("dl")),
        likes=int(raw.get("likes") or 0),
        views=int(raw.get("views") or 0),
        camera=camera,
        show_on_profile=bool(raw.get("show_on_profile", True)),
        show_on_profile_known=known,
        urls=urls,
        collections=collections,
    )


@dataclass
class Place:
    name: str
    city: str | None = None
    region: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    def as_location(self) -> Location:
        return Location(
            name=self.name,
            city=self.city,
            region=self.region,
            country=self.country,
            latitude=self.latitude,
            longitude=self.longitude,
        )


@dataclass
class TripDay:
    day: date
    places: list[Place] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class Trip:
    name: str
    collection_name: str
    description: str = ""
    template: str | None = None
    tags: list[str] = field(default_factory=list)
    days: list[TripDay] = field(default_factory=list)
    source: str = ""

    def on(self, day: date | None) -> TripDay | None:
        if day is None:
            return None
        for item in self.days:
            if item.day == day:
                return item
        return None


@dataclass
class FieldSuggestion:
    value: Any
    confidence: float
    source: str
    flag: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = self.value
        if isinstance(value, Location):
            value = value.to_dict()
        return {
            "value": value,
            "confidence": self.confidence,
            "source": self.source,
            "flag": self.flag,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any], *, location: bool = False) -> FieldSuggestion:
        value = raw.get("value")
        if location and isinstance(value, dict):
            value = Location.from_dict(value)
        return cls(
            value=value,
            confidence=float(raw.get("confidence") or 0),
            source=str(raw.get("source") or ""),
            flag=str(raw.get("flag") or "review"),
            reason=str(raw.get("reason") or ""),
        )


@dataclass
class PhotoPlan:
    photo_id: str
    slug: str
    created_at: str
    downloads: int
    likes: int
    approve: str
    notes: str
    collection_title: str
    collection_description: str
    collection_action: str
    current_location: str
    current_tags: list[str]
    current_description: str
    current_show_on_profile: bool
    location: FieldSuggestion
    tags: FieldSuggestion
    description: FieldSuggestion
    show_on_profile: FieldSuggestion

    def to_dict(self) -> dict[str, Any]:
        return {
            "photo_id": self.photo_id,
            "slug": self.slug,
            "created_at": self.created_at,
            "downloads": self.downloads,
            "likes": self.likes,
            "approve": self.approve,
            "notes": self.notes,
            "collection_title": self.collection_title,
            "collection_description": self.collection_description,
            "collection_action": self.collection_action,
            "current_location": self.current_location,
            "current_tags": list(self.current_tags),
            "current_description": self.current_description,
            "current_show_on_profile": self.current_show_on_profile,
            "location": self.location.to_dict(),
            "tags": self.tags.to_dict(),
            "description": self.description.to_dict(),
            "show_on_profile": self.show_on_profile.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PhotoPlan:
        return cls(
            photo_id=str(raw["photo_id"]),
            slug=str(raw.get("slug") or ""),
            created_at=str(raw.get("created_at") or ""),
            downloads=int(raw.get("downloads") or 0),
            likes=int(raw.get("likes") or 0),
            approve=str(raw.get("approve") or "no"),
            notes=str(raw.get("notes") or ""),
            collection_title=str(raw.get("collection_title") or ""),
            collection_description=str(raw.get("collection_description") or ""),
            collection_action=str(raw.get("collection_action") or "skip"),
            current_location=str(raw.get("current_location") or ""),
            current_tags=[str(tag) for tag in raw.get("current_tags") or []],
            current_description=str(raw.get("current_description") or ""),
            current_show_on_profile=bool(raw.get("current_show_on_profile", True)),
            location=FieldSuggestion.from_dict(raw["location"], location=True),
            tags=FieldSuggestion.from_dict(raw["tags"]),
            description=FieldSuggestion.from_dict(raw["description"]),
            show_on_profile=FieldSuggestion.from_dict(raw["show_on_profile"]),
        )


@dataclass
class Plan:
    run_id: str
    created_at: str
    photos: list[PhotoPlan] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "photos": [photo.to_dict() for photo in self.photos],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Plan:
        return cls(
            run_id=str(raw.get("run_id") or ""),
            created_at=str(raw.get("created_at") or ""),
            photos=[PhotoPlan.from_dict(item) for item in raw.get("photos") or []],
        )


def has_clock_time(value: str | None) -> bool:
    """True when a timestamp includes a time, not just a calendar day."""
    if not value or "T" not in value:
        return False
    return not value.endswith("T00:00:00Z") and not value.endswith("T00:00:00+00:00")


def parse_when(value: str | None) -> datetime | None:
    if not value or not has_clock_time(value):
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed
