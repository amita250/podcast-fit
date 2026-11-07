from datetime import date

import pytest

from podcast_fit.models import Episode, format_duration, minutes_to_ms, parse_release_date


class TestFromSpotify:
    def test_parses_real_episode(self, episode_json):
        ep = Episode.from_spotify(episode_json)
        assert ep.id == "19Ld3RMiadlr4RtTMe8D7E"
        assert ep.uri == "spotify:episode:19Ld3RMiadlr4RtTMe8D7E"
        assert ep.duration_ms == 1464816
        assert ep.duration_label == "24:25"
        assert ep.release_date == date(2022, 10, 24)
        assert ep.language == "he"
        assert ep.is_playable is True

    def test_takes_show_from_nested_object(self, episode_json):
        ep = Episode.from_spotify(episode_json, show_id="ignored", show_name="ignored")
        assert ep.show_id == "6VGc4JosqImDe1CQegoLEr"
        assert ep.show_name == "שיר אחד One Song"

    def test_uses_passed_show_when_missing(self, episode_json):
        # /shows/{id}/episodes returns simplified episodes without `show`
        del episode_json["show"]
        ep = Episode.from_spotify(episode_json, show_id="s1", show_name="My Show")
        assert (ep.show_id, ep.show_name) == ("s1", "My Show")

    def test_without_resume_point(self, episode_json):
        # An app token (client credentials) gets no resume_point at all
        ep = Episode.from_spotify(episode_json)
        assert ep.fully_played is None
        assert ep.resume_position_ms == 0
        assert ep.remaining_ms == ep.duration_ms
        assert not ep.is_started

    def test_partly_played(self, episode_json):
        episode_json["resume_point"] = {"fully_played": False, "resume_position_ms": 464816}
        ep = Episode.from_spotify(episode_json)
        assert ep.is_started
        assert ep.remaining_ms == 1_000_000

    def test_fully_played_has_nothing_left(self, episode_json):
        episode_json["resume_point"] = {"fully_played": True, "resume_position_ms": 0}
        ep = Episode.from_spotify(episode_json)
        assert ep.remaining_ms == 0
        assert not ep.is_started

    def test_resume_beyond_duration_does_not_go_negative(self, episode_json):
        episode_json["resume_point"] = {"fully_played": False, "resume_position_ms": 9_999_999}
        assert Episode.from_spotify(episode_json).remaining_ms == 0

    def test_missing_is_playable_means_playable(self, episode_json):
        del episode_json["is_playable"]
        assert Episode.from_spotify(episode_json).is_playable is True

    def test_unplayable(self, episode_json):
        episode_json["is_playable"] = False
        assert Episode.from_spotify(episode_json).is_playable is False


class TestHelpers:
    @pytest.mark.parametrize("ms, label", [
        (1464816, "24:25"),
        (1_800_000, "30:00"),
        (1_799_600, "30:00"),  # 29:59.6 rounds up for display only
        (59_400, "0:59"),
        (0, "0:00"),
    ])
    def test_format_duration(self, ms, label):
        assert format_duration(ms) == label

    def test_minutes_to_ms(self):
        assert minutes_to_ms(20) == 1_200_000
        assert minutes_to_ms(30) == 1_800_000

    @pytest.mark.parametrize("value, precision, expected", [
        ("2022-10-24", "day", date(2022, 10, 24)),
        ("2022-10", "month", date(2022, 10, 1)),
        ("2022", "year", date(2022, 1, 1)),
        ("2022", None, date(2022, 1, 1)),
        (None, "day", None),
        ("", "day", None),
        ("not-a-date", "day", None),
    ])
    def test_parse_release_date(self, value, precision, expected):
        assert parse_release_date(value, precision) == expected
