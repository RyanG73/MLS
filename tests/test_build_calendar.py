from datetime import date

import scripts.build_calendar as calendar


class _FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 7, 25)


def test_calendar_keeps_today_selectable_and_sorts_matches(monkeypatch):
    monkeypatch.setattr(calendar, "date", _FixedDate)
    files = [
        (
            "test-league",
            {
                "league": {"name": "Test League"},
                "games": [
                    {
                        "date": "2026-07-25",
                        "home": "Later",
                        "away": "Away",
                        "ko": "2026-07-25T18:00Z",
                    },
                    {
                        "date": "2026-07-25",
                        "home": "Earlier",
                        "away": "Away",
                        "ko": "2026-07-25T12:00Z",
                    },
                ],
            },
        )
    ]

    payload = calendar.build_calendar(files)

    assert payload["today"] == "2026-07-25"
    assert payload["today"] in payload["dates"]
    assert len(payload["dates"]) == calendar.DAYS_BACK + calendar.DAYS_FWD + 1
    assert [row["home"] for row in payload["days"]["2026-07-25"]] == [
        "Earlier",
        "Later",
    ]


def test_calendar_includes_quiet_days(monkeypatch):
    monkeypatch.setattr(calendar, "date", _FixedDate)

    payload = calendar.build_calendar([])

    assert payload["days"] == {}
    assert payload["dates"][calendar.DAYS_BACK] == "2026-07-25"
