"""CLI and end-to-end coverage against a mocked Unsplash API."""

from __future__ import annotations

import json
import shutil
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from tests.support import write_jpeg
from upw.adapters.oauth import wait_for_code
from upw.cli import app
from upw.errors import UpwError

runner = CliRunner()


def _project(tmp_path: Path) -> Path:
    shutil.copytree(Path("config"), tmp_path / "config")
    trips = tmp_path / "trips"
    trips.mkdir()
    (trips / "trip.yaml").write_text(
        """
name: Test Trip
collection: Test Trip Collection
description: Lakes and trails.
template: mountain-autumn
tags: [test trip]
days:
  - date: 2026-10-31
    places:
      - name: Five Flower Lake
        city: Jiuzhaigou County
        region: Ngawa
        country: China
        latitude: 33.215
        longitude: 103.917
  - date: 2026-11-01
    places:
      - name: Pearl Shoals
        city: Jiuzhaigou County
        region: Ngawa
        country: China
        latitude: 33.2
        longitude: 103.9
""",
        encoding="utf-8",
    )
    write_jpeg(tmp_path / "originals" / "exif1.jpg", lat=33.215, lon=103.917, when="2026:10:31 10:00:00")
    write_jpeg(tmp_path / "originals" / "burst2.jpg", lat=None, lon=None, when="2026:10:31 10:00:02")
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "UNSPLASH_ACCESS_KEY=test-access-key",
                "UNSPLASH_SECRET_KEY=test-secret-key",
                "UNSPLASH_USER_TOKEN=test-user-token",
                "UNSPLASH_USERNAME=tester",
                "NOMINATIM_USER_AGENT=unsplash-photo-workflow/test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return tmp_path


def _photo(photo_id: str, created: str, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": photo_id,
        "slug": photo_id,
        "created_at": created,
        "width": 4000,
        "height": 3000,
        "description": None,
        "downloads": 0,
        "likes": 0,
        "views": 0,
        "tags": [{"title": "travel photography"}],
        "location": None,
        "urls": {"small": "https://images.unsplash.com/example"},
    }
    payload.update(extra)
    return payload


