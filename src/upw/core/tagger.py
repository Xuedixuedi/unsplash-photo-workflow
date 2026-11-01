"""Fill tags up to the configured target. The LLM only fills leftover slots."""

from __future__ import annotations

import re

from upw.adapters.llm import JsonCompleter, suggest_tags
from upw.core.rules import Rules
from upw.models import FieldSuggestion, Location, Photo, Trip

_WORD = re.compile(r"[a-z0-9][a-z0-9'&/+.-]*$")


def normalize_tag(tag: str, *, brands: tuple[str, ...], max_words: int) -> str | None:
    text = " ".join(tag.strip().lower().split())
    if not text or "#" in text:
        return None
    words = text.split(" ")
    if not 1 <= len(words) <= max_words:
        return None
    if any(word in brands for word in words):
        return None
    if any(_WORD.fullmatch(word) is None for word in words):
        return None
    if len(text) > 40:
        return None
    return text


def build_tags(
    photo: Photo,
    location: Location | None,
    trip: Trip | None,
    day_tags: list[str],
    template_tags: list[str],
    rules: Rules,
    llm: JsonCompleter | None = None,
    image: bytes | None = None,
) -> FieldSuggestion:
    kept: list[str] = []
    seen: set[str] = set()
    used_llm = False

    def add(raw: str, *, existing: bool) -> None:
        limit = rules.max_existing_tag_words if existing else rules.max_new_tag_words
        cleaned = normalize_tag(raw, brands=rules.camera_brands, max_words=limit)
        if cleaned is None or cleaned.casefold() in seen:
            return
        if len(kept) >= rules.target_tag_count:
            return
        kept.append(cleaned)
        seen.add(cleaned.casefold())

    for tag in photo.tags:
        add(tag, existing=True)
    if location is not None:
        for part in (location.name, location.city, location.region, location.country):
            if part:
                add(part, existing=False)
    for tag in template_tags:
        add(tag, existing=False)
    if trip is not None:
        for tag in list(trip.tags) + list(day_tags):
            add(tag, existing=False)
    remaining = rules.target_tag_count - len(kept)
    if remaining > 0 and llm is not None:
        extras = suggest_tags(llm, photo_id=photo.id, existing=kept, need=remaining, image=image)
        if extras:
            used_llm = True
        for tag in extras:
            add(tag, existing=False)
    if not kept:
        return FieldSuggestion([], 0.2, "none", "review", "no usable tags")
    source = "llm" if used_llm else "deterministic"
    flag = "review" if used_llm else "ok"
    confidence = 0.58 if used_llm else (0.86 if len(kept) >= 8 else 0.78)
    reason = f"{len(kept)} tags"
    if len(kept) < rules.target_tag_count and not used_llm:
        reason += f"; {rules.target_tag_count - len(kept)} slots left for a later image pass"
    return FieldSuggestion(kept, confidence, source, flag, reason)
