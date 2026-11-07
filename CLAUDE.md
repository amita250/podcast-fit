# podcast-fit: context for Claude

## Working with the owner
- Reply in Hebrew, addressing the owner in the feminine form. Code, comments,
  README and commit messages stay in English.
- The owner is a QA automation engineer: comfortable with Python, REST APIs,
  Postman and pytest. Explain the "why", skip the basics.
- She reviews every change. Prefer small, explained diffs over big rewrites,
  and add or update tests with every behavior change.
- Never open, print or edit `.env`. It holds real Spotify secrets.

## What this project is
Spotify can't filter podcasts by length. This tool fills one Spotify playlist
per "time slot" (e.g. a 20-30 min walk, a 40-50 min commute) with episodes
from the podcasts she follows. It runs weekly on GitHub Actions.

Sharing plan: public playlists for anyone, plus an open-source repo so
technical people can run their own copy. No public web app (see limits below).

## Architecture (each module does one thing)
- `models.py`: `Episode`, our own model. Only place that converts Spotify JSON
  (ms durations, partial release dates) into our types.
- `filters.py`: pure logic, which episodes fit a `FilterRules`. No network.
- `playlist_sync.py`: pure logic, diff between playlist and eligible list.
  Keeps still-eligible episodes, removes heard ones, fills free slots. Never
  touches non-episode items (songs) in the playlist.
- `spotify_client.py`: the ONLY module that knows Spotify URLs/JSON. Handles
  pagination, 429 Retry-After, 5xx retries, batching (100 URIs per write).
- `auth.py`: one-time login (Authorization Code, local server on
  127.0.0.1:8888) saves a refresh token to `.env`; later runs only refresh.
- `config.py`: secrets from env/.env, profiles from `config.yaml`.
- `main.py`: ties it together. `--dry-run` prints the plan without writing.

Keeping the data source behind `spotify_client.py` is deliberate: a future RSS /
Podcast Index source should return the same `Episode` objects.

## Decisions made (and why)
- Duration range is inclusive on both ends; compare in ms, convert input once.
- Half-heard episodes are judged by time remaining (`use_remaining_time`).
- `started_episodes: last` (default): episodes she started but didn't finish
  get a second chance only to fill leftover slots. Her usual reason for
  stopping is disliking the start, but sometimes it was just the wrong mood.
  Other modes: `first`, `exclude`.
- `max_per_show` stops one show from flooding a playlist.
- Run weekly (Saturday 18:00 UTC) plus a manual "Run workflow" button.
  `target_count` is sized for a week (12 commute, 8 walk).
- `config.yaml` and `.env` are git-ignored. In Actions, config comes from the
  repo variable `PODCAST_FIT_CONFIG`, secrets from repo secrets.

## Spotify API facts learned the hard way (2026)
- Development Mode: owner needs Premium; max 5 allow-listed users; extended
  quota is effectively out of reach for individuals.
- Batch endpoints (`GET /episodes`, `GET /shows`) were removed for dev-mode
  apps; fetch one by one. `/shows/{id}/episodes` still includes `duration_ms`.
- Playlist endpoints are `/playlists/{id}/items` (not `/tracks`); response
  field `track` was renamed `item`. Contents are only returned for playlists
  the user owns or collaborates on. DELETE body is `{"items": [{"uri": ...}]}`.
- `GET /search` max `limit` is 10.
- `show.publisher` and `available_markets` were removed from responses.
- `resume_point` only appears with a user token, never with client credentials.
- Refresh tokens expire 6 months after the original sign-in.
- Redirect URIs must match the dashboard exactly and be SAVED there;
  `localhost` is not accepted, use `127.0.0.1`.

## Status
- Done: Spotify app, Redirect URI, sign-in, two playlists, `config.yaml`.
  `auth.py` ConfigError handling and `started_episodes` applied (83 tests).
  First real run filled both playlists (2026-11-07).
- Next: push to GitHub (public), set Actions secrets and the
  `PODCAST_FIT_CONFIG` variable, then a manual "Run workflow" with dry_run.

## Ideas for later
Fill a slot with two shorter episodes; RSS source for a public tool; a small
web UI for discovery.

## Commands
```bash
pytest -q                                  # all tests, no network needed
python -m podcast_fit.auth                 # one-time sign-in
python -m podcast_fit.main --dry-run       # show the plan
python -m podcast_fit.main                 # update playlists
```
