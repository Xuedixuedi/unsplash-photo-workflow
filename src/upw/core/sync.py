"""Fetch the owner's photos and compare them with local processed ids."""

from __future__ import annotations

from dataclasses import dataclass

from upw.adapters.unsplash import UnsplashClient
from upw.errors import UpwError
from upw.models import Photo
from upw.state.store import StateStore


@dataclass
class SyncResult:
    username: str
    photos: list[Photo]
    new_ids: list[str]


def sync_account(client: UnsplashClient, store: StateStore, username: str) -> SyncResult:
    resolved = username
    if not resolved:
        profile = client.me()
        resolved = str(profile.get("username") or "")
    if not resolved:
        raise UpwError("Could not resolve the Unsplash username. Set UNSPLASH_USERNAME.")
    photos = client.list_user_photos(resolved)
    store.save_photos(photos)
    store.save_username(resolved)
    processed = store.processed_ids()
    new_ids = [photo.id for photo in photos if photo.id not in processed]
    return SyncResult(username=resolved, photos=photos, new_ids=new_ids)
