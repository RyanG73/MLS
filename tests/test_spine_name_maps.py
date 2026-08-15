"""The fixture-diff name-map derivation that unblocks getting off ESPN.

`config/api_football_team_names.json` covered three leagues because MLS's map
was worked out by hand. Seventy-five more cannot be done that way, and the
failure mode is silent: an unmapped club is discarded downstream as "not in
this league" and the payload still looks healthy, short a team nobody counted.

The rule under test is that a pair is proven by FIXTURES, never by name
similarity — fuzzy matching once proposed `Bristol City → Stoke City`, which
would have attributed one club's results to another and looked plausible.
"""
from __future__ import annotations

import datetime as dt

from scripts.generate_spine_name_maps import (
    MIN_CORROBORATING_FIXTURES, audit, derive_pairs, overrides_only, token_match,
)

D = dt.date(2026, 3, 1)


def fx(day, home, away, hg, ag):
    return {"date": D + dt.timedelta(days=day), "home": home, "away": away,
            "hg": hg, "ag": ag}


def _round_robin(names, scores):
    """Enough fixtures per club to clear the corroboration floor."""
    rows, day = [], 0
    for hg, ag in scores:
        for i in range(len(names)):
            rows.append(fx(day, names[i], names[(i + 1) % len(names)], hg, ag))
            day += 1
    return rows


OURS_NAMES = ["Arsenal", "Liverpool", "Brentford", "Ipswich Town"]
SCORES = [(2, 1), (0, 3), (1, 1), (4, 0)]


def test_a_pair_is_proven_by_shared_fixtures_not_by_spelling():
    ours = _round_robin(OURS_NAMES, SCORES)
    theirs = _round_robin(
        ["Arsenal FC", "Liverpool FC", "Brentford FC", "Ipswich"], SCORES)

    pairs, problems, _ = derive_pairs(ours, theirs)
    assert problems == []
    assert pairs["Ipswich"] == "Ipswich Town"
    assert pairs["Arsenal FC"] == "Arsenal"


def test_a_late_kickoff_a_day_out_still_matches():
    """A 23:30 UTC fixture lands on the next calendar day. Measured on MLS: the
    19th of 19 matched a day later at the same 2-1, a timezone not a defect."""
    ours = _round_robin(OURS_NAMES, SCORES)
    theirs = [dict(row, date=row["date"] + dt.timedelta(days=1))
              for row in _round_robin(
                  ["Arsenal FC", "Liverpool FC", "Brentford FC", "Ipswich"], SCORES)]

    pairs, problems, _ = derive_pairs(ours, theirs)
    assert problems == []
    assert pairs["Ipswich"] == "Ipswich Town"


def test_two_days_out_is_a_different_matchday_and_does_not_match():
    ours = _round_robin(OURS_NAMES, SCORES)
    theirs = [dict(row, date=row["date"] + dt.timedelta(days=2))
              for row in _round_robin(
                  ["Arsenal FC", "Liverpool FC", "Brentford FC", "Ipswich"], SCORES)]

    pairs, _, _ = derive_pairs(ours, theirs)
    assert pairs == {}, "widening the window is how two matchdays start matching"


def test_the_opponent_is_what_identifies_a_fixture():
    """Scoreline and date alone are far too weak, and this is why.

    Both of our day-0 fixtures finished 1-0, so on scoreline and date the spine
    row could be either. Its OPPONENT settles it: `Bristol` played Arsenal, and
    only one of ours did. This is the constraint that makes the derivation safe
    rather than a coin flip — remove it and the pairing becomes arbitrary.
    """
    ours = [fx(0, "Bristol City", "Arsenal", 1, 0),
            fx(0, "Stoke City", "Liverpool", 1, 0),
            fx(1, "Bristol City", "Liverpool", 2, 2),
            fx(1, "Stoke City", "Arsenal", 2, 2),
            fx(2, "Bristol City", "Brentford", 0, 1),
            fx(2, "Stoke City", "Brentford", 0, 1)]
    theirs = [fx(0, "Bristol", "Arsenal", 1, 0),
              fx(1, "Bristol", "Liverpool", 2, 2),
              fx(2, "Bristol", "Brentford", 0, 1)]

    pairs, problems, unplaced = derive_pairs(ours, theirs)
    assert pairs["Bristol"] == "Bristol City", problems
    assert "Stoke City" not in pairs.values()


