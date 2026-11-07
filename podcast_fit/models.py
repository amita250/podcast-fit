"""Our own data model for an episode.

Only spotify_client.py knows what Spotify's JSON looks like. Everything else in
the project works with `Episode`, so a future data source (e.g. RSS) only has to
produce the same objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

MS_PER_MINUTE = 60 * 1000


def minutes_to_ms(minutes: float) -> int:
    return int(minutes * MS_PER_MINUTE)


def format_duration(ms: int) -> str:
    """1464816 -> '24:25'. Rounds to the nearest second."""
    total_sec = round(ms / 1000)
    return f"{total_sec // 60}:{total_sec % 60:02d}"


def parse_release_date(value: str | None, precision: str | None) -> date | None:
    """Spotify may send '2022-10-24', '2022-10' or '2022' depending on precision.

    Partial dates are pinned to the first day of the period.
    """
    if not value:
        return None
    try:
        if precision == "year" or len(value) == 4:
            return date(int(value), 1, 1)
        if precision == "month" or len(value) == 7:
            year, month = value.split("-")
            return date(int(year), int(month), 1)
        return date.fromisoformat(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class Episode:
    id: str
    uri: str
    name: str
    show_id: str | None
    show_name: str | None
    duration_ms: int
    release_date: date | None
    language: str | None
    is_playable: bool
    fully_played: bool | None  # None = unknown (no user token, or field missing)
    resume_position_ms: int

    @property
    def is_started(self) -> bool:
        return self.resume_position_ms > 0 and not self.fully_played

    @property
    def remaining_ms(self) -> int:
        """Time left to listen. Equals duration for episodes not yet started."""
        if self.fully_played:
            return 0
        return max(self.duration_ms - self.resume_position_ms, 0)

    @property
    def duration_label(self) -> str:
        return format_duration(self.duration_ms)

    @classmethod
    def from_spotify(
        cls,
        data: dict[str, Any],
        show_id: str | None = None,
        show_name: str | None = None,
    ) -> Episode:
        """Build an Episode from a Spotify episode object (full or simplified).

        The simplified episodes returned by /shows/{id}/episodes don't include
        the parent show, so the caller can pass it in.
        """
        show = data.get("show") or {}
        resume = data.get("resume_point") or {}
        return cls(
            id=data["id"],
            uri=data["uri"],
            name=data.get("name", ""),
            show_id=show.get("id") or show_id,
            show_name=show.get("name") or show_name,
            duration_ms=int(data.get("duration_ms") or 0),
            release_date=parse_release_date(
                data.get("release_date"), data.get("release_date_precision")
            ),
            language=data.get("language"),
            # Missing means Spotify didn't restrict it, so treat as playable.
            is_playable=data.get("is_playable", True) is not False,
            fully_played=resume.get("fully_played"),
            resume_position_ms=int(resume.get("resume_position_ms") or 0),
        )
