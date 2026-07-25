from pathlib import Path

from scripts.build_dashboard_data import mls_local_date


def test_mls_local_date_uses_home_venue_timezone():
    assert mls_local_date("2026-07-17T00:30Z", "CHI") == "2026-07-16"
    assert mls_local_date("2026-07-17T02:30Z", "SEA") == "2026-07-16"
    assert mls_local_date("2026-07-16T23:30Z", "MTL") == "2026-07-16"


def test_mls_local_date_falls_back_when_unknown():
    assert mls_local_date("2026-07-17T00:30Z", "???", "2026-07-17") == "2026-07-17"
    assert mls_local_date(None, "CHI", "2026-07-17") == "2026-07-17"


def test_mls_builds_refresh_the_feature_frame_before_dashboard_data():
    root = Path(__file__).resolve().parent.parent
    daily = (root / ".github/workflows/refresh-daily.yml").read_text()
    local = (root / "scripts/build_all.sh").read_text()
    refresh = "scripts/eval_baseline.py"
    dashboard = "scripts/build_dashboard_data.py"
    for build in (daily, local):
        assert refresh in build
        assert "--dump-frame data/parity_frame.parquet" in build
        assert build.index(refresh) < build.index(dashboard)
