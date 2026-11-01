import httpx
import respx

from upw.adapters.unsplash import UnsplashClient, authorize_url
from upw.errors import RateLimitError, UpwError

PHOTO = {
    "id": "abc",
    "created_at": "2026-10-31T00:00:00Z",
    "width": 10,
    "height": 10,
    "tags": [{"title": "lake"}],
    "downloads": 0,
    "likes": 0,
    "views": 0,
}


def _client(**kwargs: object) -> UnsplashClient:
    values = {
        "access_key": "access-key",
        "user_token": "user-token",
        "sleeper": lambda _seconds: None,
        "clock": lambda: 1_700_000_000.0,
        "max_sleep": 100,
    }
    values.update(kwargs)
    return UnsplashClient(**values)  # type: ignore[arg-type]


def test_authorize_url_contains_scopes() -> None:
    url = authorize_url(
        access_key="app-key",
        redirect_uri="http://127.0.0.1:8787/callback",
        state="xyz",
    )
    assert url.startswith("https://unsplash.com/oauth/authorize?")
    assert "client_id=app-key" in url
    assert "write_photos" in url
    assert "write_collections" in url
    assert "state=xyz" in url


@respx.mock
def test_exchange_and_photo_crud() -> None:
    respx.post("https://unsplash.com/oauth/token").mock(return_value=httpx.Response(200, json={"access_token": "token-value"}))
    respx.get("https://api.unsplash.com/me").mock(return_value=httpx.Response(200, json={"username": "liuxuedi"}))
    respx.get("https://api.unsplash.com/users/liuxuedi/photos").mock(
        side_effect=[
            httpx.Response(200, json=[PHOTO, {**PHOTO, "id": "def"}]),
            httpx.Response(200, json=[]),
        ]
    )
    respx.get("https://api.unsplash.com/photos/abc").mock(return_value=httpx.Response(200, json=PHOTO))
    update = respx.put("https://api.unsplash.com/photos/abc").mock(return_value=httpx.Response(200, json=PHOTO))
    respx.get("https://api.unsplash.com/users/liuxuedi/collections").mock(
        return_value=httpx.Response(200, json=[{"id": 4, "title": "Autumn", "description": "lakes"}])
    )
    created = respx.post("https://api.unsplash.com/collections").mock(
        return_value=httpx.Response(201, json={"id": 9, "title": "New", "description": "d"})
    )
    respx.put("https://api.unsplash.com/collections/9").mock(
        return_value=httpx.Response(200, json={"id": 9, "title": "New", "description": "edited"})
    )
    added = respx.post("https://api.unsplash.com/collections/9/add").mock(return_value=httpx.Response(201, json={"id": 9}))
    removed = respx.delete("https://api.unsplash.com/collections/9/remove").mock(return_value=httpx.Response(204))
    with _client() as client:
        assert client.exchange_code(client_secret="secret", redirect_uri="http://127.0.0.1/callback", code="c") == "token-value"
        assert client.me()["username"] == "liuxuedi"
        photos = client.list_user_photos("liuxuedi")
        assert [photo.id for photo in photos] == ["abc", "def"]
        assert client.get_photo("abc").id == "abc"
        client.update_photo(
            "abc",
            description="A lake.",
            show_on_profile=False,
            tags=["lake", "china"],
            location={"latitude": 33.2, "longitude": 103.9, "name": "Lake", "city": "Jiuzhaigou", "country": "China"},
        )
        body = update.calls[0].request.content.decode()
        assert "description=A+lake." in body or "description=A+lake" in body
        assert "show_on_profile=false" in body
        assert "tags%5B%5D=lake" in body
        assert "location%5Blatitude%5D=33.200000" in body
        collections = client.list_collections("liuxuedi")
        assert collections[0].title == "Autumn"
        made = client.create_collection("New", "d")
        assert made.id == "9"
        assert created.called
        edited = client.update_collection("9", title="New", description="edited", private=False)
        assert edited.description == "edited"
        client.add_photo("9", "abc")
        client.remove_photo("9", "abc")
        assert added.called and removed.called


@respx.mock
def test_retries_rate_limit_then_succeeds() -> None:
    sleeps: list[float] = []
    respx.get("https://api.unsplash.com/me").mock(
        side_effect=[
            httpx.Response(
                403,
                json={"errors": ["Rate Limit Exceeded"]},
                headers={"X-Ratelimit-Remaining": "0", "Retry-After": "3"},
            ),
            httpx.Response(200, json={"username": "liuxuedi"}, headers={"X-Ratelimit-Remaining": "10"}),
        ]
    )
    with _client(sleeper=sleeps.append) as client:
        assert client.me()["username"] == "liuxuedi"
    assert sleeps == [3.0]


@respx.mock
def test_sleeps_when_budget_is_already_empty() -> None:
    now = {"t": 1_700_000_000.0}
    sleeps: list[float] = []

    def clock() -> float:
        return now["t"]

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        now["t"] += seconds

    respx.get("https://api.unsplash.com/me").mock(
        side_effect=[
            httpx.Response(
                200,
                json={"username": "a"},
                headers={"X-Ratelimit-Remaining": "0", "X-Ratelimit-Reset": "1700000030"},
            ),
            httpx.Response(200, json={"username": "b"}, headers={"X-Ratelimit-Remaining": "9"}),
        ]
    )
    with _client(clock=clock, sleeper=sleeper, max_sleep=100) as client:
        assert client.me()["username"] == "a"
        assert client.me()["username"] == "b"
    assert sleeps == [30.0]


@respx.mock
def test_long_wait_raises_and_can_resume() -> None:
    respx.get("https://api.unsplash.com/me").mock(
        return_value=httpx.Response(
            200,
            json={"username": "a"},
            headers={"X-Ratelimit-Remaining": "0"},
        )
    )
    with _client(clock=lambda: 1_700_000_100.0, max_sleep=10) as client:
        client.me()
        try:
            client.me()
        except RateLimitError as exc:
            assert exc.retry_at is not None
            return
    raise AssertionError("expected a rate limit error")


@respx.mock
def test_unauthorized_and_missing_token() -> None:
    respx.get("https://api.unsplash.com/me").mock(return_value=httpx.Response(401, json={"errors": ["no"]}))
    with _client() as client:
        try:
            client.me()
        except UpwError as exc:
            assert "401" in str(exc)
        else:
            raise AssertionError("expected 401")
    respx.post("https://unsplash.com/oauth/token").mock(return_value=httpx.Response(401, text="no"))
    with _client() as client:
        try:
            client.exchange_code(client_secret="s", redirect_uri="http://localhost", code="c")
        except UpwError as exc:
            assert "token" in str(exc).lower()
        else:
            raise AssertionError("expected token error")