@respx.mock
def test_run_plans_and_applies(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("UNSPLASH_USER_TOKEN", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    root = _project(tmp_path)
    photos = [
        _photo("exif1", "2026-10-31T08:00:00Z"),
        _photo("burst2", "2026-10-31T08:00:02Z"),
        _photo(
            "popular",
            "2025-05-31",
            downloads=200,
            location={"name": "Myeong-dong", "city": "Seoul", "country": "South Korea"},
            tags=[{"title": "seoul"}, {"title": "street"}],
        ),
        _photo("day2", "2026-11-01"),
    ]
    respx.get(url__regex=r".*/users/tester/photos").mock(return_value=httpx.Response(200, json=photos))
    respx.get(url__regex=r"https://nominatim.openstreetmap.org/reverse").mock(
        return_value=httpx.Response(
            200,
            json={
                "lat": "33.215",
                "lon": "103.917",
                "address": {
                    "tourism": "Five Flower Lake",
                    "county": "Jiuzhaigou County",
                    "state": "Sichuan",
                    "country": "China",
                },
            },
        )
    )
    respx.get(url__regex=r".*/users/tester/collections").mock(return_value=httpx.Response(200, json=[]))
    puts = respx.put(url__regex=r".*/photos/").mock(
        side_effect=lambda request: httpx.Response(
            200,
            json={"id": request.url.path.rsplit("/", 1)[-1], "created_at": "2026-10-31T00:00:00Z", "tags": []},
        )
    )
    creates = respx.post("https://api.unsplash.com/collections").mock(
        side_effect=lambda request: httpx.Response(
            201,
            json={
                "id": "c-" + urllib.parse.parse_qs(request.content.decode())["title"][0][:8],
                "title": urllib.parse.parse_qs(request.content.decode())["title"][0],
                "description": "",
            },
        )
    )
    adds = respx.post(url__regex=r".*/collections/.*/add").mock(return_value=httpx.Response(201, json={}))

    dry = runner.invoke(app, ["run", "--root", str(root), "--no-ai"])
    assert dry.exit_code == 0, dry.stdout + dry.stderr
    assert "Stopped before apply" in dry.stdout
    assert puts.call_count == 0
    assert "test-user-token" not in dry.stdout
    assert "test-user-token" not in dry.stderr
    review = (root / "state" / "review.csv").read_text(encoding="utf-8")
    assert "exif1" in review and "burst2" in review
    assert "five flower lake" in review

    live = runner.invoke(app, ["run", "--root", str(root), "--no-ai", "--yes"])
    assert live.exit_code == 0, live.stdout + live.stderr
    assert "test-user-token" not in live.stderr
    updated = {call.request.url.path.rsplit("/", 1)[-1] for call in puts.calls}
    assert updated == {"exif1", "popular", "day2"}
    assert "burst2" not in updated
    bodies = [urllib.parse.unquote_plus(call.request.content.decode()) for call in puts.calls]
    exif_body = next(body for body in bodies if "five flower lake" in body.lower())
    assert "location[latitude]=" in exif_body
    assert creates.call_count == 2
    assert adds.call_count == 3
    status = runner.invoke(app, ["status", "--root", str(root), "--format", "json"])
    payload = json.loads(status.stdout)
    assert payload["processed"] == 3
    assert payload["failed"] == 0


def test_status_review_and_missing_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("UNSPLASH_USER_TOKEN", raising=False)
    root = _project(tmp_path)
    env = (root / ".env").read_text(encoding="utf-8")
    (root / ".env").write_text(
        "\n".join(line for line in env.splitlines() if not line.startswith("UNSPLASH_USER_TOKEN=")) + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    first = runner.invoke(app, ["status", "--root", str(root), "--format", "json"])
    assert json.loads(first.stdout)["photos"] == 0
    blocked = runner.invoke(app, ["sync", "--root", str(root)])
    assert blocked.exit_code == 2
    assert "UNSPLASH_USER_TOKEN" in blocked.stdout
    missing = runner.invoke(app, ["review", "--root", str(root)])
    assert missing.exit_code == 2


def test_auth_stores_token_without_printing_it(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("upw.cli.secrets.token_urlsafe", lambda _n: "fixed-state")
    monkeypatch.setattr("upw.cli.webbrowser.open", lambda _url: True)
    monkeypatch.delenv("UNSPLASH_USER_TOKEN", raising=False)
    root = tmp_path
    (root / ".env").write_text(
        "UNSPLASH_ACCESS_KEY=test-access-key\nUNSPLASH_SECRET_KEY=test-secret-key\nUNSPLASH_REDIRECT_URI=http://127.0.0.1:18765/callback\n",
        encoding="utf-8",
    )

    def trigger() -> None:
        for _ in range(40):
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:18765/callback?code=auth-code&state=fixed-state",
                    timeout=0.2,
                )
                return
            except OSError:
                time.sleep(0.05)

    with respx.mock:
        respx.post("https://unsplash.com/oauth/token").mock(return_value=httpx.Response(200, json={"access_token": "fresh-user-token"}))
        thread = threading.Thread(target=trigger)
        thread.start()
        result = runner.invoke(app, ["auth", "--root", str(root)])
        thread.join(5)
    assert result.exit_code == 0, result.stdout + result.stderr
    saved = (root / ".env").read_text(encoding="utf-8")
    assert "UNSPLASH_USER_TOKEN=fresh-user-token" in saved
    assert "fresh-user-token" not in result.stdout
    assert "fresh-user-token" not in result.stderr


def test_oauth_rejects_bad_state() -> None:
    def trigger() -> None:
        for _ in range(40):
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:18766/callback?code=nope&state=wrong",
                    timeout=0.2,
                )
                break
            except OSError:
                time.sleep(0.05)
        urllib.request.urlopen(
            "http://127.0.0.1:18766/callback?code=good&state=right",
            timeout=2,
        )

    thread = threading.Thread(target=trigger)
    thread.start()
    try:
        code = wait_for_code("http://127.0.0.1:18766/callback", "right", timeout=5)
    finally:
        thread.join(5)
    assert code == "good"
    try:
        wait_for_code("http://127.0.0.1:18767/callback", "none", timeout=0.2)
    except UpwError as exc:
        assert "Timed out" in str(exc)
    else:
        raise AssertionError("expected timeout")
