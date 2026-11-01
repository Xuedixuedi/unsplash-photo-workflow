from tests.support import photo

from upw.adapters.unsplash import Collection
from upw.core.applier import apply_plan, locations_equal
from upw.core.describe import build_description
from upw.core.planner import (
    build_plan,
    encode_location,
    overlay_csv,
    parse_location_cell,
    write_review_csv,
)
from upw.core.rules import Rules
from upw.models import FieldSuggestion, Location, Plan
from upw.state.store import StateStore


class FakeApi:
    def __init__(self, fail: set[str] | None = None) -> None:
        self.fail = fail or set()
        self.updates: list[tuple[str, dict[str, object]]] = []
        self.created: list[str] = []
        self.added: list[tuple[str, str]] = []
        self.collections: list[Collection] = []

    def list_collections(self, username: str) -> list[Collection]:
        return list(self.collections)

    def create_collection(self, title: str, description: str = "", private: bool = False) -> Collection:
        made = Collection(id=str(len(self.created) + 1), title=title, description=description)
        self.created.append(title)
        self.collections.append(made)
        return made

    def add_photo(self, collection_id: str, photo_id: str) -> None:
        self.added.append((collection_id, photo_id))

    def update_photo(self, photo_id: str, **kwargs: object):  # type: ignore[no-untyped-def]
        if photo_id in self.fail:
            raise RuntimeError(f"boom {photo_id}")
        self.updates.append((photo_id, kwargs))
        return photo(id=photo_id)


def _plan(store: StateStore) -> tuple[Plan, list]:
    rules = Rules()
    shots = [
        photo(id="a", tags=["lake"]),
        photo(id="b", tags=["lake"], downloads=0),
    ]
    locations = {
        "a": FieldSuggestion(Location(name="Lake", country="China", latitude=1, longitude=2), 0.9, "exif", "ok", ""),
        "b": FieldSuggestion(None, 0.0, "none", "empty", "missing"),
    }
    tags = {
        "a": FieldSuggestion(["lake", "china"], 0.86, "deterministic", "ok", ""),
        "b": FieldSuggestion(["lake"], 0.86, "deterministic", "ok", ""),
    }
    descriptions = {
        "a": FieldSuggestion("Lake, China.", 0.8, "template", "ok", ""),
        "b": FieldSuggestion("", 0.0, "none", "empty", ""),
    }
    visibility = {
        "a": FieldSuggestion(True, 0.6, "unchanged", "ok", ""),
        "b": FieldSuggestion(False, 0.72, "rule:burst", "review", "burst"),
    }
    collections = {
        "a": ("Jiuzhaigou Autumn 2026", "Autumn lakes.", "add"),
        "b": ("Jiuzhaigou Autumn 2026", "Autumn lakes.", "add"),
    }
    plan = build_plan(
        run_id="run1",
        photos=shots,
        locations=locations,
        tags=tags,
        descriptions=descriptions,
        visibility=visibility,
        collections=collections,
        rules=rules,
    )
    store.save_photos(shots)
    store.save_plan(plan)
    write_review_csv(plan, store.review_csv_path())
    return plan, shots


def test_csv_round_trip_and_description(tmp_path) -> None:
    assert parse_location_cell(encode_location(Location(name="A|B", city="C", latitude=1.5))).name == "A/B"
    store = StateStore(tmp_path)
    plan, shots = _plan(store)
    assert plan.photos[0].approve == "yes"
    assert plan.photos[1].approve == "no"
    text = store.review_csv_path().read_text(encoding="utf-8")
    text = text.replace("lake|china", "lake|mist")
    store.review_csv_path().write_text(text, encoding="utf-8")
    edited = overlay_csv(plan, store.review_csv_path())
    assert edited.photos[0].tags.value == ["lake", "mist"]
    assert edited.photos[0].tags.source == "human"
    described = build_description(shots[0], Location(name="Lake", city="Jiuzhaigou", country="China"), Rules())
    assert described.value == "Lake, Jiuzhaigou, China."
    kept = build_description(photo(description="Already written."), None, Rules())
    assert kept.source == "existing"


def test_apply_is_idempotent_and_records_failures(tmp_path) -> None:
    store = StateStore(tmp_path / "state")
    plan, shots = _plan(store)
    plan = overlay_csv(plan, store.review_csv_path())
    api = FakeApi()
    report = apply_plan(plan, shots, store, write=False, client=api, username="liuxuedi", run_id="dry")
    assert report["dry_run"] is True
    assert api.updates == []
    assert {item["status"] for item in report["results"]} == {"dry-run", "needs-review"}

    report = apply_plan(plan, store.load_photos(), store, write=True, client=api, username="liuxuedi", run_id="live")
    assert [item["status"] for item in report["results"]] == ["updated", "needs-review"]
    assert api.created == ["Jiuzhaigou Autumn 2026"]
    assert api.added == [("1", "a")]
    assert api.updates[0][0] == "a"
    assert "show_on_profile" not in api.updates[0][1]
    saved = store.load_photos()
    assert saved[0].tags == ["lake", "china"]
    assert saved[0].collections[0].title == "Jiuzhaigou Autumn 2026"
    again = apply_plan(plan, saved, store, write=True, client=api, username="liuxuedi", run_id="again")
    assert again["results"][0]["status"] == "skipped"
    assert len(api.updates) == 1

    failing = FakeApi(fail={"a"})
    # Reset snapshot tags so another update is required, and drop the collection membership.
    shots[0].tags = ["lake"]
    shots[0].collections = []
    shots[0].description = None
    shots[0].location = None
    store.save_photos(shots)
    failed = apply_plan(plan, shots, store, write=True, client=failing, username="liuxuedi", run_id="bad")
    assert failed["results"][0]["status"] == "failed"
    assert store.failed_photo_ids() == {"a"}
    retry = apply_plan(
        plan,
        shots,
        store,
        write=True,
        client=FakeApi(),
        username="liuxuedi",
        run_id="retry",
        only_ids=store.failed_photo_ids(),
    )
    assert [item["photo_id"] for item in retry["results"]] == ["a"]
    assert locations_equal(Location(name="Lake", country="China"), Location(name="lake", country="china"))


def test_skip_marks_processed(tmp_path) -> None:
    store = StateStore(tmp_path)
    plan, shots = _plan(store)
    plan.photos[0].approve = "skip"
    apply_plan(plan, shots, store, write=True, client=FakeApi(), username="u", run_id="s")
    assert "a" in store.processed_ids()
    assert "b" not in store.processed_ids()
