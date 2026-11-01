"""Optional OpenAI-compatible JSON client.

The provider is a small interface so another backend can be plugged in.
Calls are cached by photo id plus a hash of the prompt (and image bytes).
Pass no client, or run with --no-ai, and the rest of the pipeline stays deterministic.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any, Protocol

import httpx

from upw.errors import UpwError

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class JsonCompleter(Protocol):
    def complete_json(
        self,
        *,
        photo_id: str,
        purpose: str,
        prompt: str,
        image: bytes | None,
    ) -> dict[str, Any]:
        """Return a JSON object. Implementations may hit the cache."""


class LlmClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        cache_path: Path,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise UpwError("LLM_API_KEY is empty.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.cache_path = cache_path
        self._cache = self._load()
        self._owns_client = client is None
        self.http = client or httpx.Client(timeout=60.0)

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
        self.cache_path.write_text(json.dumps(self._cache) + "\n", encoding="utf-8")

    def complete_json(
        self,
        *,
        photo_id: str,
        purpose: str,
        prompt: str,
        image: bytes | None,
    ) -> dict[str, Any]:
        image_hash = hashlib.sha256(image).hexdigest() if image else ""
        material = "\n".join([photo_id, purpose, self.model, prompt, image_hash])
        key = hashlib.sha256(material.encode("utf-8")).hexdigest()
        if key in self._cache and isinstance(self._cache[key], dict):
            return self._cache[key]
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if image:
            small = shrink_image(image)
            encoded = base64.b64encode(small).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                }
            )
        response = self.http.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": "Reply with one JSON object and nothing else.",
                    },
                    {"role": "user", "content": content},
                ],
            },
        )
        if response.status_code >= 400:
            raise UpwError(f"LLM request failed ({response.status_code}).")
        payload = response.json()
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise UpwError("LLM response did not include a message.") from exc
        parsed = parse_json_object(text)
        self._cache[key] = parsed
        self._save()
        return parsed


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = _FENCE.sub("", text.strip())
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise UpwError("LLM response was not JSON.")
    payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise UpwError("LLM response was not a JSON object.")
    return payload


def shrink_image(data: bytes, *, max_edge: int = 512) -> bytes:
    """Return a small JPEG so a vision call does not send the original file."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return data
    with Image.open(io.BytesIO(data)) as opened:
        converted = opened.convert("RGB")
        converted.thumbnail((max_edge, max_edge))
        buffer = io.BytesIO()
        converted.save(buffer, format="JPEG", quality=70)
        return buffer.getvalue()


def choose_place(client: JsonCompleter, *, photo_id: str, names: list[str], image: bytes | None) -> str | None:
    if not names or image is None:
        return None
    prompt = (
        "Choose the single place that best matches the photograph. "
        "You may only pick a name from this list, or null if none fit. "
        'Reply as {"place": "<name or null>"}.\nCandidates:\n' + "\n".join(f"- {name}" for name in names)
    )
    payload = client.complete_json(photo_id=photo_id, purpose="place", prompt=prompt, image=image)
    chosen = payload.get("place")
    if not isinstance(chosen, str):
        return None
    for name in names:
        if name.casefold() == chosen.strip().casefold():
            return name
    return None


def suggest_tags(
    client: JsonCompleter,
    *,
    photo_id: str,
    existing: list[str],
    need: int,
    image: bytes | None,
) -> list[str]:
    if need <= 0 or image is None:
        return []
    prompt = (
        f"Suggest up to {need} subject tags that are visible in the image. "
        "Lowercase, 1 to 3 words, no hashtags, no camera brands. "
        "Do not repeat existing tags. "
        'Reply as {"tags": ["..."]}.\nExisting:\n' + ", ".join(existing)
    )
    payload = client.complete_json(photo_id=photo_id, purpose="tags", prompt=prompt, image=image)
    raw = payload.get("tags")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if isinstance(item, str)]


def suggest_description(
    client: JsonCompleter,
    *,
    photo_id: str,
    context: str,
    image: bytes | None,
) -> str | None:
    if image is None and not context.strip():
        return None
    prompt = (
        "Write one factual sentence describing the photograph for Unsplash. "
        "Do not invent a place that is not in the context. "
        'Reply as {"description": "..."}.\nContext:\n' + context
    )
    payload = client.complete_json(photo_id=photo_id, purpose="description", prompt=prompt, image=image)
    text = payload.get("description")
    if not isinstance(text, str):
        return None
    cleaned = " ".join(text.split())
    return cleaned or None
