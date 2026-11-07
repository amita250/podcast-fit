# podcast-fit

Spotify won't let you filter podcasts by length. This fills your playlists with
episodes that fit a time slot: 20–30 minutes for a walk, 40–50 for a commute,
whatever your routine needs.

Once a week it:

1. reads the podcasts you follow (or a list you choose),
2. picks unplayed episodes that fit each slot, with half-heard ones judged by
   the time left in them,
3. tops up a playlist per slot, removing episodes you've finished.

Songs or anything else you add to those playlists by hand are left alone.

## Setup

You need Python 3.10+ and **Spotify Premium** (Spotify requires it for
developer apps).

### 1. Create a Spotify app

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) → **Create app**.
2. Redirect URI: `http://127.0.0.1:8888/callback` (Spotify doesn't accept `localhost`).
3. Tick **Web API**, save.
4. From **Settings**, copy the Client ID and Client Secret.

### 2. Install

```bash
git clone https://github.com/<you>/podcast-fit.git
cd podcast-fit
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then fill in client ID and secret
cp config.example.yaml config.yaml
```

### 3. Sign in once

```bash
python -m podcast_fit.auth
```

A browser opens. Approve, and your refresh token is saved to `.env`.

### 4. Create playlists and configure

Create an empty playlist in Spotify for each slot, copy its ID from the share
link (`open.spotify.com/playlist/<ID>`), and put it in `config.yaml`.

### 5. Run

```bash
python -m podcast_fit.main --dry-run   # see what would change
python -m podcast_fit.main             # do it
```

## Run it weekly on GitHub Actions

The workflow in `.github/workflows/update_playlists.yml` runs every Saturday
evening and can also be started by hand (**Actions → Update playlists → Run workflow**).

In your repo, under **Settings → Secrets and variables → Actions**:

| Type | Name | Value |
|---|---|---|
| Secret | `SPOTIFY_CLIENT_ID` | from the dashboard |
| Secret | `SPOTIFY_CLIENT_SECRET` | from the dashboard |
| Secret | `SPOTIFY_REFRESH_TOKEN` | from your `.env` after step 3 |
| Variable | `PODCAST_FIT_CONFIG` | the full contents of your `config.yaml` |

**Every six months** Spotify expires the refresh token. Run step 3 again and
update the secret.

## Limits worth knowing

- A Spotify app in Development Mode can be used by up to 5 people you add
  under **User Management** in the dashboard. To share more widely, share the
  repo (everyone runs their own app) or make your playlists public.
- Spotify sometimes rotates the refresh token. If a run prints a warning about
  it, update the secret.

## Project layout

```
podcast_fit/
  models.py          Episode: our own data model, independent of Spotify's JSON
  filters.py         which episodes fit a slot (pure logic, no network)
  playlist_sync.py   what to add/remove so the playlist matches (pure logic)
  spotify_client.py  every Spotify API call
  auth.py            one-time sign-in and token refresh
  config.py          loads config.yaml and secrets
  main.py            ties it together
tests/               pytest suite; fixtures/ holds a real API response
```

Run the tests with `pytest`.
