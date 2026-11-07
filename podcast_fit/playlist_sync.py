"""Work out what to add to and remove from a playlist.

We don't wipe and refill the playlist on every run. Episodes already in it stay
as long as they're still eligible, so the order you're listening in doesn't
jump around. Only the gaps get filled.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

EPISODE_URI_PREFIX = "spotify:episode:"


@dataclass(frozen=True)
class SyncPlan:
    keep: list[str] = field(default_factory=list)
    to_add: list[str] = field(default_factory=list)
    to_remove: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.to_add or self.to_remove)


def plan_sync(
    current_uris: Sequence[str],
    eligible_uris: Sequence[str],
    target_count: int,
) -> SyncPlan:
    """
    current_uris:  what's in the playlist now, in playlist order.
    eligible_uris: what may be in it, best first (output of select_episodes).
    target_count:  how many episodes the playlist should hold.

    Rules:
      * Only episodes are managed. Songs or anything else you added by hand
        are never touched.
      * An episode already in the playlist stays if it's still eligible.
      * Episodes that stopped being eligible (heard, too long now, etc.) go.
      * Free slots are filled from the top of the eligible list.
    """
    if target_count < 0:
        raise ValueError("target_count can't be negative")

    eligible_set = set(eligible_uris)

    current_episodes: list[str] = []
    for uri in current_uris:
        if uri.startswith(EPISODE_URI_PREFIX) and uri not in current_episodes:
            current_episodes.append(uri)

    keep = [u for u in current_episodes if u in eligible_set][:target_count]
    keep_set = set(keep)

    to_remove = [u for u in current_episodes if u not in keep_set]

    free_slots = target_count - len(keep)
    to_add = [u for u in eligible_uris if u not in keep_set][:free_slots]

    return SyncPlan(keep=keep, to_add=to_add, to_remove=to_remove)
