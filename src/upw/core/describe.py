"""Descriptions are templated from the location. The model is a last resort."""

from __future__ import annotations

from upw.adapters.llm import JsonCompleter, suggest_description
from upw.core.rules import Rules
from upw.models import FieldSuggestion, Location, Photo


def build_description(
    photo: Photo,
    location: Location | None,
    rules: Rules,
    llm: JsonCompleter | None = None,
    image: bytes | None = None,
) -> FieldSuggestion:
    if photo.description:
        return FieldSuggestion(
            photo.description,
            0.9,
            "existing",
            "ok",
            "keeping the current description",
        )
    if rules.description_from_location and location is not None and not location.is_empty():
        parts: list[str] = []
        for part in (location.name, location.city, location.country):
            if part and part not in parts:
                parts.append(part)
        if parts:
            return FieldSuggestion(
                ", ".join(parts) + ".",
                0.8,
                "template",
                "ok",
                "built from the location",
            )
    context = ""
    if location is not None and not location.is_empty():
        context = ", ".join(part for part in (location.name, location.city, location.country) if part)
    if llm is not None:
        text = suggest_description(llm, photo_id=photo.id, context=context, image=image)
        if text:
            return FieldSuggestion(text, 0.5, "llm", "review", "model wrote the description")
    return FieldSuggestion("", 0.0, "none", "empty", "no description")
