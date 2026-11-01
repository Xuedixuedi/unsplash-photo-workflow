import json
from pathlib import Path

from upw.models import parse_location_text, photo_from_api


def test_parse_location_text_splits_country() -> None:
    location = parse_location_text("Jiuzhaigou Valley, Jiuzhaigou County, Ngawa Tibetan and Qiang Autonomous Prefecture, China")
    assert location is not None
    assert location.name == "Jiuzhaigou Valley"
    assert location.city == "Jiuzhaigou County"
    assert location.country == "China"
    assert parse_location_text("Songdo Beach") is not None
    assert parse_location_text("  ") is None


def test_photo_from_api_and_fixture_file() -> None:
    raw = {
        "id": "abc",
        "created_at": "2026-10-31T08:00:00Z",
        "width": 100,
        "height": 80,
        "description": None,
        "downloads": 3,
        "likes": 1,
        "views": 9,
        "tags": [{"title": "Lake"}, "mist"],
        "location": {"name": "Five Flower Lake, Jiuzhaigou County, China", "position": {"latitude": 1.5, "longitude": 2.5}},
        "exif": {"name": "Example body"},
        "urls": {"small": "https://images.unsplash.com/example"},
        "current_user_collections": [{"id": 7, "title": "Autumn"}],
        "show_on_profile": False,
    }
    photo = photo_from_api(raw)
    assert photo.tags == ["Lake", "mist"]
    assert photo.location is not None
    assert photo.location.country == "China"
    assert photo.location.latitude == 1.5
    assert photo.show_on_profile is False
    assert photo.show_on_profile_known is True
    assert photo.collections[0].title == "Autumn"
    assert photo.camera == "Example body"
    again = photo_from_api(photo.to_dict())
    assert again.id == "abc"

    fixture = json.loads(Path("fixtures/photos.json").read_text(encoding="utf-8"))
    parsed = [photo_from_api(item) for item in fixture]
    assert len(parsed) >= 20
    assert any(item.downloads > 100 for item in parsed)
    assert any(item.location is None for item in parsed)


def test_missing_show_on_profile_is_unknown() -> None:
    photo = photo_from_api({"id": "x", "created_at": "2026-01-01"})
    assert photo.show_on_profile is True
    assert photo.show_on_profile_known is False
