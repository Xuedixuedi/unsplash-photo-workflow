"""Run the suggest stage: locate, tag, describe, group, and write the review plan."""

from __future__ import annotations

from pathlib import Path

from upw.adapters.exif import OriginalIndex, load_track
from upw.adapters.geocoder import NominatimGeocoder
from upw.adapters.llm import LlmClient, shrink_image
from upw.core.describe import build_description
from upw.core.grouper import assign_collections
from upw.core.locate import locate_batch
from upw.core.planner import build_plan, render_table, write_review_csv
from upw.core.rules import burst_roles, decide_visibility, load_rules, load_templates
from upw.core.tagger import build_tags
from upw.core.trips import load_trips, trip_for_day
from upw.models import Location, Plan
from upw.runlog import RunLog
from upw.settings import Settings
from upw.state.store import StateStore


def suggest(
    settings: Settings,
    log: RunLog,
    *,
    no_ai: bool,
    include_processed: bool = False,
) -> Plan:
    store = StateStore(settings.state_dir)
    rules = load_rules(settings.config_dir / "rules.yaml")
    templates = load_templates(settings.config_dir / "tag_templates.yaml")
    trips = load_trips(settings.trips_dir)
    photos = store.load_photos()
    if not include_processed:
        processed = store.processed_ids()
        photos = [photo for photo in photos if photo.id not in processed]
    originals = OriginalIndex(
        settings.originals_dir,
        timezone_name=rules.timezone,
        offset_seconds=rules.camera_clock_offset_seconds,
    )
    for photo in photos:
        local = originals.by_photo_id.get(photo.id)
        if local is None:
            continue
        if local.captured_at:
            photo.captured_at = local.captured_at
        if local.location is not None:
            photo.exif_location = local.location
    phone_points = load_track(settings.phone_source) if settings.phone_source else []
    images = _images(originals, [photo.id for photo in photos])
    llm: LlmClient | None = None
    use_ai = not no_ai and not settings.no_ai and bool(settings.llm_api_key)
    if use_ai:
        llm = LlmClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            cache_path=store.cache_path("llm.json"),
        )
        log.event("info", "LLM enabled for leftover slots", model=settings.llm_model)
    else:
        log.event("info", "AI disabled; using deterministic suggestions only")
    geocoder = NominatimGeocoder(
        cache_path=store.cache_path("geocode.json"),
        user_agent=settings.nominatim_user_agent,
        base_url=settings.nominatim_base,
    )
    try:
        located = locate_batch(photos, trips, phone_points, geocoder, llm, rules, images)
        tagged = {}
        described = {}
        for photo in photos:
            suggestion = located[photo.id]
            location = suggestion.value if isinstance(suggestion.value, Location) else None
            trip = trip_for_day(trips, photo.day())
            day = trip.on(photo.day()) if trip is not None else None
            tagged[photo.id] = build_tags(
                photo,
                location,
                trip,
                day.tags if day is not None else [],
                templates.for_name(trip.template if trip else None),
                rules,
                llm,
                images.get(photo.id),
            )
            described[photo.id] = build_description(photo, location, rules, llm, images.get(photo.id))
        roles = burst_roles(photos, rules)
        visibility = {photo.id: decide_visibility(photo, rules, roles.get(photo.id, "single")) for photo in photos}
        grouped = assign_collections(photos, trips, rules)
        collections = {photo_id: (item.title, item.description, item.action) for photo_id, item in grouped.items()}
        plan = build_plan(
            run_id=log.run_id,
            photos=photos,
            locations=located,
            tags=tagged,
            descriptions=described,
            visibility=visibility,
            collections=collections,
            rules=rules,
        )
    finally:
        geocoder.close()
        if llm is not None:
            llm.close()
    store.save_plan(plan)
    write_review_csv(plan, store.review_csv_path())
    approved = sum(1 for row in plan.photos if row.approve == "yes")
    log.event(
        "info",
        "Wrote the review plan",
        photos=len(plan.photos),
        approved=approved,
        review=str(store.review_csv_path()),
    )
    return plan


def summary_for(plan: Plan, *, applied: bool, stopped: bool) -> str:
    approved = sum(1 for row in plan.photos if row.approve == "yes")
    review = sum(1 for row in plan.photos if row.approve != "yes")
    lines = [
        f"Run {plan.run_id}",
        f"Photos in this plan: {len(plan.photos)}",
        f"Rows marked approve=yes: {approved}",
        f"Rows waiting for review: {review}",
    ]
    if stopped:
        lines.append("Stopped before apply. Edit state/review.csv, then run `upw apply --yes`.")
    elif applied:
        lines.append("Apply finished. See the failed-items list and state/logs for details.")
    lines.append(render_table(plan, limit=15))
    return "\n".join(lines)


def _images(originals: OriginalIndex, photo_ids: list[str]) -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    for photo_id in photo_ids:
        path: Path | None = originals.image_path(photo_id)
        if path is None or not path.exists():
            continue
        found[photo_id] = shrink_image(path.read_bytes())
    return found
