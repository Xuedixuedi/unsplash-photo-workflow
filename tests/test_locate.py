from datetime import date, datetime

from tests.support import photo, trip_one
from upw.adapters.exif import TrackPoint
from upw.core.locate import locate_batch
from upw.core.rules import Rules
from upw.models import Location, Place, Trip, TripDay


class Geo:
    def __init__(self) -> None:
        self.calls = 0

    def reverse(self, latitude: float, longitude: float) -> Location:
        self.calls += 1
        return Location(name="Five Flower Lake", city="Jiuzhaigou County", country="China", latitude=latitude, longitude=longitude)

    def forward(self, query: str) -> Location | None:
        return None


class Llm:
    def __init__(self, place: str | None) -> None:
        self.place = place

    def complete_json(self, *, photo_id: str, purpose: str, prompt: str, image: bytes | None) -> dict[str, object]:
        return {"place": self.place}


def test_chain_order() -> None:
    rules = Rules()
    geo = Geo()
    exif = photo(
        id="exif",
        exif_location=Location(latitude=33.2, longitude=103.9),
        captured_at="2026-10-31T02:00:00Z",
    )
    phone = photo(id="phone", captured_at="2026-10-31T03:00:00Z")
    kept = photo(id="kept", location=Location(name="Seoul", country="South Korea"))
    single = photo(id="single", created_at="2026-11-01")
    neighbour = photo(id="near", captured_at="2026-10-31T02:00:30Z")
    ambiguous = photo(id="amb", captured_at="2026-12-01T01:00:00Z")
    empty = photo(id="empty", created_at="2020-01-01")
    trips = [
        trip_one("2026-11-01"),
        Trip(
            name="Two places",
            collection_name="Two",
            days=[
                TripDay(
                    day=date(2026, 12, 1),
                    places=[
                        Place(name="Five Flower Lake", country="China"),
                        Place(name="Pearl Shoals", country="China"),
                    ],
                )
            ],
        ),
    ]
    points = [
        TrackPoint(
            captured_at=datetime.fromisoformat("2026-10-31T03:00:10+00:00"),
            latitude=35.0,
            longitude=129.0,
        )
    ]
    found = locate_batch(
        [exif, phone, kept, single, neighbour, ambiguous, empty],
        trips,
        points,
        geo,
        Llm("Pearl Shoals"),
        rules,
        images={"amb": b"jpeg"},
    )
    assert found["exif"].source == "exif" and found["exif"].value.name == "Five Flower Lake"
    assert geo.calls == 2
    assert found["phone"].source == "phone"
    assert found["kept"].source == "existing"
    assert found["single"].source == "itinerary"
    assert found["near"].source == "neighbour" and found["near"].flag == "review"
    assert found["amb"].source == "llm" and found["amb"].value.name == "Pearl Shoals"
    assert found["empty"].flag == "empty"


def test_ambiguous_without_ai_stays_empty() -> None:
    trip = Trip(
        name="Two",
        collection_name="Two",
        days=[
            TripDay(
                day=date(2026, 10, 31),
                places=[Place(name="A", country="China"), Place(name="B", country="China")],
            )
        ],
    )
    found = locate_batch([photo(id="x", created_at="2026-10-31")], [trip], [], None, None, Rules(), None)
    assert found["x"].source == "ambiguous"
    assert found["x"].value is None
