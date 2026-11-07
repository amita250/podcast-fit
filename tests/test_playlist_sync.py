import pytest

from podcast_fit.playlist_sync import plan_sync


def ep(n) -> str:
    return f"spotify:episode:{n}"


SONG = "spotify:track:abc"


def test_empty_playlist_gets_filled_from_the_top():
    plan = plan_sync([], [ep(1), ep(2), ep(3)], target_count=2)
    assert plan.to_add == [ep(1), ep(2)]
    assert plan.to_remove == []


def test_still_eligible_episodes_are_kept():
    plan = plan_sync([ep(2)], [ep(1), ep(2), ep(3)], target_count=2)
    assert plan.keep == [ep(2)]
    assert plan.to_add == [ep(1)]
    assert plan.to_remove == []


def test_heard_episode_is_replaced():
    # ep(1) was heard this week, so it's no longer eligible
    plan = plan_sync([ep(1), ep(2)], [ep(2), ep(3)], target_count=2)
    assert plan.to_remove == [ep(1)]
    assert plan.keep == [ep(2)]
    assert plan.to_add == [ep(3)]


def test_nothing_to_do():
    plan = plan_sync([ep(1), ep(2)], [ep(1), ep(2)], target_count=2)
    assert not plan.has_changes


def test_songs_are_never_touched():
    plan = plan_sync([SONG, ep(1)], [ep(2)], target_count=1)
    assert SONG not in plan.to_remove
    assert plan.to_remove == [ep(1)]


def test_target_lowered_trims_playlist():
    plan = plan_sync([ep(1), ep(2), ep(3)], [ep(1), ep(2), ep(3)], target_count=2)
    assert plan.keep == [ep(1), ep(2)]
    assert plan.to_remove == [ep(3)]
    assert plan.to_add == []


def test_not_enough_eligible_episodes():
    plan = plan_sync([], [ep(1)], target_count=10)
    assert plan.to_add == [ep(1)]


def test_duplicate_in_playlist_is_not_added_again():
    plan = plan_sync([ep(1), ep(1)], [ep(1), ep(2)], target_count=2)
    assert plan.keep == [ep(1)]
    assert plan.to_add == [ep(2)]


def test_negative_target_rejected():
    with pytest.raises(ValueError):
        plan_sync([], [], target_count=-1)
