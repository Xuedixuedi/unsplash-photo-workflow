"""Apply an approved review plan. Dry-run is the default and writes nothing."""

from __future__ import annotations

from typing import Any, Protocol

from upw.adapters.unsplash import Collection
from upw.models import Location, Photo, PhotoPlan, Plan
from upw.redact import redact
from upw.state.store import StateStore

_YES = {"yes", "y", "true", "1"}


class PhotoApi(Protocol):
    def list_collections(self, username: str) -> list[Collection]: ...

    def create_collection(self, title: str, description: str = "", private: bool = False) -> Collection: ...

    def add_photo(self, collection_id: str, photo_id: str) -> None: ...

    def update_photo(
        self,
        photo_id: str,
        *,
        description: str | None = None,
        show_on_profile: bool | None = None,
        tags: list[str] | None = None,
        location: dict[str, Any] | None = None,
        exif: dict[str, Any] | None = None,
    ) -> Photo: ...


def locations_equal(left: Location | None, right: Location | None) -> bool:
    if left is None or left.is_empty():
        return right is None or right.is_empty()
    if right is None or right.is_empty():
        return False

    def text(value: str | None) -> str:
        return (value or "").strip().casefold()

    # Region is used for tags only. The Unsplash update endpoint has no region field.
    if any(text(getattr(left, field)) != text(getattr(right, field)) for field in ("name", "city", "country")):
        return False
    return _coords_equal(left.latitude, right.latitude) and _coords_equal(left.longitude, right.longitude)


def _coords_equal(left: float | None, right: float | None) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    return abs(left - right) < 1e-5


def tags_equal(left: list[str], right: list[str]) -> bool:
    return [tag.casefold() for tag in left] == [tag.casefold() for tag in right]


def update_payload(photo: Photo, row: PhotoPlan) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    proposed = row.location.value if isinstance(row.location.value, Location) else None
    if proposed is not None and not locations_equal(photo.location, proposed):
        payload["location"] = {
            "name": proposed.name,
            "city": proposed.city,
            "country": proposed.country,
            "latitude": proposed.latitude,
            "longitude": proposed.longitude,
        }
    proposed_tags = [str(tag) for tag in (row.tags.value or [])]
    if proposed_tags and not tags_equal(photo.tags, proposed_tags):
        payload["tags"] = proposed_tags
    description = str(row.description.value or "").strip()
    if description and description != (photo.description or "").strip():
        payload["description"] = description
    proposed_show = bool(row.show_on_profile.value)
    if photo.show_on_profile_known:
        if proposed_show != photo.show_on_profile:
            payload["show_on_profile"] = proposed_show
    elif proposed_show is False:
        payload["show_on_profile"] = False
    return payload


def apply_plan(
    plan: Plan,
    photos: list[Photo],
    store: StateStore,
    *,
    write: bool,
    client: PhotoApi | None,
    username: str,
    run_id: str,
    only_ids: set[str] | None = None,
) -> dict[str, Any]:
    by_id = {photo.id: photo for photo in photos}
    known: dict[str, Collection] = {}
    if client is not None and username:
        for collection in client.list_collections(username):
            known[collection.title.casefold()] = collection
    results: list[dict[str, Any]] = []
    for row in plan.photos:
        if only_ids is not None and row.photo_id not in only_ids:
            continue
        photo = by_id.get(row.photo_id)
        if photo is None:
            results.append(_result(row.photo_id, "failed", ["missing photo in the last sync"], "Photo was not in the sync snapshot."))
            continue
        decision = row.approve.strip().lower()
        if decision == "skip":
            results.append(_result(row.photo_id, "skipped", ["skip"], ""))
            store.mark_processed(row.photo_id, {"status": "skipped", "run_id": run_id})
            continue
        if decision not in _YES:
            results.append(_result(row.photo_id, "needs-review", ["held"], "approve is not yes"))
            continue
        payload = update_payload(photo, row)
        operations: list[str] = []
        if payload:
            operations.append("update")
        collection_op = _collection_op(photo, row, known)
        if collection_op:
            operations.append(collection_op)
        if not operations:
            results.append(_result(row.photo_id, "skipped", ["unchanged"], ""))
            if write:
                store.mark_processed(row.photo_id, {"status": "skipped", "run_id": run_id})
            continue
        if not write:
            if collection_op == "create_collection":
                known[row.collection_title.strip().casefold()] = Collection(id="dry-run", title=row.collection_title.strip())
            results.append(_result(row.photo_id, "dry-run", operations, ""))
            continue
        try:
            if client is None:
                raise RuntimeError("No Unsplash client was configured.")
            if payload:
                client.update_photo(row.photo_id, **payload)
                _remember_update(photo, payload)
            if collection_op:
                collection = _ensure_collection(client, row, known)
                if not any(item.title.casefold() == collection.title.casefold() for item in photo.collections):
                    photo.collections.append(collection.to_ref())
            results.append(_result(row.photo_id, "updated", operations, ""))
            store.mark_processed(
                row.photo_id,
                {"status": "updated", "run_id": run_id, "operations": operations},
            )
        except Exception as exc:
            # One photo must not abort the rest of the batch.
            results.append(_result(row.photo_id, "failed", operations, redact(str(exc))))
    if write:
        store.save_photos(photos)
    report = {"run_id": run_id, "dry_run": not write, "results": results}
    store.save_apply_report(report)
    return report


def _remember_update(photo: Photo, payload: dict[str, Any]) -> None:
    if "location" in payload:
        photo.location = Location.from_dict(payload["location"])
    if "tags" in payload:
        photo.tags = list(payload["tags"])
    if "description" in payload:
        photo.description = str(payload["description"])
    if "show_on_profile" in payload:
        photo.show_on_profile = bool(payload["show_on_profile"])
        photo.show_on_profile_known = True


def _collection_op(photo: Photo, row: PhotoPlan, known: dict[str, Collection]) -> str:
    title = row.collection_title.strip()
    if not title or row.collection_action == "skip":
        return ""
    if any(item.title.casefold() == title.casefold() for item in photo.collections):
        return ""
    if title.casefold() in known:
        return "add_to_collection"
    return "create_collection"


def _ensure_collection(client: PhotoApi, row: PhotoPlan, known: dict[str, Collection]) -> Collection:
    title = row.collection_title.strip()
    collection = known.get(title.casefold())
    if collection is None:
        collection = client.create_collection(title, row.collection_description)
        known[title.casefold()] = collection
    client.add_photo(collection.id, row.photo_id)
    return collection


def _result(photo_id: str, status: str, operations: list[str], error: str) -> dict[str, Any]:
    return {
        "photo_id": photo_id,
        "status": status,
        "operations": operations,
        "error": error,
    }
