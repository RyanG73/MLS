"""
Playwright browser smoke tests for webapp/index.html.

Covers the Section-6 gaps from the Codex review:
  - No JavaScript console errors on any route
  - No visible NaN / undefined / [object Object] in rendered text
  - No horizontal overflow at desktop (1280px) or mobile (390px) widths
  - Preseason health renders status text rather than bogus percentages
  - Power route does not trigger the normal league favorite-card renderer
  - Placeholder routes render something rather than crashing

Run:
  venv/bin/python -m pytest tests/test_browser_smoke.py -v --browser chromium

Requires:
  venv/bin/playwright install chromium  (one-time, ~90 MB)
"""
import os
import re
import socket
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Generator

import pytest
from playwright.sync_api import ConsoleMessage, Page

WEBAPP_DIR = Path(__file__).parent.parent / "webapp"

# ── Local HTTP server fixture ─────────────────────────────────────────────────

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class _QuietHandler(SimpleHTTPRequestHandler):
    """Suppress HTTP access log noise during tests."""
    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def webapp_url() -> Generator[str, None, None]:
    """Serve webapp/ on a free local port for the duration of the test session.

    SimpleHTTPRequestHandler serves from os.getcwd(), so we chdir into the
    webapp directory before starting the server thread and restore cwd after.
    """
    port = _free_port()
    original_cwd = os.getcwd()
    os.chdir(WEBAPP_DIR)
    server = HTTPServer(("127.0.0.1", port), _QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.15)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    os.chdir(original_cwd)


# ── Route definitions ─────────────────────────────────────────────────────────

ROUTES = [
    {"id": "mls",         "desc": "MLS live season"},
    {"id": "epl",         "desc": "EPL preseason table"},
    {"id": "ucl",         "desc": "UCL knockout"},
    {"id": "canadian-pl", "desc": "Canadian PL placeholder"},
    {"id": "power",       "desc": "Cross-league power rankings"},
]

# Routes where the health tab is expected to exist
HEALTH_ROUTES = [r for r in ROUTES if r["id"] not in ("power", "canadian-pl")]

# ── Helpers ───────────────────────────────────────────────────────────────────

_BOGUS_PATTERN = re.compile(r"\bNaN\b|\bundefined\b|\[object Object\]")


def _attach_error_collector(page: Page) -> list[str]:
    """Attach a console listener; return the list it appends errors to."""
    errors: list[str] = []

    def _on_console(msg: ConsoleMessage):
        if msg.type == "error":
            errors.append(msg.text)

    page.on("console", _on_console)
    return errors


def _visible_body_text(page: Page) -> str:
    return page.locator("body").inner_text(timeout=5000)


def _scrolls_wider_than_viewport(page: Page) -> bool:
    return page.evaluate(
        "() => document.documentElement.scrollWidth > window.innerWidth"
    )


def _load_route(page: Page, base_url: str, league_id: str):
    page.goto(f"{base_url}/index.html?league={league_id}", wait_until="networkidle")
    page.wait_for_timeout(400)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestNoConsoleErrors:
    """Each route must load without JavaScript console errors."""

    @pytest.mark.parametrize("route", ROUTES, ids=[r["id"] for r in ROUTES])
    def test_no_console_errors_on_load(self, page: Page, webapp_url: str, route: dict):
        errors = _attach_error_collector(page)
        _load_route(page, webapp_url, route["id"])
        assert not errors, (
            f"Console errors on ?league={route['id']}:\n"
            + "\n".join(f"  {e}" for e in errors)
        )


class TestNoVisibleBogusValues:
    """No route or tab may display NaN, undefined, or [object Object]."""

    @pytest.mark.parametrize("route", ROUTES, ids=[r["id"] for r in ROUTES])
    def test_no_bogus_on_default_view(self, page: Page, webapp_url: str, route: dict):
        _load_route(page, webapp_url, route["id"])
        text = _visible_body_text(page)
        matches = _BOGUS_PATTERN.findall(text)
        assert not matches, (
            f"?league={route['id']} (default tab) shows: {set(matches)}"
        )

    @pytest.mark.parametrize("route", HEALTH_ROUTES, ids=[r["id"] for r in HEALTH_ROUTES])
    def test_no_bogus_on_health_tab(self, page: Page, webapp_url: str, route: dict):
        """Health tab was the specific source of NaN% in preseason leagues (Codex review)."""
        _load_route(page, webapp_url, route["id"])
        tab = page.locator('[data-view="health"]')
        if tab.count() == 0:
            pytest.skip(f"?league={route['id']} has no health tab")
        tab.click()
        page.wait_for_timeout(300)
        text = _visible_body_text(page)
        matches = _BOGUS_PATTERN.findall(text)
        assert not matches, (
            f"?league={route['id']} health tab shows: {set(matches)}"
        )


class TestNoHorizontalOverflow:
    """Page must not overflow horizontally at standard desktop or mobile widths.

    KNOWN ISSUE (mobile): The Codex review measured ~443px document width at a
    390px viewport — the table layout overflows before the CSS breakpoint pass
    is applied. These tests will fail on routes where overflow exists. They are
    intentionally left un-skipped to stay visible as open work items.
    """

    @pytest.mark.parametrize("route", ROUTES, ids=[r["id"] for r in ROUTES])
    def test_no_overflow_desktop(self, page: Page, webapp_url: str, route: dict):
        page.set_viewport_size({"width": 1280, "height": 800})
        _load_route(page, webapp_url, route["id"])
        assert not _scrolls_wider_than_viewport(page), (
            f"?league={route['id']} overflows horizontally at 1280px"
        )

    @pytest.mark.parametrize("route", ROUTES, ids=[r["id"] for r in ROUTES])
    def test_no_overflow_mobile(self, page: Page, webapp_url: str, route: dict):
        # KNOWN: mobile overflow documented in Codex review (443px at 390px viewport).
        # Failing tests here are intentional regression pins, not new bugs.
        page.set_viewport_size({"width": 390, "height": 844})
        _load_route(page, webapp_url, route["id"])
        assert not _scrolls_wider_than_viewport(page), (
            f"?league={route['id']} overflows horizontally at 390px"
        )


