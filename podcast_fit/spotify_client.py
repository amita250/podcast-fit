"""Every call to the Spotify Web API lives here.

This is the only module that knows Spotify's URLs and JSON shapes. It hands
the rest of the project `Episode` objects and plain URI lists.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import requests

from .models import Episode

API_BASE = "https://api.spotify.com/v1"
PAGE_SIZE = 50          # max page size for library/show/playlist listings
WRITE_BATCH_SIZE = 100  # max URIs per add/remove call
MAX_RETRIES = 3


class SpotifyError(RuntimeError):
    def __init__(self, status: int, message: str, url: str):
        super().__init__(f"Spotify API {status} on {url}: {message}")
        self.status = status
        self.url = url


class SpotifyClient:
    def __init__(
        self,
        access_token: str,
        market: str = "IL",
        session: requests.Session | None = None,
        sleep=time.sleep,
    ):
        self.market = market
        self._session = session or requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {access_token}"})
        self._sleep = sleep  # injectable so tests don't really wait

    # ------------------------------------------------------------------ HTTP

    def _request(self, method: str, path_or_url: str, **kwargs: Any) -> dict[str, Any]:
        url = path_or_url if path_or_url.startswith("http") else f"{API_BASE}{path_or_url}"
        for attempt in range(MAX_RETRIES + 1):
            resp = self._session.request(method, url, timeout=30, **kwargs)

            if resp.status_code == 429 and attempt < MAX_RETRIES:
                # Rate limited: Spotify says how long to wait.
                wait = int(resp.headers.get("Retry-After", "1"))
                self._sleep(wait + 1)
                continue
            if resp.status_code >= 500 and attempt < MAX_RETRIES:
                self._sleep(2 ** attempt)
                continue

            if resp.status_code >= 400:
                try:
                    message = resp.json().get("error", {}).get("message", resp.text)
                except ValueError:
                    message = resp.text
                raise SpotifyError(resp.status_code, message, url)

            if not resp.content:
                return {}
            return resp.json()

        raise SpotifyError(resp.status_code, "gave up after retries", url)  # pragma: no cover

    def _paginate(self, path: str, params: dict[str, Any] | None = None,
                  max_items: int | None = None) -> Iterator[dict[str, Any]]:
        """Follow `next` links until done (or until max_items were yielded)."""
        params = {"limit": PAGE_SIZE, **(params or {})}
        url: str | None = path
        yielded = 0
        while url:
            page = self._request("GET", url, params=params)
            params = None  # `next` already carries the query string
            for item in page.get("items", []):
                if item is None:  # Spotify occasionally returns null entries
                    continue
                yield item
                yielded += 1
                if max_items is not None and yielded >= max_items:
                    return
            url = page.get("next")

    # --------------------------------------------------------------- reading

    def get_followed_shows(self) -> list[dict[str, Any]]:
        """Podcasts saved in your library: [{'id':..., 'name':...}, ...]"""
        return [
            {"id": entry["show"]["id"], "name": entry["show"]["name"]}
            for entry in self._paginate("/me/shows")
            if entry.get("show")
        ]

    def get_show(self, show_id: str) -> dict[str, Any]:
        data = self._request("GET", f"/shows/{show_id}", params={"market": self.market})
        return {"id": data["id"], "name": data["name"]}

    def get_show_episodes(self, show_id: str, show_name: str | None = None,
                          max_episodes: int = 50) -> list[Episode]:
        """Most recent episodes of a show (Spotify returns newest first)."""
        items = self._paginate(
            f"/shows/{show_id}/episodes",
            params={"market": self.market},
            max_items=max_episodes,
        )
        return [Episode.from_spotify(i, show_id=show_id, show_name=show_name) for i in items]

    def get_playlist_uris(self, playlist_id: str) -> list[str]:
        """URIs currently in a playlist, in order. Works only for your own playlists."""
        uris = []
        for entry in self._paginate(f"/playlists/{playlist_id}/items"):
            # The field was renamed from 'track' to 'item' in 2026; accept both.
            obj = entry.get("item") or entry.get("track")
            if obj and obj.get("uri"):
                uris.append(obj["uri"])
        return uris

    # --------------------------------------------------------------- writing

    def add_to_playlist(self, playlist_id: str, uris: list[str]) -> None:
        for i in range(0, len(uris), WRITE_BATCH_SIZE):
            self._request("POST", f"/playlists/{playlist_id}/items",
                          json={"uris": uris[i:i + WRITE_BATCH_SIZE]})

    def remove_from_playlist(self, playlist_id: str, uris: list[str]) -> None:
        for i in range(0, len(uris), WRITE_BATCH_SIZE):
            batch = uris[i:i + WRITE_BATCH_SIZE]
            self._request("DELETE", f"/playlists/{playlist_id}/items",
                          json={"items": [{"uri": u} for u in batch]})
