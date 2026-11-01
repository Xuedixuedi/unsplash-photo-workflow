"""One JSON log file per command, plus a short human summary."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from upw.redact import redact, redact_obj


class RunLog:
    def __init__(self, state_dir: Path, command: str) -> None:
        self.state_dir = state_dir
        self.command = command
        self.run_id = uuid.uuid4().hex[:12]
        self.started = datetime.now(UTC)
        self.events: list[dict[str, Any]] = []
        self.failed: list[dict[str, str]] = []
        self.path = state_dir / "logs" / f"{self.run_id}.json"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "logs").mkdir(parents=True, exist_ok=True)

    def event(self, level: str, message: str, **fields: Any) -> None:
        record: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "run_id": self.run_id,
            "command": self.command,
            "level": level,
            "message": redact(message),
        }
        record.update(redact_obj(fields))
        self.events.append(record)
        print(json.dumps(record, ensure_ascii=False), file=sys.stderr)

    def fail(self, item_id: str, error: str) -> None:
        self.failed.append({"id": item_id, "error": redact(error)})
        self.event("error", error, item_id=item_id)

    def finish(self, summary: str) -> None:
        payload = {
            "run_id": self.run_id,
            "command": self.command,
            "started": self.started.isoformat(),
            "finished": datetime.now(UTC).isoformat(),
            "summary": redact(summary),
            "failed": self.failed,
            "events": self.events,
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(summary)
        if self.failed:
            print("Failed items:")
            for item in self.failed:
                print(f"- {item['id']}: {item['error']}")
