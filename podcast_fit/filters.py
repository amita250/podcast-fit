
"""Which episodes fit a time slot.

Pure functions: no network, no tokens. Given a list of Episodes and a set of
rules, return the eligible ones in the order we'd like to hear them.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from .models import Episode, minutes_to_ms

STARTED_EPISODE_MODES = ("last", "first", "exclude")


@dataclass(frozen=True)
class FilterRules:
    min_minutes: float
    max_minutes: float
    # Judge a half-heard episode by the time left in it, not its full length.
    use_remaining_time: bool = True
    include_played: bool = False
    max_age_days: int | None = None
    languages: tuple[str, ...] | None = None
    # Stop one show from filling the whole playlist.
    max_per_show: int | None = None
    # Episodes you started but didn't finish:
    #   "last"    = second chance, only to fill leftover slots (usually you
    #               stopped because you disliked the start)
    #   "first"   = put them on top (finish what you began)
    #   "exclude" = never pick them
    started_episodes: str = "last"

    def __post_init__(self) -> None:
        if self.started_episodes not in STARTED_EPISODE_MODES:
            raise ValueError(
                f"started_episodes must be one of {', '.join(STARTED_EPISODE_MODES)}, "
                f"got {self.started_episodes!r}"
            )
        if self.min_minutes < 0 or self.max_minutes <= 0:
            raise ValueError("Minutes must be positive")
        if self.min_minutes > self.max_minutes:
            raise ValueError(
                f"min_minutes ({self.min_minutes}) is greater than "
                f"max_minutes ({self.max_minutes})"
            )

    @property
    def min_ms(self) -> int:
        return minutes_to_ms(self.min_minutes)

    @property
    def max_ms(self) -> int:
        return minutes_to_ms(self.max_minutes)


def listening_time_ms(episode: Episode, use_remaining_time: bool) -> int:
    return episode.remaining_ms if use_remaining_time else episode.duration_ms


def fits(episode: Episode, rules: FilterRules, today: date | None = None) -> bool:
    """Does this single episode match the rules? Range edges are inclusive."""
    if not episode.is_playable:
        return False
    if episode.fully_played and not rules.include_played:
        return False
    if episode.is_started and rules.started_episodes == "exclude":
        return False

    length = listening_time_ms(episode, rules.use_remaining_time)
    if not rules.min_ms <= length <= rules.max_ms:
        return False

    if rules.languages and episode.language not in rules.languages:
        return False

    if rules.max_age_days is not None:
        if episode.release_date is None:
            return False
        cutoff = (today or date.today()) - timedelta(days=rules.max_age_days)
        if episode.release_date < cutoff:
            return False

    return True


def select_episodes(
    episodes: Iterable[Episode],
    rules: FilterRules,
    today: date | None = None,
) -> list[Episode]:
    """Eligible episodes, best first.

    Order: newest releases first. By default (started_episodes="last"),
    episodes you started but didn't finish go after all untouched ones.
    Duplicates (same id) are dropped.
    """
    seen: set[str] = set()
    eligible: list[Episode] = []
    for ep in episodes:
        if ep.id in seen:
            continue
        seen.add(ep.id)
        if fits(ep, rules, today):
            eligible.append(ep)

    def started_rank(ep: Episode) -> int:
        if rules.started_episodes == "first":
            return 0 if ep.is_started else 1
        return 1 if ep.is_started else 0

    eligible.sort(key=lambda e: (
        started_rank(e),
        -(e.release_date.toordinal() if e.release_date else 0),
    ))

    if rules.max_per_show is None:
        return eligible

    per_show: dict[str | None, int] = {}
    limited: list[Episode] = []
    for ep in eligible:
        count = per_show.get(ep.show_id, 0)
        if count < rules.max_per_show:
            limited.append(ep)
            per_show[ep.show_id] = count + 1
    return limited
