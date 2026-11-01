"""OpenStreetMap Nominatim forward and reverse geocoding.

The public service requires a descriptive User-Agent and at most one request
per second. Results are cached on disk so a re-run does not repeat lookups.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from upw.errors import UpwError
from upw.models import Location

_MIN_INTERVAL = 1.0


class NominatimGeocoder:
    def __init__(
        self,
        *,
        cache_path: Path,
        user_agent: str,
        base_url: str = "https://nominatim.openstreetmap.org",
        sleeper: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not user_agent or len(user_agent) < 8:
            raise UpwError("Set NOMINATIM_USER_AGENT to a descriptive User-Agent before geocoding.")
        self.cache_path = cache_path
        self.user_agent = user_agent
        self.base_url = base_url.rstrip("/")
        self.sleeper = sleeper or time.sleep
        self.clock = clock or time.monotonic
        self._last = 0.0
        self._cache = self._load()
        self._owns_client = client is None
        self.http = client or httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=30.0,
        )

    def close(self) -> None:
        if self._owns_client:
            self.http.close()

    def _load(self) -> dict[str, Any]:
        if not self.cache_path.exists():
            return {}
        raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache, indent=2) + "\n", encoding="utf-8")

    def _throttle(self) -> None:
        elapsed = self.clock() - self._last
        if self._last and elapsed < _MIN_INTERVAL:
            self.sleeper(_MIN_INTERVAL - elapsed)
        self._last = self.clock()

    def _get(self, path: str, params: dict[str, str]) -> Any:
        self._throttle()
        response = self.http.get(f"{self.base_url}{path}", params=params)
        response.raise_for_status()
        return response.json()

    def forward(self, query: str) -> Location | None:
        query = " ".join(query.split())
        if not query:
            return None
        key = "fwd:" + query.casefold()
        if key in self._cache:
            return Location.from_dict(self._cache[key])
        payload = self._get(
            "/search",
            {"q": query, "format": "jsonv2", "limit": "1", "addressdetails": "1"},
        )
        location = None
        if isinstance(payload, list) and payload:
            location = location_from_nominatim(payload[0])
        self._cache[key] = None if location is None else location.to_dict()
        self._save()
        return location

    def reverse(self, latitude: float, longitude: float) -> Location | None:
        key = f"rev:{latitude:.5f},{longitude:.5f}"
        if key in self._cache:
            return Location.from_dict(self._cache[key])
        payload = self._get(
            "/reverse",
            {
                "lat": f"{latitude:.6f}",
                "lon": f"{longitude:.6f}",
                "format": "jsonv2",
                "addressdetails": "1",
            },
        )
        location = location_from_nominatim(payload) if isinstance(payload, dict) else None
        if location is not None and location.latitude is None:
            location.latitude = latitude
            location.longitude = longitude
        self._cache[key] = None if location is None else location.to_dict()
        self._save()
        return location


def location_from_nominatim(data: dict[str, Any]) -> Location | None:
    if data.get("error"):
        return None
    address_raw = data.get("address")
    address: dict[str, Any] = address_raw if isinstance(address_raw, dict) else {}
    name = (
        address.get("tourism")
        or address.get("attraction")
        or address.get("peak")
        or address.get("water")
        or address.get("natural")
        or address.get("historic")
        or data.get("name")
    )
    city = address.get("city") or address.get("town") or address.get("village") or address.get("municipality") or address.get("county")
    region = address.get("state")
    country = address.get("country")
    latitude = _float(data.get("lat"))
    longitude = _float(data.get("lon"))
    if not name:
        display = str(data.get("display_name") or "")
        name = display.split(",")[0].strip() or None
    location = Location(
        name=_text(name),
        city=_text(city),
        region=_text(region),
        country=_text(country),
        latitude=latitude,
        longitude=longitude,
    )
    return None if location.is_empty() else location


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
