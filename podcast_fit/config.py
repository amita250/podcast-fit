"""Settings.

Two kinds, kept apart on purpose:
  * secrets (keys, tokens)    -> environment variables / .env, never in Git
  * preferences (profiles)    -> config.yaml, safe to share
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .filters import FilterRules

DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"


class ConfigError(ValueError):
    pass


# ------------------------------------------------------------------ secrets


@dataclass(frozen=True)
class Secrets:
    client_id: str
    client_secret: str
    refresh_token: str | None
    redirect_uri: str = DEFAULT_REDIRECT_URI


def load_secrets(env_path: Path | None = Path(".env"),
                 require_refresh_token: bool = True) -> Secrets:
    if env_path and env_path.exists():
        load_dotenv(env_path)

    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN", "").strip() or None

    missing = [name for name, value in [
        ("SPOTIFY_CLIENT_ID", client_id),
        ("SPOTIFY_CLIENT_SECRET", client_secret),
    ] if not value]
    if require_refresh_token and not refresh_token:
        missing.append("SPOTIFY_REFRESH_TOKEN")
    if missing:
        raise ConfigError(f"Missing environment variables: {', '.join(missing)}")

    return Secrets(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip(),
    )


# --------------------------------------------------------------- profiles


@dataclass(frozen=True)
class Profile:
    name: str
    playlist_id: str
    rules: FilterRules
    target_count: int = 10
    # "followed" = every podcast in your library, or an explicit list of show IDs
    shows: str | tuple[str, ...] = "followed"


@dataclass(frozen=True)
class AppConfig:
    profiles: list[Profile]
    market: str = "IL"
    episodes_per_show: int = 50  # how far back to look in each show
    extra: dict[str, Any] = field(default_factory=dict)


def _parse_profile(raw: dict[str, Any], index: int) -> Profile:
    where = f"profiles[{index}]"
    for key in ("name", "playlist_id", "min_minutes", "max_minutes"):
        if raw.get(key) in (None, ""):
            raise ConfigError(f"{where}: '{key}' is required")

    shows = raw.get("shows", "followed")
    if isinstance(shows, list):
        if not shows:
            raise ConfigError(f"{where}: 'shows' list is empty")
        shows = tuple(str(s).strip() for s in shows)
    elif shows != "followed":
        raise ConfigError(f"{where}: 'shows' must be 'followed' or a list of show IDs")

    languages = raw.get("languages")
    try:
        rules = FilterRules(
            min_minutes=float(raw["min_minutes"]),
            max_minutes=float(raw["max_minutes"]),
            use_remaining_time=bool(raw.get("use_remaining_time", True)),
            include_played=bool(raw.get("include_played", False)),
            max_age_days=raw.get("max_age_days"),
            languages=tuple(languages) if languages else None,
            max_per_show=raw.get("max_per_show"),
            started_episodes=str(raw.get("started_episodes", "last")),
        )
    except ValueError as exc:
        raise ConfigError(f"{where}: {exc}") from exc

    target = int(raw.get("target_count", 10))
    if target < 1:
        raise ConfigError(f"{where}: 'target_count' must be at least 1")

    return Profile(
        name=str(raw["name"]),
        playlist_id=str(raw["playlist_id"]).strip(),
        rules=rules,
        target_count=target,
        shows=shows,
    )


def parse_config(data: dict[str, Any]) -> AppConfig:
    if not isinstance(data, dict) or not data.get("profiles"):
        raise ConfigError("Config must contain a non-empty 'profiles' list")
    profiles = [_parse_profile(p, i) for i, p in enumerate(data["profiles"])]

    names = [p.name for p in profiles]
    if len(names) != len(set(names)):
        raise ConfigError("Profile names must be unique")

    return AppConfig(
        profiles=profiles,
        market=str(data.get("market", "IL")),
        episodes_per_show=int(data.get("episodes_per_show", 50)),
    )


def load_config(path: Path = Path("config.yaml")) -> AppConfig:
    if not path.exists():
        raise ConfigError(
            f"{path} not found. Copy config.example.yaml to config.yaml and edit it."
        )
    with path.open(encoding="utf-8") as fh:
        return parse_config(yaml.safe_load(fh))
