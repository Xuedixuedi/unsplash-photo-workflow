"""Config-driven visibility and tag limits."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from upw.models import FieldSuggestion, Photo, has_clock_time, parse_when

_DEFAULT_BRANDS = (
    "canon",
    "nikon",
    "sony",
    "fuji",
    "fujifilm",
    "eos",
    "dslr",
    "iphone",
    "adobe",
    "lightroom",
    "leica",
    "panasonic",
    "lumix",
    "gopro",
)


@dataclass
class Rules:
    target_tag_count: int = 20
    never_hide_above_downloads: int = 100
    burst_seconds: int = 4
    hide_burst_extras: bool = True
    min_auto_approve_confidence: float = 0.75
    camera_brands: tuple[str, ...] = _DEFAULT_BRANDS
    timezone: str = "Asia/Shanghai"
    camera_clock_offset_seconds: int = 0
    phone_match_max_seconds: int = 180
    neighbour_max_seconds: int = 900
    cluster_gap_days: int = 2
    force_hide_ids: tuple[str, ...] = ()
    force_show_ids: tuple[str, ...] = ()
    max_new_tag_words: int = 3
    max_existing_tag_words: int = 5
    description_from_location: bool = True


@dataclass
class TagTemplates:
    templates: dict[str, list[str]] = field(default_factory=dict)

    def for_name(self, name: str | None) -> list[str]:
        if not name:
            return []
        return list(self.templates.get(name, []))


def load_rules(path: Path) -> Rules:
    if not path.exists():
        return Rules()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return Rules()
    brands = raw.get("camera_brands")
    hide_ids = raw.get("force_hide_ids") or []
    show_ids = raw.get("force_show_ids") or []
    return Rules(
        target_tag_count=int(raw.get("target_tag_count", 20)),
        never_hide_above_downloads=int(raw.get("never_hide_above_downloads", 100)),
        burst_seconds=int(raw.get("burst_seconds", 4)),
        hide_burst_extras=bool(raw.get("hide_burst_extras", True)),
        min_auto_approve_confidence=float(raw.get("min_auto_approve_confidence", 0.75)),
        camera_brands=tuple(str(item).casefold() for item in brands) if brands else _DEFAULT_BRANDS,
        timezone=str(raw.get("timezone") or "Asia/Shanghai"),
        camera_clock_offset_seconds=int(raw.get("camera_clock_offset_seconds", 0)),
        phone_match_max_seconds=int(raw.get("phone_match_max_seconds", 180)),
        neighbour_max_seconds=int(raw.get("neighbour_max_seconds", 900)),
        cluster_gap_days=int(raw.get("cluster_gap_days", 2)),
        force_hide_ids=tuple(str(item) for item in hide_ids),
        force_show_ids=tuple(str(item) for item in show_ids),
        max_new_tag_words=int(raw.get("max_new_tag_words", 3)),
        max_existing_tag_words=int(raw.get("max_existing_tag_words", 5)),
        description_from_location=bool(raw.get("description_from_location", True)),
    )


def load_templates(path: Path) -> TagTemplates:
    if not path.exists():
        return TagTemplates()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    templates: dict[str, list[str]] = {}
    source = raw.get("templates") if isinstance(raw, dict) else None
    if isinstance(source, dict):
        for name, tags in source.items():
            templates[str(name)] = [str(tag) for tag in tags or []]
    return TagTemplates(templates=templates)


def burst_roles(photos: list[Photo], rules: Rules) -> dict[str, str]:
    """Mark extra frames in a short burst. The keeper stays visible."""
    roles = {photo.id: "single" for photo in photos}
    timed = [photo for photo in photos if parse_when(photo.captured_at) is not None]
    ordered = sorted(timed, key=lambda photo: photo.captured_at or "")
    group: list[Photo] = []

    def close(previous: Photo, current: Photo) -> bool:
        left = parse_when(previous.captured_at)
        right = parse_when(current.captured_at)
        if left is None or right is None:
            return False
        return abs((right - left).total_seconds()) <= rules.burst_seconds

    def finish(items: list[Photo]) -> None:
        if len(items) < 2:
            return
        keeper = max(
            items,
            key=lambda photo: (photo.downloads, photo.likes, photo.views, photo.width * photo.height),
        )
        for photo in items:
            roles[photo.id] = "keeper" if photo.id == keeper.id else "extra"

    for photo in ordered:
        if not group or close(group[-1], photo):
            group.append(photo)
        else:
            finish(group)
            group = [photo]
    finish(group)
    return roles


def decide_visibility(photo: Photo, rules: Rules, role: str) -> FieldSuggestion:
    if photo.downloads > rules.never_hide_above_downloads:
        return FieldSuggestion(
            True,
            0.99,
            "rule:downloads",
            "ok",
            f"downloads {photo.downloads} are above {rules.never_hide_above_downloads}",
        )
    if photo.id in rules.force_show_ids:
        return FieldSuggestion(True, 0.95, "rule:force-show", "ok", "listed in force_show_ids")
    if photo.id in rules.force_hide_ids:
        return FieldSuggestion(False, 0.9, "rule:force-hide", "review", "listed in force_hide_ids")
    if rules.hide_burst_extras and role == "extra":
        return FieldSuggestion(
            False,
            0.72,
            "rule:burst",
            "review",
            "extra frame in a short burst",
        )
    if not has_clock_time(photo.captured_at) and photo.show_on_profile:
        return FieldSuggestion(True, 0.6, "unchanged", "ok", "no burst timing available")
    return FieldSuggestion(
        photo.show_on_profile,
        0.6,
        "unchanged",
        "ok",
        "keeping the current visibility",
    )