class TestRouteStateCorrectness:
    """Specific route-state invariants documented in the Codex review."""

    def test_power_does_not_crash_with_team_undefined_error(
        self, page: Page, webapp_url: str
    ):
        """Power route must not trigger the normal league favorite-card renderer.

        Codex review finding: loading ?league=power threw
        'TypeError: Cannot read properties of undefined (reading 'team')'
        because the normal league renderer ran before the power renderer.
        Left as a failing pin if the bug is still present.
        """
        errors = _attach_error_collector(page)
        _load_route(page, webapp_url, "power")
        team_errors = [
            e for e in errors
            if "team" in e.lower() and "undefined" in e.lower()
        ]
        assert not team_errors, (
            "Power route triggered 'team' undefined errors:\n"
            + "\n".join(f"  {e}" for e in team_errors)
        )

    def test_preseason_health_shows_no_bogus_percentages(
        self, page: Page, webapp_url: str
    ):
        """EPL is preseason — health tab must not render raw NaN% bars.

        Root cause (pre-fix): empty preseason frame → pandas mean() = NaN
        → json.dumps without allow_nan=False → NaN literal in payload
        → rendered as 'NaN%' in the health tab.
        """
        _load_route(page, webapp_url, "epl")
        health_tab = page.locator('[data-view="health"]')
        if health_tab.count() == 0:
            pytest.skip("EPL has no health tab in current build")
        health_tab.click()
        page.wait_for_timeout(300)
        text = _visible_body_text(page)
        assert "NaN" not in text, "EPL health tab renders 'NaN' — preseason NaN% bug still present"
        assert "undefined" not in text, "EPL health tab renders 'undefined events'"

    def test_placeholder_route_renders_content(self, page: Page, webapp_url: str):
        """canadian-pl is 'soon' — must render visible content, not a blank page."""
        _load_route(page, webapp_url, "canadian-pl")
        body_text = _visible_body_text(page).strip()
        assert body_text, "canadian-pl placeholder rendered a blank page"


class TestOddsDecimalFormatting:
    """Sub-1% odds in the league table must show one decimal, not round to '0'."""

    def test_epl_table_has_sub_one_percent_with_decimal(self, page: Page, webapp_url: str):
        _load_route(page, webapp_url, "epl")
        text = _visible_body_text(page)
        # EPL preseason title odds include several teams under 1% (e.g. Chelsea's title
        # odds in webapp/data/epl.js are 0.2%) — the table row must render "0.2", not a
        # bare "0", right after that team's name. A page-wide "0.X" regex would false-
        # positive on unrelated summary-card text (e.g. "VS MARKET +0.1%"), so anchor on
        # the specific row instead.
        idx = text.find("Chelsea")
        assert idx != -1, "Expected 'Chelsea' row in the EPL table"
        row_text = text[idx:idx + 60]
        assert "\n0.2\n" in row_text, (
            f"Expected Chelsea's sub-1% title-odds cell formatted as '0.2' near its row, got: {row_text!r}"
        )


class TestProjectedFinishConsistency:
    """The Projected Finish plot's team order must match the League Table's order —
    same team must not appear at a materially different rank in the two views."""

    def test_epl_finish_plot_matches_standings_order(self, page: Page, webapp_url: str):
        _load_route(page, webapp_url, "epl")
        standings_order = page.locator(".tlad .trow .tname").all_inner_texts()
        finish_order = page.locator(".plotpanel .frow b").all_inner_texts()
        assert standings_order == finish_order, (
            f"Standings order {standings_order} != Projected Finish order {finish_order}"
        )


class TestMlsTopBoxes:
    """MLS must show all 5 title-race boxes: Cup, Shield, East, West, Spoon."""

    def test_mls_shows_five_fav_cards(self, page: Page, webapp_url: str):
        _load_route(page, webapp_url, "mls")
        cards = page.locator(".fav")
        assert cards.count() == 5, f"Expected 5 .fav cards, got {cards.count()}"
        labels = page.locator(".fav .lab").all_inner_texts()
        # .fav .lab is CSS text-transform:uppercase, so inner_text() reflects the
        # rendered case ("MLS CUP") rather than the source markup — compare case-insensitively.
        assert any("mls cup" in l.lower() for l in labels), f"No MLS Cup card in {labels}"


class TestSquadValuePanel:
    """Squad value must render expanded by default with a 4-way position breakdown."""

    def test_squad_value_panel_is_open_and_shows_four_positions(self, page: Page, webapp_url: str):
        _load_route(page, webapp_url, "epl")
        page.locator('[data-view="teams"]').click()
        page.wait_for_timeout(300)
        panel = page.locator(".sv-panel").first
        assert "open" in (panel.get_attribute("class") or ""), "Squad value panel is not open by default"
        text = panel.inner_text()
        for label in ["Attack value", "Midfield value", "Defense value", "Goalkeeper value"]:
            assert label in text, f"Missing '{label}' row in squad value panel"
