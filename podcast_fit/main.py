"""Entry point: update every playlist defined in config.yaml.

    python -m podcast_fit.main               # update playlists
    python -m podcast_fit.main --dry-run     # show what would change, touch nothing
    python -m podcast_fit.main --profile "Commute 40-50"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .auth import AuthError, refresh_access_token
from .config import AppConfig, ConfigError, Profile, load_config, load_secrets
from .filters import select_episodes
from .models import Episode, format_duration
from .playlist_sync import SyncPlan, plan_sync
from .spotify_client import SpotifyClient, SpotifyError


class EpisodeCache:
    """Several profiles often read the same shows; fetch each show only once."""

    def __init__(self, client: SpotifyClient, episodes_per_show: int):
        self._client = client
        self._per_show = episodes_per_show
        self._episodes: dict[str, list[Episode]] = {}
        self._followed: list[dict] | None = None

    def followed_shows(self) -> list[dict]:
        if self._followed is None:
            self._followed = self._client.get_followed_shows()
        return self._followed

    def shows_for(self, profile: Profile) -> list[dict]:
        if profile.shows == "followed":
            return self.followed_shows()
        return [self._client.get_show(show_id) for show_id in profile.shows]

    def episodes_of(self, show: dict) -> list[Episode]:
        if show["id"] not in self._episodes:
            self._episodes[show["id"]] = self._client.get_show_episodes(
                show["id"], show_name=show["name"], max_episodes=self._per_show
            )
        return self._episodes[show["id"]]


def build_plan(profile: Profile, cache: EpisodeCache,
               client: SpotifyClient) -> tuple[SyncPlan, dict[str, Episode]]:
    episodes: list[Episode] = []
    for show in cache.shows_for(profile):
        episodes.extend(cache.episodes_of(show))

    eligible = select_episodes(episodes, profile.rules)
    by_uri = {e.uri: e for e in episodes}

    current = client.get_playlist_uris(profile.playlist_id)
    plan = plan_sync(current, [e.uri for e in eligible], profile.target_count)
    return plan, by_uri


def describe(uri: str, by_uri: dict[str, Episode]) -> str:
    ep = by_uri.get(uri)
    if not ep:
        return uri
    length = ep.duration_label
    if ep.is_started:
        length += f", {format_duration(ep.remaining_ms)} left"
    return f"[{length}] {ep.show_name} - {ep.name}"


def run(config: AppConfig, client: SpotifyClient, dry_run: bool,
        only_profile: str | None = None) -> None:
    cache = EpisodeCache(client, config.episodes_per_show)
    profiles = [p for p in config.profiles if only_profile in (None, p.name)]
    if not profiles:
        raise ConfigError(f"No profile named '{only_profile}'")

    for profile in profiles:
        print(f"\n=== {profile.name} "
              f"({profile.rules.min_minutes:g}-{profile.rules.max_minutes:g} min) ===")
        plan, by_uri = build_plan(profile, cache, client)

        for uri in plan.to_remove:
            print(f"  - {describe(uri, by_uri)}")
        for uri in plan.to_add:
            print(f"  + {describe(uri, by_uri)}")
        total = len(plan.keep) + len(plan.to_add)
        print(f"  kept {len(plan.keep)}, adding {len(plan.to_add)}, "
              f"removing {len(plan.to_remove)} -> {total}/{profile.target_count}")
        if total < profile.target_count:
            print("  note: not enough matching episodes to reach the target")

        if dry_run or not plan.has_changes:
            continue
        if plan.to_remove:
            client.remove_from_playlist(profile.playlist_id, plan.to_remove)
        if plan.to_add:
            client.add_to_playlist(profile.playlist_id, plan.to_add)

    if dry_run:
        print("\nDry run: no playlist was changed.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill Spotify playlists with episodes that fit.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan without changing playlists")
    parser.add_argument("--profile", help="run only the profile with this name")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        secrets_ = load_secrets()
        access_token, rotated = refresh_access_token(secrets_)
        if rotated:
            print("WARNING: Spotify issued a new refresh token. "
                  "Update SPOTIFY_REFRESH_TOKEN in .env / GitHub secrets.")
        client = SpotifyClient(access_token, market=config.market)
        run(config, client, dry_run=args.dry_run, only_profile=args.profile)
    except (ConfigError, AuthError, SpotifyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
