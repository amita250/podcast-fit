"""Client tests against a fake HTTP session: no network, no real Spotify."""

import pytest

from podcast_fit.spotify_client import SpotifyClient, SpotifyError


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.content = b"x" if body is not None else b""
        self.text = str(body)

    def json(self):
        return self._body


class FakeSession:
    """Returns queued responses in order and records every call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def make_client(responses):
    session = FakeSession(responses)
    sleeps = []
    client = SpotifyClient("token", market="IL", session=session, sleep=sleeps.append)
    return client, session, sleeps


def episode_item(n, minutes=25):
    return {"id": f"e{n}", "uri": f"spotify:episode:e{n}", "name": f"E{n}",
            "duration_ms": minutes * 60_000, "release_date": "2026-11-01",
            "release_date_precision": "day"}


def test_sends_bearer_token():
    client, session, _ = make_client([])
    assert session.headers["Authorization"] == "Bearer token"


def test_follows_next_links_and_skips_nulls():
    page1 = {"items": [episode_item(1), None], "next": "https://api.spotify.com/v1/next-page"}
    page2 = {"items": [episode_item(2)], "next": None}
    client, session, _ = make_client([FakeResponse(body=page1), FakeResponse(body=page2)])

    episodes = client.get_show_episodes("show1", show_name="My Show")

    assert [e.id for e in episodes] == ["e1", "e2"]
    assert episodes[0].show_name == "My Show"
    assert session.calls[0][2]["params"]["market"] == "IL"
    assert session.calls[1][1] == "https://api.spotify.com/v1/next-page"


def test_max_episodes_stops_early():
    page = {"items": [episode_item(i) for i in range(5)],
            "next": "https://api.spotify.com/v1/more"}
    client, session, _ = make_client([FakeResponse(body=page)])
    assert len(client.get_show_episodes("s", max_episodes=3)) == 3
    assert len(session.calls) == 1


def test_retries_after_rate_limit():
    ok = FakeResponse(body={"items": [], "next": None})
    client, session, sleeps = make_client([
        FakeResponse(429, body={}, headers={"Retry-After": "2"}),
        ok,
    ])
    client.get_followed_shows()
    assert len(session.calls) == 2
    assert sleeps == [3]


def test_error_raises_with_spotify_message():
    client, _, _ = make_client([
        FakeResponse(403, body={"error": {"status": 403, "message": "Forbidden"}}),
    ])
    with pytest.raises(SpotifyError, match="403.*Forbidden"):
        client.get_followed_shows()


def test_playlist_reads_both_item_and_track_fields():
    body = {"items": [
        {"item": {"uri": "spotify:episode:a"}},
        {"track": {"uri": "spotify:track:b"}},
        {"item": None},
    ], "next": None}
    client, _, _ = make_client([FakeResponse(body=body)])
    assert client.get_playlist_uris("pl") == ["spotify:episode:a", "spotify:track:b"]


def test_add_is_batched_by_100():
    uris = [f"spotify:episode:{i}" for i in range(150)]
    client, session, _ = make_client([FakeResponse(body={}), FakeResponse(body={})])
    client.add_to_playlist("pl", uris)
    sizes = [len(call[2]["json"]["uris"]) for call in session.calls]
    assert sizes == [100, 50]


def test_remove_uses_items_body():
    client, session, _ = make_client([FakeResponse(body={})])
    client.remove_from_playlist("pl", ["spotify:episode:a"])
    method, url, kwargs = session.calls[0]
    assert method == "DELETE"
    assert url.endswith("/playlists/pl/items")
    assert kwargs["json"] == {"items": [{"uri": "spotify:episode:a"}]}
