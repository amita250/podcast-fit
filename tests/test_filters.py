from datetime import date

import pytest

from podcast_fit.filters import FilterRules, fits, select_episodes

from .conftest import make_episode

WALK = FilterRules(min_minutes=20, max_minutes=30)
COMMUTE = FilterRules(min_minutes=40, max_minutes=50)
TODAY = date(2026, 11, 7)


class TestRules:
    def test_min_above_max_rejected(self):
        with pytest.raises(ValueError):
            FilterRules(min_minutes=50, max_minutes=40)

    def test_non_positive_max_rejected(self):
        with pytest.raises(ValueError):
            FilterRules(min_minutes=0, max_minutes=0)


class TestDurationRange:
    @pytest.mark.parametrize("minutes, expected", [
        (19.99, False),
        (20, True),       # lower edge is inclusive
        (24.41, True),    # the real "שיר אחד" episode
        (30, True),       # upper edge is inclusive
        (30.01, False),
        (45, False),
    ])
    def test_walk_range(self, minutes, expected):
        assert fits(make_episode(minutes=minutes), WALK) is expected

    def test_same_episode_different_profile(self):
        ep = make_episode(minutes=45)
        assert not fits(ep, WALK)
        assert fits(ep, COMMUTE)


class TestListeningState:
    def test_fully_played_excluded_by_default(self):
        assert not fits(make_episode(fully_played=True), WALK)

    def test_fully_played_allowed_when_asked(self):
        rules = FilterRules(20, 30, include_played=True, use_remaining_time=False)
        assert fits(make_episode(fully_played=True), rules)

    def test_long_episode_with_commute_left_in_it(self):
        # 90 min episode, stopped at 45 -> 45 min left -> fits the commute
        ep = make_episode(minutes=90, resume_minutes=45)
        assert fits(ep, COMMUTE)

    def test_remaining_time_can_be_turned_off(self):
        ep = make_episode(minutes=90, resume_minutes=45)
        rules = FilterRules(40, 50, use_remaining_time=False)
        assert not fits(ep, rules)

    def test_started_episode_with_too_little_left(self):
        ep = make_episode(minutes=25, resume_minutes=15)  # 10 min left
        assert not fits(ep, WALK)

    def test_unknown_played_state_counts_as_unplayed(self):
        assert fits(make_episode(fully_played=None), WALK)

    def test_unplayable_excluded(self):
        assert not fits(make_episode(is_playable=False), WALK)


class TestOptionalRules:
    def test_language(self):
        rules = FilterRules(20, 30, languages=("en",))
        assert not fits(make_episode(language="he"), rules)
        assert fits(make_episode(language="en"), rules)

    def test_max_age(self):
        rules = FilterRules(20, 30, max_age_days=30)
        assert fits(make_episode(released=date(2026, 10, 20)), rules, today=TODAY)
        assert not fits(make_episode(released=date(2026, 9, 1)), rules, today=TODAY)

    def test_max_age_with_unknown_date_excluded(self):
        rules = FilterRules(20, 30, max_age_days=30)
        assert not fits(make_episode(released=None), rules, today=TODAY)


class TestSelectEpisodes:
    def test_newest_first(self):
        old = make_episode("old", released=date(2026, 1, 1))
        new = make_episode("new", released=date(2026, 11, 1))
        result = select_episodes([old, new], WALK)
        assert [e.id for e in result] == ["new", "old"]

    def test_filters_out_non_matching(self):
        result = select_episodes(
            [make_episode("ok"), make_episode("long", minutes=60)], WALK
        )
        assert [e.id for e in result] == ["ok"]

    def test_duplicates_removed(self):
        ep = make_episode("same")
        assert len(select_episodes([ep, ep], WALK)) == 1

    def test_max_per_show(self):
        rules = FilterRules(20, 30, max_per_show=2)
        eps = [make_episode(f"a{i}", show_id="A", released=date(2026, 10, 10 + i))
               for i in range(5)]
        eps.append(make_episode("b1", show_id="B", released=date(2026, 1, 1)))
        result = select_episodes(eps, rules)
        assert [e.id for e in result] == ["a4", "a3", "b1"]

    def test_empty_input(self):
        assert select_episodes([], WALK) == []


class TestStartedEpisodes:
    old = make_episode("old", released=date(2026, 1, 1))
    new = make_episode("new", released=date(2026, 11, 1))
    # 25 min left; newest on purpose, so "last" must beat date order
    started = make_episode("started", minutes=40, resume_minutes=15,
                           released=date(2026, 11, 5))

    def ids(self, rules):
        return [e.id for e in select_episodes([self.old, self.new, self.started], rules)]

    def test_default_is_last(self):
        assert WALK.started_episodes == "last"
        assert self.ids(WALK) == ["new", "old", "started"]

    def test_first(self):
        rules = FilterRules(20, 30, started_episodes="first")
        assert self.ids(rules) == ["started", "new", "old"]

    def test_exclude(self):
        rules = FilterRules(20, 30, started_episodes="exclude")
        assert self.ids(rules) == ["new", "old"]

    def test_last_loses_slot_to_max_per_show(self):
        rules = FilterRules(20, 30, max_per_show=2)
        assert self.ids(rules) == ["new", "old"]

    def test_unknown_mode_rejected(self):
        with pytest.raises(ValueError, match="started_episodes"):
            FilterRules(20, 30, started_episodes="maybe")
