from scripts.build_dashboard_data import mls_local_date


def test_mls_local_date_uses_home_venue_timezone():
    assert mls_local_date("2026-07-17T00:30Z", "CHI") == "2026-07-16"
    assert mls_local_date("2026-07-17T02:30Z", "SEA") == "2026-07-16"
    assert mls_local_date("2026-07-16T23:30Z", "MTL") == "2026-07-16"


def test_mls_local_date_falls_back_when_unknown():
    assert mls_local_date("2026-07-17T00:30Z", "???", "2026-07-17") == "2026-07-17"
    assert mls_local_date(None, "CHI", "2026-07-17") == "2026-07-17"
