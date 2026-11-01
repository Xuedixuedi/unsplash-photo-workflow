"""Environment and project paths. Secrets stay in the process environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from upw.errors import UpwError


def _path_from_env(root: Path, env_name: str, default: str) -> Path:
    raw = os.environ.get(env_name, default)
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    return path


@dataclass
class Settings:
    root: Path
    state_dir: Path
    trips_dir: Path
    config_dir: Path
    originals_dir: Path
    phone_source: Path | None
    access_key: str
    secret_key: str
    user_token: str
    redirect_uri: str
    username: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    nominatim_user_agent: str
    api_base: str
    oauth_base: str
    nominatim_base: str
    no_ai: bool
    max_rate_sleep: float

    @classmethod
    def load(cls, root: Path | None = None) -> Settings:
        project = (root or Path.cwd()).resolve()
        load_dotenv(project / ".env")
        phone_raw = os.environ.get("UPW_PHONE_SOURCE", "").strip()
        phone = _path_from_env(project, "UPW_PHONE_SOURCE", phone_raw) if phone_raw else None
        no_ai = os.environ.get("UPW_NO_AI", "").strip().lower() in {"1", "true", "yes"}
        return cls(
            root=project,
            state_dir=_path_from_env(project, "UPW_STATE_DIR", "state"),
            trips_dir=_path_from_env(project, "UPW_TRIPS_DIR", "trips"),
            config_dir=_path_from_env(project, "UPW_CONFIG_DIR", "config"),
            originals_dir=_path_from_env(project, "UPW_ORIGINALS_DIR", "originals"),
            phone_source=phone,
            access_key=os.environ.get("UNSPLASH_ACCESS_KEY", "").strip(),
            secret_key=os.environ.get("UNSPLASH_SECRET_KEY", "").strip(),
            user_token=os.environ.get("UNSPLASH_USER_TOKEN", "").strip(),
            redirect_uri=os.environ.get("UNSPLASH_REDIRECT_URI", "http://127.0.0.1:8787/callback").strip(),
            username=os.environ.get("UNSPLASH_USERNAME", "").strip(),
            llm_api_key=os.environ.get("LLM_API_KEY", "").strip(),
            llm_base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/"),
            llm_model=os.environ.get("LLM_MODEL", "gpt-4o-mini").strip(),
            nominatim_user_agent=os.environ.get(
                "NOMINATIM_USER_AGENT",
                "unsplash-photo-workflow/0.1 (https://github.com/Xuedixuedi/unsplash-photo-workflow)",
            ).strip(),
            api_base=os.environ.get("UPW_API_BASE", "https://api.unsplash.com").strip().rstrip("/"),
            oauth_base=os.environ.get("UPW_OAUTH_BASE", "https://unsplash.com").strip().rstrip("/"),
            nominatim_base=os.environ.get("UPW_NOMINATIM_BASE", "https://nominatim.openstreetmap.org").strip().rstrip("/"),
            no_ai=no_ai,
            max_rate_sleep=float(os.environ.get("UPW_MAX_RATE_SLEEP", "90")),
        )

    def require_token(self) -> None:
        if not self.user_token:
            raise UpwError("UNSPLASH_USER_TOKEN is missing. Run `upw auth` or add the token to .env.")

    def require_app_keys(self) -> None:
        missing = [
            name
            for name, value in (
                ("UNSPLASH_ACCESS_KEY", self.access_key),
                ("UNSPLASH_SECRET_KEY", self.secret_key),
            )
            if not value
        ]
        if missing:
            raise UpwError("Missing " + ", ".join(missing) + ". Copy .env.example to .env.")


def upsert_env(path: Path, updates: dict[str, str]) -> None:
    """Replace or append keys in a dotenv file without printing the values."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    written: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            written.append(line)
            continue
        key = line.split("=", 1)[0]
        if key in updates:
            written.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            written.append(line)
    for key, value in updates.items():
        if key not in seen:
            written.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(written) + "\n", encoding="utf-8")
