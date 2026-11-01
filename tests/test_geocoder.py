import httpx
import respx

from upw.adapters.geocoder import NominatimGeocoder
from upw.errors import UpwError


def test_requires_user_agent(tmp_path) -> None:
    try:
        NominatimGeocoder(cache_path=tmp_path / "c.json", user_agent="short")
    except UpwError:
        return
    raise AssertionError("expected a user-agent error")


@respx.mock
def test_forward_reverse_throttle_and_cache(tmp_path) -> None:
    sleeps: list[float] = []
    now = {"t": 10.0}

    def clock() -> float:
        return now["t"]

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        now["t"] += seconds

    search = respx.get("https://nominatim.openstreetmap.org/search").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "lat": "33.2",
                    "lon": "103.9",
                    "display_name": "Five Flower Lake, China",
                    "address": {"tourism": "Five Flower Lake", "state": "Sichuan", "country": "China"},
                }
            ],
        )
    )
    reverse = respx.get("https://nominatim.openstreetmap.org/reverse").mock(
        return_value=httpx.Response(
            200,
            json={
                "lat": "33.2",
                "lon": "103.9",
                "address": {"peak": "Mount Omuro", "city": "Ito", "state": "Shizuoka", "country": "Japan"},
            },
        )
    )
    geo = NominatimGeocoder(
        cache_path=tmp_path / "geo.json",
        user_agent="unsplash-photo-workflow/test",
        sleeper=sleeper,
        clock=clock,
    )
    try:
        forward = geo.forward("Five Flower Lake")
        assert forward is not None and forward.name == "Five Flower Lake"
        assert search.calls[0].request.headers["user-agent"] == "unsplash-photo-workflow/test"
        again = geo.forward("  five   flower lake ")
        assert again is not None and again.country == "China"
        assert search.call_count == 1
        place = geo.reverse(33.2, 103.9)
        assert place is not None and place.city == "Ito"
        assert sleeps and sleeps[0] >= 1
        geo.reverse(33.2, 103.9)
        assert reverse.call_count == 1
        assert geo.forward("") is None
    finally:
        geo.close()
