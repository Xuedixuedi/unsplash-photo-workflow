"""Unsplash API client: OAuth, photos, and collections.

Rate-limit headers are read on every response. When the remaining budget hits
zero the client sleeps until the documented reset (or Retry-After) when that
wait is short, and otherwise records a resume time so a later run can continue.
"""

from __future__ import annotations

import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from upw.errors import RateLimitError, UpwError
from upw.models import CollectionRef, Photo, photo_from_api
from upw.redact import redact

SCOPES = "public read_user write_photos write_collections"


@dataclass
class Collection:
    id: str
    title: str
    description: str = ""

    def to_ref(self) -> CollectionRef:
        return CollectionRef(id=self.id, title=self.title)


def authorize_url(
    *,
    access_key: str,
    redirect_uri: str,
    oauth_base: str = "https://unsplash.com",
    state: str,
    scope: str = SCOPES,
) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": access_key,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "state": state,
        }
    )
    return f"{oauth_base.rstrip('/')}/oauth/authorize?{query}"


class UnsplashClient:
    def __init__(
        self,
        *,
        access_key: str,
        user_token: str,
        api_base: str = "https://api.unsplash.com",
        oauth_base: str = "https://unsplash.com",
        sleeper: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
        max_retries: int = 4,
        max_sleep: float = 90,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.access_key = access_key
        self.user_token = user_token
        self.api_base = api_base.rstrip("/")
        self.oauth_base = oauth_base.rstrip("/")
        self.sleeper = sleeper or time.sleep
        self.clock = clock or time.time
        self.max_retries = max_retries
        self.max_sleep = max_sleep
        self.remaining: int | None = None
        self.limit: int | None = None
        self.resume_at: float | None = None
        headers = {"Accept-Version": "v1"}
        if user_token:
            headers["Authorization"] = f"Bearer {user_token}"
        elif access_key:
            headers["Authorization"] = f"Client-ID {access_key}"
        self.http = httpx.Client(
            base_url=self.api_base,
            headers=headers,
            timeout=30.0,
            transport=transport,
        )

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> UnsplashClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def exchange_code(
        self,
        *,
        client_secret: str,
        redirect_uri: str,
        code: str,
    ) -> str:
        response = httpx.post(
            f"{self.oauth_base}/oauth/token",
            data={
                "client_id": self.access_key,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=30.0,
        )
        if response.status_code >= 400:
            raise UpwError(f"Unsplash token exchange failed ({response.status_code}).")
        payload = response.json()
        token = str(payload.get("access_token") or "")
        if not token:
            raise UpwError("Unsplash token response did not include an access token.")
        return token

    def _note_limits(self, headers: httpx.Headers) -> None:
        remaining = headers.get("X-Ratelimit-Remaining")
        limit = headers.get("X-Ratelimit-Limit")
        if remaining is not None and remaining.isdigit():
            self.remaining = int(remaining)
        if limit is not None and limit.isdigit():
            self.limit = int(limit)
        reset = headers.get("X-Ratelimit-Reset")
        if reset and reset.isdigit():
            stamp = int(reset)
            now = self.clock()
            # Accept either a unix timestamp or a small delay in seconds.
            self.resume_at = float(stamp if stamp > 1_000_000_000 else now + stamp)

    def _rate_limited(self, response: httpx.Response) -> bool:
        if response.status_code == 429:
            return True
        if response.status_code != 403:
            return False
        body = response.text.lower()
        return "rate limit" in body

    def _wait(self, seconds: float) -> None:
        delay = max(0.0, seconds)
        if delay > self.max_sleep:
            resume = self.clock() + delay
            self.resume_at = resume
            raise RateLimitError(
                f"Unsplash rate limit reached. Re-run this command after {int(delay)} seconds to resume.",
                retry_at=resume,
            )
        if delay:
            self.sleeper(delay)

    def _respect_budget(self) -> None:
        now = self.clock()
        if self.resume_at is not None and self.resume_at > now and (self.remaining or 0) <= 0:
            self._wait(self.resume_at - now)
            self.remaining = None
            return
        if self.remaining == 0:
            if self.resume_at and self.resume_at > now:
                self._wait(self.resume_at - now)
            else:
                # The documented window is one hour. Sleep to the next hour
                # only when that wait is short enough for this process.
                wait = 3600 - (now % 3600)
                self._wait(wait)
            self.remaining = None

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error = "request failed"
        for attempt in range(self.max_retries):
            self._respect_budget()
            try:
                response = self.http.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                last_error = redact(str(exc))
                self._wait(min(self.max_sleep, 0.5 * (2**attempt)))
                continue
            self._note_limits(response.headers)
            if self._rate_limited(response) or response.status_code in {500, 502, 503, 504}:
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.replace(".", "", 1).isdigit():
                    delay = float(retry_after)
                    # The server named the wait, so don't also block for the whole hour.
                    self.remaining = None
                    self.resume_at = None
                else:
                    delay = min(self.max_sleep, 0.5 * (2**attempt))
                last_error = f"HTTP {response.status_code}"
                if attempt == self.max_retries - 1:
                    break
                self._wait(delay)
                continue
            if response.status_code == 401:
                raise UpwError("Unsplash rejected the user token (401). Run `upw auth` again.")
            if response.status_code >= 400:
                raise UpwError(f"Unsplash {method} {url} failed ({response.status_code}).")
            return response
        raise RateLimitError(f"Unsplash request failed after retries: {last_error}")

    def me(self) -> dict[str, Any]:
        response = self.request("GET", "/me")
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def list_collections(self, username: str) -> list[Collection]:
        found: list[Collection] = []
        page = 1
        while True:
            response = self.request(
                "GET",
                f"/users/{username}/collections",
                params={"page": page, "per_page": 30},
            )
            batch = response.json()
            if not isinstance(batch, list) or not batch:
                break
            for item in batch:
                if isinstance(item, dict):
                    found.append(
                        Collection(
                            id=str(item.get("id")),
                            title=str(item.get("title") or ""),
                            description=str(item.get("description") or ""),
                        )
                    )
            if len(batch) < 30:
                break
            page += 1
            if page > 50:
                break
        return found

    def list_user_photos(self, username: str) -> list[Photo]:
        photos: list[Photo] = []
        page = 1
        while page <= 100:
            response = self.request(
                "GET",
                f"/users/{username}/photos",
                params={"page": page, "per_page": 30, "order_by": "latest"},
            )
            batch = response.json()
            if not isinstance(batch, list) or not batch:
                break
            photos.extend(photo_from_api(item) for item in batch if isinstance(item, dict))
            if len(batch) < 30:
                break
            page += 1
        return photos

    def get_photo(self, photo_id: str) -> Photo:
        response = self.request("GET", f"/photos/{photo_id}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise UpwError(f"Unexpected photo payload for {photo_id}.")
        return photo_from_api(payload)

    def update_photo(
        self,
        photo_id: str,
        *,
        description: str | None = None,
        show_on_profile: bool | None = None,
        tags: list[str] | None = None,
        location: dict[str, Any] | None = None,
        exif: dict[str, Any] | None = None,
    ) -> Photo:
        form: list[tuple[str, str]] = []
        if description is not None:
            form.append(("description", description))
        if show_on_profile is not None:
            form.append(("show_on_profile", "true" if show_on_profile else "false"))
        for tag in tags or []:
            form.append(("tags[]", tag))
        if location:
            for key in ("latitude", "longitude", "name", "city", "country"):
                value = location.get(key)
                if value is None or value == "":
                    continue
                if key in {"latitude", "longitude"}:
                    form.append((f"location[{key}]", f"{float(value):.6f}"))
                else:
                    form.append((f"location[{key}]", str(value)))
        if exif:
            for key, value in exif.items():
                if value is not None:
                    form.append((f"exif[{key}]", str(value)))
        encoded = urllib.parse.urlencode(form).encode()
        response = self.request(
            "PUT",
            f"/photos/{photo_id}",
            content=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        payload = response.json()
        if isinstance(payload, dict) and payload.get("id"):
            return photo_from_api(payload)
        return self.get_photo(photo_id)

    def create_collection(self, title: str, description: str = "", private: bool = False) -> Collection:
        response = self.request(
            "POST",
            "/collections",
            data={
                "title": title,
                "description": description,
                "private": "true" if private else "false",
            },
        )
        return _collection(response.json())

    def update_collection(
        self,
        collection_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        private: bool | None = None,
    ) -> Collection:
        form: dict[str, str] = {}
        if title is not None:
            form["title"] = title
        if description is not None:
            form["description"] = description
        if private is not None:
            form["private"] = "true" if private else "false"
        response = self.request("PUT", f"/collections/{collection_id}", data=form)
        return _collection(response.json())

    def add_photo(self, collection_id: str, photo_id: str) -> None:
        # Adding a photo that is already in the collection is a no-op on Unsplash.
        self.request(
            "POST",
            f"/collections/{collection_id}/add",
            data={"photo_id": photo_id},
        )

    def remove_photo(self, collection_id: str, photo_id: str) -> None:
        self.request(
            "DELETE",
            f"/collections/{collection_id}/remove",
            params={"photo_id": photo_id},
        )


def _collection(payload: Any) -> Collection:
    if not isinstance(payload, dict):
        raise UpwError("Unexpected collection payload.")
    return Collection(
        id=str(payload.get("id")),
        title=str(payload.get("title") or ""),
        description=str(payload.get("description") or ""),
    )
