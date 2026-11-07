import json
from datetime import date
from pathlib import Path

import pytest

from podcast_fit.models import Episode

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def episode_json() -> dict:
    """The real response from GET /episodes/19Ld3RMiadlr4RtTMe8D7E."""
    return json.loads((FIXTURES / "episode_sample.json").read_text(encoding="utf-8"))


def make_episode(
    id: str = "ep1",
    minutes: float = 25,
    show_id: str = "show1",
    released: date | None = date(2026, 11, 1),
    language: str = "he",
    is_playable: bool = True,
    fully_played: bool | None = False,
    resume_minutes: float = 0,
) -> Episode:
    """Build an Episode quickly for tests, in minutes instead of milliseconds."""
    return Episode(
        id=id,
        uri=f"spotify:episode:{id}",
        name=f"Episode {id}",
        show_id=show_id,
        show_name=f"Show {show_id}",
        duration_ms=int(minutes * 60_000),
        release_date=released,
        language=language,
        is_playable=is_playable,
        fully_played=fully_played,
        resume_position_ms=int(resume_minutes * 60_000),
    )
