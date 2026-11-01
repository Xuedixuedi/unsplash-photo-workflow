"""JSON files under the gitignored state directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from upw.errors import UpwError
from upw.models import Photo, Plan


class StateStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "cache").mkdir(parents=True, exist_ok=True)
        (self.root / "logs").mkdir(parents=True, exist_ok=True)

    def _read(self, name: str, default: Any) -> Any:
        path = self.root / name
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, name: str, payload: Any) -> None:
        path = self.root / name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def save_username(self, username: str) -> None:
        self._write("account.json", {"username": username})

    def load_username(self) -> str:
        raw = self._read("account.json", {})
        if isinstance(raw, dict):
            return str(raw.get("username") or "")
        return ""

    def save_photos(self, photos: list[Photo]) -> None:
        self._write("photos.json", [photo.to_dict() for photo in photos])

    def load_photos(self) -> list[Photo]:
        raw = self._read("photos.json", [])
        return [Photo.from_dict(item) for item in raw]

    def processed_map(self) -> dict[str, Any]:
        raw = self._read("processed.json", {})
        return raw if isinstance(raw, dict) else {}

    def processed_ids(self) -> set[str]:
        return set(self.processed_map())

    def mark_processed(self, photo_id: str, info: dict[str, Any]) -> None:
        current = self.processed_map()
        current[photo_id] = info
        self._write("processed.json", current)

    def save_plan(self, plan: Plan) -> None:
        self._write("review.json", plan.to_dict())

    def load_plan(self) -> Plan:
        raw = self._read("review.json", None)
        if not isinstance(raw, dict):
            raise UpwError("No review plan yet. Run `upw suggest` first.")
        return Plan.from_dict(raw)

    def review_csv_path(self) -> Path:
        return self.root / "review.csv"

    def save_apply_report(self, report: dict[str, Any]) -> None:
        history = self._read("apply_results.json", [])
        if not isinstance(history, list):
            history = []
        history.append(report)
        self._write("apply_results.json", history)
        self._write("apply_last.json", report)

    def last_apply_report(self) -> dict[str, Any] | None:
        raw = self._read("apply_last.json", None)
        return raw if isinstance(raw, dict) else None

    def failed_photo_ids(self) -> set[str]:
        report = self.last_apply_report()
        if not report:
            return set()
        return {
            str(item.get("photo_id")) for item in report.get("results") or [] if item.get("status") == "failed" and item.get("photo_id")
        }

    def save_rate_limit(self, payload: dict[str, Any]) -> None:
        self._write("rate_limit.json", payload)

    def cache_path(self, name: str) -> Path:
        return self.root / "cache" / name
