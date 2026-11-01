"""Merge suggestions into review.json and a spreadsheet the owner can edit."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from upw.core.rules import Rules
from upw.models import FieldSuggestion, Location, Photo, PhotoPlan, Plan


def encode_location(location: Location | None) -> str:
    if location is None or location.is_empty():
        return ""

    def cell(value: str | None) -> str:
        return (value or "").replace("|", "/")

    def num(value: float | None) -> str:
        if value is None:
            return ""
        return f"{value:.6f}".rstrip("0").rstrip(".")

    return "|".join(
        [
            cell(location.name),
            cell(location.city),
            cell(location.region),
            cell(location.country),
            num(location.latitude),
            num(location.longitude),
        ]
    )


def parse_location_cell(cell: str) -> Location | None:
    if not cell.strip():
        return None
    parts = cell.split("|")
    while len(parts) < 6:
        parts.append("")
    name, city, region, country, lat, lon = (part.strip() for part in parts[:6])

    def num(value: str) -> float | None:
        if not value:
            return None
        return float(value)

    location = Location(
        name=name or None,
        city=city or None,
        region=region or None,
        country=country or None,
        latitude=num(lat),
        longitude=num(lon),
    )
    return None if location.is_empty() else location


def encode_tags(tags: list[str]) -> str:
    return "|".join(tag.replace("|", "/") for tag in tags)


def parse_tags_cell(cell: str) -> list[str]:
    if not cell.strip():
        return []
    return [part.strip() for part in cell.split("|") if part.strip()]


def decide_approve(
    location: FieldSuggestion,
    tags: FieldSuggestion,
    description: FieldSuggestion,
    visibility: FieldSuggestion,
    rules: Rules,
) -> str:
    checks = (
        ("location", location),
        ("tags", tags),
        ("description", description),
        ("show_on_profile", visibility),
    )
    for kind, suggestion in checks:
        if kind == "description" and (not suggestion.value or suggestion.flag == "empty"):
            continue
        if kind == "show_on_profile" and suggestion.source == "unchanged":
            continue
        if suggestion.flag in {"review", "empty"}:
            return "no"
        if suggestion.confidence < rules.min_auto_approve_confidence:
            return "no"
    return "yes"


def build_plan(
    *,
    run_id: str,
    photos: list[Photo],
    locations: dict[str, FieldSuggestion],
    tags: dict[str, FieldSuggestion],
    descriptions: dict[str, FieldSuggestion],
    visibility: dict[str, FieldSuggestion],
    collections: dict[str, tuple[str, str, str]],
    rules: Rules,
) -> Plan:
    rows: list[PhotoPlan] = []
    for photo in photos:
        location = locations[photo.id]
        tag = tags[photo.id]
        description = descriptions[photo.id]
        shown = visibility[photo.id]
        title, summary, action = collections.get(photo.id, ("", "", "skip"))
        notes = " | ".join(item.reason for item in (location, tag, description, shown) if item.reason)
        rows.append(
            PhotoPlan(
                photo_id=photo.id,
                slug=photo.slug,
                created_at=photo.created_at,
                downloads=photo.downloads,
                likes=photo.likes,
                approve=decide_approve(location, tag, description, shown, rules),
                notes=notes,
                collection_title=title,
                collection_description=summary,
                collection_action=action,
                current_location=encode_location(photo.location),
                current_tags=list(photo.tags),
                current_description=photo.description or "",
                current_show_on_profile=photo.show_on_profile,
                location=location,
                tags=tag,
                description=description,
                show_on_profile=shown,
            )
        )
    return Plan(
        run_id=run_id,
        created_at=datetime.now(UTC).isoformat(),
        photos=rows,
    )


def write_review_csv(plan: Plan, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "photo_id",
        "slug",
        "created_at",
        "downloads",
        "likes",
        "approve",
        "current_location",
        "proposed_location",
        "location_confidence",
        "location_source",
        "location_flag",
        "current_tags",
        "proposed_tags",
        "tags_confidence",
        "tags_source",
        "tags_flag",
        "current_description",
        "proposed_description",
        "description_confidence",
        "description_source",
        "description_flag",
        "current_show_on_profile",
        "proposed_show_on_profile",
        "visibility_confidence",
        "visibility_source",
        "visibility_flag",
        "collection_title",
        "collection_description",
        "collection_action",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in plan.photos:
            location = row.location.value if isinstance(row.location.value, Location) else None
            tag_value = row.tags.value if isinstance(row.tags.value, list) else []
            writer.writerow(
                {
                    "photo_id": row.photo_id,
                    "slug": row.slug,
                    "created_at": row.created_at,
                    "downloads": row.downloads,
                    "likes": row.likes,
                    "approve": row.approve,
                    "current_location": row.current_location,
                    "proposed_location": encode_location(location),
                    "location_confidence": f"{row.location.confidence:.2f}",
                    "location_source": row.location.source,
                    "location_flag": row.location.flag,
                    "current_tags": encode_tags(row.current_tags),
                    "proposed_tags": encode_tags([str(tag) for tag in tag_value]),
                    "tags_confidence": f"{row.tags.confidence:.2f}",
                    "tags_source": row.tags.source,
                    "tags_flag": row.tags.flag,
                    "current_description": row.current_description,
                    "proposed_description": str(row.description.value or ""),
                    "description_confidence": f"{row.description.confidence:.2f}",
                    "description_source": row.description.source,
                    "description_flag": row.description.flag,
                    "current_show_on_profile": _bool(row.current_show_on_profile),
                    "proposed_show_on_profile": _bool(bool(row.show_on_profile.value)),
                    "visibility_confidence": f"{row.show_on_profile.confidence:.2f}",
                    "visibility_source": row.show_on_profile.source,
                    "visibility_flag": row.show_on_profile.flag,
                    "collection_title": row.collection_title,
                    "collection_description": row.collection_description,
                    "collection_action": row.collection_action,
                    "notes": row.notes,
                }
            )


def overlay_csv(plan: Plan, path: Path) -> Plan:
    """Apply spreadsheet edits on top of the JSON plan."""
    if not path.exists():
        return plan
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_id = {row.photo_id: row for row in plan.photos}
    for raw in rows:
        photo_id = (raw.get("photo_id") or "").strip()
        current = by_id.get(photo_id)
        if current is None:
            continue
        current.approve = (raw.get("approve") or current.approve).strip().lower()
        proposed_location = parse_location_cell(raw.get("proposed_location") or "")
        encoded_now = encode_location(current.location.value if isinstance(current.location.value, Location) else None)
        if (raw.get("proposed_location") or "") != encoded_now:
            current.location = FieldSuggestion(proposed_location, 1.0, "human", "ok", "edited in review.csv")
        tag_now = encode_tags([str(tag) for tag in current.tags.value or []])
        if (raw.get("proposed_tags") or "") != tag_now:
            current.tags = FieldSuggestion(
                parse_tags_cell(raw.get("proposed_tags") or ""),
                1.0,
                "human",
                "ok",
                "edited in review.csv",
            )
        description_now = str(current.description.value or "")
        if (raw.get("proposed_description") or "") != description_now:
            current.description = FieldSuggestion(
                raw.get("proposed_description") or "",
                1.0,
                "human",
                "ok",
                "edited in review.csv",
            )
        shown_now = _bool(bool(current.show_on_profile.value))
        if (raw.get("proposed_show_on_profile") or "") != shown_now:
            current.show_on_profile = FieldSuggestion(
                _parse_bool(raw.get("proposed_show_on_profile") or ""),
                1.0,
                "human",
                "ok",
                "edited in review.csv",
            )
        if raw.get("collection_title") is not None:
            current.collection_title = raw.get("collection_title") or ""
        if raw.get("collection_action"):
            current.collection_action = raw["collection_action"]
    return plan


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def render_table(plan: Plan, limit: int = 40) -> str:
    lines = [f"Review {plan.run_id}  {len(plan.photos)} photos  ({sum(1 for row in plan.photos if row.approve == 'yes')} approved)"]
    lines.append(f"{'photo':<16} {'approve':<8} {'where':<28} {'flag':<8} collection")
    for row in plan.photos[:limit]:
        location = row.location.value if isinstance(row.location.value, Location) else None
        where = (location.name if location and location.name else row.location.source)[:28]
        lines.append(f"{row.photo_id:<16} {row.approve:<8} {where:<28} {row.location.flag:<8} {row.collection_title}")
    if len(plan.photos) > limit:
        lines.append(f"... {len(plan.photos) - limit} more rows in the csv")
    return "\n".join(lines)
