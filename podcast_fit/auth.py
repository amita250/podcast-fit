"""Signing in to Spotify on your behalf.

Run once, locally:

    python -m podcast_fit.auth

A browser opens, you approve, and the script saves a refresh token to .env.
Every later run (including GitHub Actions) turns that refresh token into a
fresh one-hour access token without any browser.
"""

from __future__ import annotations

import base64
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import set_key

from .config import ConfigError, Secrets, load_secrets

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"

SCOPES = [
    "user-library-read",            # which podcasts you follow
    "user-read-playback-position",  # what you've already heard
    "playlist-read-private",        # read your playlists
    "playlist-modify-private",      # update private playlists
    "playlist-modify-public",       # update public playlists
]


class AuthError(RuntimeError):
    pass


def _basic_auth_header(client_id: str, client_secret: str) -> dict[str, str]:
    raw = f"{client_id}:{client_secret}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def _post_token(secrets_: Secrets, data: dict[str, str]) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data=data,
        headers=_basic_auth_header(secrets_.client_id, secrets_.client_secret),
        timeout=30,
    )
    if resp.status_code != 200:
        raise AuthError(f"Token request failed ({resp.status_code}): {resp.text}")
    return resp.json()


def refresh_access_token(secrets_: Secrets) -> tuple[str, str | None]:
    """Return (access_token, new_refresh_token_or_None).

    Spotify sometimes rotates the refresh token. If it does, the new one must be
    saved, or the next run will fail.
    """
    if not secrets_.refresh_token:
        raise AuthError(
            "No SPOTIFY_REFRESH_TOKEN found. Run `python -m podcast_fit.auth` first."
        )
    payload = _post_token(secrets_, {
        "grant_type": "refresh_token",
        "refresh_token": secrets_.refresh_token,
    })
    new_refresh = payload.get("refresh_token")
    if new_refresh == secrets_.refresh_token:
        new_refresh = None
    return payload["access_token"], new_refresh


# ------------------------------------------------------------ one-time login


class _CallbackHandler(BaseHTTPRequestHandler):
    result: dict[str, str] = {}

    def do_GET(self):  # noqa: N802 (name required by BaseHTTPRequestHandler)
        query = parse_qs(urlparse(self.path).query)
        _CallbackHandler.result = {k: v[0] for k, v in query.items()}
        ok = "code" in query
        self.send_response(200 if ok else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        message = "Signed in. You can close this tab." if ok else "Sign-in failed. Check the terminal."
        self.wfile.write(f"<h2 style='font-family:sans-serif'>{message}</h2>".encode())

    def log_message(self, *args):  # keep the terminal quiet
        pass


def login(env_path: Path = Path(".env")) -> str:
    secrets_ = load_secrets(env_path, require_refresh_token=False)
    redirect = urlparse(secrets_.redirect_uri)
    if redirect.hostname not in ("127.0.0.1", "localhost"):
        raise AuthError("SPOTIFY_REDIRECT_URI must point to 127.0.0.1 for local login")

    state = secrets.token_urlsafe(16)
    url = AUTHORIZE_URL + "?" + urlencode({
        "client_id": secrets_.client_id,
        "response_type": "code",
        "redirect_uri": secrets_.redirect_uri,
        "scope": " ".join(SCOPES),
        "state": state,
    })

    _CallbackHandler.result = {}
    server = HTTPServer((redirect.hostname, redirect.port or 80), _CallbackHandler)
    server.timeout = 1
    deadline = time.monotonic() + 300

    def wait_for_callback() -> None:
        # Keep serving until Spotify's redirect arrives; ignore stray requests
        # such as the browser asking for /favicon.ico.
        while time.monotonic() < deadline:
            server.handle_request()
            if "code" in _CallbackHandler.result or "error" in _CallbackHandler.result:
                return

    thread = threading.Thread(target=wait_for_callback, daemon=True)
    thread.start()

    print("Opening the browser to sign in to Spotify...")
    print(f"If it doesn't open, paste this URL into your browser:\n{url}\n")
    webbrowser.open(url)

    thread.join()
    server.server_close()
    result = _CallbackHandler.result

    if "error" in result:
        raise AuthError(f"Spotify returned an error: {result['error']}")
    if "code" not in result:
        raise AuthError("Timed out after 5 minutes without hearing back from Spotify.")
    if result.get("state") != state:
        raise AuthError("State mismatch. Possible tampering, try again.")

    payload = _post_token(secrets_, {
        "grant_type": "authorization_code",
        "code": result["code"],
        "redirect_uri": secrets_.redirect_uri,
    })
    refresh_token = payload["refresh_token"]

    set_key(str(env_path), "SPOTIFY_REFRESH_TOKEN", refresh_token)
    print(f"Saved SPOTIFY_REFRESH_TOKEN to {env_path}.")
    print("For GitHub Actions, copy it into the repo secret of the same name.")
    return refresh_token


if __name__ == "__main__":
    try:
        login()
    except (AuthError, ConfigError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
