import pytest
import yaml

from podcast_fit.config import ConfigError, load_secrets, parse_config


def base_profile(**overrides) -> dict:
    profile = {
        "name": "Walk",
        "playlist_id": "pl1",
        "min_minutes": 20,
        "max_minutes": 30,
    }
    profile.update(overrides)
    return profile


def test_minimal_profile_gets_defaults():
    config = parse_config({"profiles": [base_profile()]})
    profile = config.profiles[0]
    assert profile.target_count == 10
    assert profile.shows == "followed"
    assert profile.rules.use_remaining_time is True
    assert config.market == "IL"


def test_started_episodes_default_and_parsed():
    default = parse_config({"profiles": [base_profile()]})
    assert default.profiles[0].rules.started_episodes == "last"
    explicit = parse_config({"profiles": [base_profile(started_episodes="exclude")]})
    assert explicit.profiles[0].rules.started_episodes == "exclude"


def test_explicit_show_list():
    config = parse_config({"profiles": [base_profile(shows=["a", "b"])]})
    assert config.profiles[0].shows == ("a", "b")


def test_example_config_is_valid():
    with open("config.example.yaml", encoding="utf-8") as fh:
        config = parse_config(yaml.safe_load(fh))
    assert len(config.profiles) >= 1


@pytest.mark.parametrize("bad, message", [
    ({}, "profiles"),
    ({"profiles": []}, "profiles"),
    ({"profiles": [base_profile(playlist_id="")]}, "playlist_id"),
    ({"profiles": [base_profile(min_minutes=40, max_minutes=30)]}, "greater"),
    ({"profiles": [base_profile(shows="everything")]}, "shows"),
    ({"profiles": [base_profile(shows=[])]}, "shows"),
    ({"profiles": [base_profile(target_count=0)]}, "target_count"),
    ({"profiles": [base_profile(), base_profile()]}, "unique"),
    ({"profiles": [base_profile(started_episodes="maybe")]}, "started_episodes"),
])
def test_invalid_configs(bad, message):
    with pytest.raises(ConfigError, match=message):
        parse_config(bad)


def test_missing_secrets_are_listed(monkeypatch):
    for name in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REFRESH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigError, match="SPOTIFY_CLIENT_ID.*SPOTIFY_REFRESH_TOKEN"):
        load_secrets(env_path=None)


def test_refresh_token_optional_for_login(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.delenv("SPOTIFY_REFRESH_TOKEN", raising=False)
    secrets_ = load_secrets(env_path=None, require_refresh_token=False)
    assert secrets_.refresh_token is None
