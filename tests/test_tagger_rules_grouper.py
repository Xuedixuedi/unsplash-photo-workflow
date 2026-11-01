from datetime import date

from tests.support import photo, trip_one
from upw.core.grouper import assign_collections
from upw.core.rules import Rules, burst_roles, decide_visibility, load_rules, load_templates
from upw.core.tagger import build_tags, normalize_tag
from upw.core.trips import load_trips
from upw.models import Location, Trip


def test_normalize_and_fill_tags() -> None:
    rules = Rules(target_tag_count=6)
    assert normalize_tag("#Lake", brands=rules.camera_brands, max_words=3) is None
    assert normalize_tag("Canon EOS", brands=rules.camera_brands, max_words=3) is None
    assert normalize_tag("unesco world heritage site", brands=rules.camera_brands, max_words=5) == "unesco world heritage site"
    assert normalize_tag("a b c d", brands=rules.camera_brands, max_words=3) is None
    shot = photo(tags=["Jiuzhaigou", "jiuzhaigou", "Canon", "Travel Photography"])
    suggestion = build_tags(
        shot,
        Location(name="Five Flower Lake", city="Jiuzhaigou County", region="Ngawa", country="China"),
        trip_one(),
        ["colorful lakes"],
        ["autumn foliage", "alpine lakes"],
        rules,
    )
    assert suggestion.source == "deterministic"
    assert suggestion.value[0] == "jiuzhaigou"
    assert suggestion.value.count("jiuzhaigou") == 1
    assert "canon" not in suggestion.value
    assert "five flower lake" in suggestion.value
    assert "china" in suggestion.value
    assert len(suggestion.value) <= 6


def test_llm_only_fills_remaining_slots() -> None:
    class Llm:
        def complete_json(self, *, photo_id: str, purpose: str, prompt: str, image: bytes | None) -> dict[str, object]:
            return {"tags": ["misty forest", "Canon", "one two three four"]}

    rules = Rules(target_tag_count=4)
    shot = photo(tags=["lake", "forest", "path"])
    suggestion = build_tags(shot, None, None, [], [], rules, Llm(), b"img")
    assert suggestion.value == ["lake", "forest", "path", "misty forest"]
    assert suggestion.flag == "review"
    full = build_tags(photo(tags=["a", "b"]), None, None, [], [], Rules(target_tag_count=2), Llm(), b"img")
    assert full.source == "deterministic"


def test_visibility_rules_and_bursts() -> None:
    rules = Rules(never_hide_above_downloads=100, burst_seconds=4)
    popular = photo(id="pop", downloads=101, captured_at="2026-10-31T03:00:00Z")
    extra = photo(id="extra", downloads=0, captured_at="2026-10-31T02:00:02Z")
    keeper = photo(id="keep", downloads=3, captured_at="2026-10-31T02:00:01Z", likes=2)
    roles = burst_roles([popular, extra, keeper], rules)
    assert roles["keep"] == "keeper"
    assert roles["extra"] == "extra"
    assert roles["pop"] == "single"
    assert decide_visibility(popular, rules, "extra").value is True
    assert decide_visibility(popular, rules, "extra").source == "rule:downloads"
    hidden = decide_visibility(extra, rules, "extra")
    assert hidden.value is False and hidden.flag == "review"
    forced = photo(id="hide-me", downloads=0)
    custom = Rules(force_hide_ids=("hide-me",))
    assert decide_visibility(forced, custom, "single").value is False


def test_grouper_uses_trip_then_clusters() -> None:
    rules = Rules(cluster_gap_days=2)
    matched = photo(id="a", created_at="2026-10-31")
    left = photo(id="b", created_at="2025-01-01")
    right = photo(id="c", created_at="2025-01-02")
    far = photo(id="d", created_at="2025-02-01")
    groups = assign_collections([matched, left, right, far], [trip_one()], rules)
    assert groups["a"].title == "Jiuzhaigou Autumn 2026"
    assert groups["b"].title == groups["c"].title
    assert groups["d"].title != groups["b"].title
    assert "2025-02-01" in groups["d"].title


def test_example_configs_load() -> None:
    rules = load_rules(__import__("pathlib").Path("config/rules.yaml"))
    assert rules.never_hide_above_downloads == 100
    templates = load_templates(__import__("pathlib").Path("config/tag_templates.yaml"))
    assert "alpine lakes" in templates.for_name("mountain-autumn")
    trips = load_trips(__import__("pathlib").Path("trips"))
    assert any(isinstance(trip, Trip) and trip.collection_name == "Jiuzhaigou Autumn 2026" for trip in trips)
    example = next(trip for trip in trips if trip.name == "Jiuzhaigou Autumn")
    assert example.on(date(2026, 10, 31)) is not None
    assert len(example.on(date(2026, 10, 31)).places) == 2