def test_two_clubs_with_indistinguishable_fixtures_are_refused_not_guessed():
    """The rule the Bristol City → Stoke City near-miss bought.

    Here nothing separates the two: same dates, same scorelines, and opponents
    that are themselves unresolved, so no constraint can break the tie. Picking
    one would attribute a club's whole season to another and look entirely
    plausible in the payload. Refusing is the correct answer.
    """
    ours = [fx(0, "Bristol City", "Rovers A", 1, 0),
            fx(0, "Stoke City", "Rovers B", 1, 0),
            fx(1, "Bristol City", "Rovers B", 2, 2),
            fx(1, "Stoke City", "Rovers A", 2, 2),
            fx(2, "Bristol City", "Rovers C", 0, 1),
            fx(2, "Stoke City", "Rovers D", 0, 1)]
    theirs = [fx(0, "Bristol", "Rovers X", 1, 0),
              fx(1, "Bristol", "Rovers Y", 2, 2),
              fx(2, "Bristol", "Rovers Z", 0, 1)]

    pairs, problems, unplaced = derive_pairs(ours, theirs)
    assert "Bristol" not in pairs, "nothing here separates Bristol City from Stoke City"
    assert "Bristol" in unplaced, "an unplaced spine club must be visible, not silent"


def test_one_shared_scoreline_is_a_coincidence_not_evidence():
    ours = [fx(0, "Arsenal", "Liverpool", 2, 1)]
    theirs = [fx(0, "Arsenal FC", "Liverpool FC", 2, 1)]

    pairs, problems, unplaced = derive_pairs(ours, theirs)
    assert pairs == {}
    assert any("corroborating" in p for p in problems)
    assert MIN_CORROBORATING_FIXTURES > 1


def test_two_spine_clubs_cannot_claim_the_same_club():
    ours = _round_robin(OURS_NAMES, SCORES)
    theirs = _round_robin(["Arsenal FC", "Liverpool FC", "Brentford FC", "Ipswich"],
                          SCORES)
    theirs += _round_robin(["Arsenal SC", "Liverpool FC", "Brentford FC", "Ipswich"],
                           SCORES)

    pairs, problems, unplaced = derive_pairs(ours, theirs)
    assert "Arsenal FC" not in pairs and "Arsenal SC" not in pairs
    assert any("claimed by" in p for p in problems)


def test_only_genuine_mismatches_become_overrides():
    """A pair production's token matcher already resolves needs no entry —
    writing it down would be noise that later reads as a rule."""
    assert token_match("Arsenal FC", "Arsenal")
    assert not token_match("Los Angeles Galaxy", "LA Galaxy")

    overrides = overrides_only({
        "Arsenal FC": "Arsenal",              # suffix only — already handled
        "Los Angeles Galaxy": "LA Galaxy",    # the real MLS override
    })
    assert overrides == {"Los Angeles Galaxy": "LA Galaxy"}


def test_a_league_is_held_when_one_club_is_unresolved():
    """29 of 30 is 96.7%, clears any percentage floor, and silently drops every
    fixture of the club it missed. The only honest floor is all of them."""
    ours = _round_robin(OURS_NAMES, SCORES)
    theirs = _round_robin(["Arsenal FC", "Liverpool FC", "Brentford FC", "Ipswich"],
                          SCORES)
    clubs = set(OURS_NAMES) | {"Leicester City"}      # in our table, absent upstream

    report = audit("epl", ours, theirs, clubs)
    assert report["ok"] is False
    assert report["missing"] == ["Leicester City"]


def test_a_fully_resolved_league_passes():
    ours = _round_robin(OURS_NAMES, SCORES)
    theirs = _round_robin(["Arsenal FC", "Liverpool FC", "Brentford FC", "Ipswich"],
                          SCORES)

    report = audit("epl", ours, theirs, set(OURS_NAMES))
    assert report["ok"] is True
    assert report["resolved"] == len(OURS_NAMES)
    assert report["overrides"] == {"Ipswich": "Ipswich Town"}


def test_an_empty_spine_answer_holds_the_league_rather_than_wiping_its_map():
    """A dark upstream must not be mistaken for "this league has no clubs"."""
    report = audit("epl", _round_robin(OURS_NAMES, SCORES), [], set(OURS_NAMES))
    assert report["ok"] is False
    assert sorted(report["missing"]) == sorted(OURS_NAMES)
