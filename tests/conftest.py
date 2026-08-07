collect_ignore_glob = []

import pytest


@pytest.fixture(autouse=True, scope="session")
def _no_espn_backoff_in_tests():
    """Turn off the ESPN throttle and retry ladder for the whole test session.

    A handful of tests (test_interconf_calibrate, test_league_bridge) reach
    site.api.espn.com for real. Against a rate-limited host every one of those
    requests pays the full backoff ladder, which took this suite from 75s to
    9m41s — `test_collector_returns_only_inter_confederation_pairs` alone was
    553s. Production keeps the retry; tests should not be measuring ESPN's
    patience. Retry BEHAVIOUR is covered by explicit mocks in test_http.py,
    which pass `attempts` directly and are unaffected by this.
    """
    from data_pipeline import http

    saved = (http._MAX_ATTEMPTS, http._MIN_INTERVAL)
    http._MAX_ATTEMPTS, http._MIN_INTERVAL = 1, 0.0
    yield
    http._MAX_ATTEMPTS, http._MIN_INTERVAL = saved

# Disable seleniumbase pytest plugin — system-installed seleniumbase conflicts
# with pytest-html absence.  Our tests don't use seleniumbase at all.
def pytest_configure(config):
    import sys
    for plugin_name in list(sys.modules.keys()):
        if "seleniumbase" in plugin_name:
            try:
                config.pluginmanager.unregister(plugin_name)
            except Exception:
                pass
