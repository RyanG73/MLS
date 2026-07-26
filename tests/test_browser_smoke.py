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
import functools
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

    Serves via SimpleHTTPRequestHandler's directory= argument rather than
    os.chdir — a session-scoped chdir leaks into every later test file in a
    full-suite run and breaks any test that reads repo-relative paths (e.g.
    test_league_bridge reading data/parity_frame.parquet).
    """
    port = _free_port()
    handler = functools.partial(_QuietHandler, directory=str(WEBAPP_DIR))
    server = HTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.15)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


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
    # Static smoke tests do not run the optional local API. Fulfil the one
    # background public-config read so Chromium does not report a network
    # resource error unrelated to the page under test.
    page.route(
        "http://127.0.0.1:8787/v1/public/config",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"open_access":{"active":false},"pricing":{}}',
        ),
    )
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

    def test_power_is_discoverable_and_uses_one_global_rank(
        self, page: Page, webapp_url: str
    ):
        _load_route(page, webapp_url, "power")
        assert page.locator('.mast-bar a[href="?league=power"]').count() == 1
        ranks = page.locator(".pr-row .pr-rank").all_inner_texts()
        assert ranks[:5] == ["1", "2", "3", "4", "5"]
        page.locator('.pr-chip[data-conf="Concacaf"]').click()
        filtered = [int(value) for value in
                    page.locator(".pr-row .pr-rank").all_inner_texts()]
        assert filtered == sorted(filtered)
        assert filtered and filtered[0] > 1, (
            "Confederation filtering must preserve global ranks, not restart at 1"
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
        # EPL preseason title odds include several teams under 1% — the table row
        # must retain its decimal, not render a bare "0". A page-wide "0.X" regex would false-
        # positive on unrelated summary-card text (e.g. "VS MARKET +0.1%"), so anchor on
        # the specific row instead.
        team, value = page.evaluate(
            "() => { const s=D.standings.find(x=>x.title>0&&x.title<1); return [s.team,s.title]; }"
        )
        idx = text.find(team)
        assert idx != -1, f"Expected {team!r} row in the EPL table"
        row_text = text[idx:idx + 60]
        assert f"\n{value:.1f}\n" in row_text, (
            f"Expected {team}'s sub-1% title odds formatted as {value:.1f}, got: {row_text!r}"
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


class TestLeaguePageRaceFirstLayout:
    """Table leagues use the EPL race-first, full-width ladder template."""

    def test_epl_table_emphasizes_team_and_places_gp_gd_beside_points(
        self, page: Page, webapp_url: str
    ):
        page.set_viewport_size({"width": 1280, "height": 900})
        _load_route(page, webapp_url, "epl")
        headers = [
            h.lower()
            for h in page.locator(".tlad .thead > span").all_inner_texts()
        ]
        assert headers[1:7] == ["club", "pts", "gp", "gd", "proj", "global elo"]
        assert headers[-1] == "next 5 sim 🔒"
        assert page.locator(".tlad .tsub").count() == 0, (
            "League-table team cells should not retain the old GP/GD footnote"
        )
        type_sizes = page.evaluate(
            """() => ({
                header: parseFloat(getComputedStyle(document.querySelector('.tlad .thead')).fontSize),
                team: parseFloat(getComputedStyle(document.querySelector('.tlad .tname')).fontSize)
            })"""
        )
        assert type_sizes["header"] >= 10
        assert type_sizes["team"] >= 13

    def test_free_epl_next_five_sim_is_visible_but_locked(
        self, page: Page, webapp_url: str
    ):
        _load_route(page, webapp_url, "epl")
        rows = page.locator(".tlad .trow")
        locked = page.locator(".tlad .wgroup.wlocked")
        assert locked.count() == rows.count()
        assert locked.first.get_attribute("href") == "?league=intel"
        assert locked.first.get_attribute("data-upsell") == "next-5-sim"
        assert locked.first.locator(".wbox").count() == 5
        assert locked.first.locator(".wbox").first.get_attribute("data-gid") is None
        gate = page.locator(".tlad .sim-gate-overlay")
        assert gate.count() == 1
        assert gate.locator(".sg-boxes i").count() == 5
        assert (
            "See how probabilities change based on upcoming performances across the league"
            in (gate.text_content() or "")
        )
        assert gate.get_attribute("href") == "?league=intel"
        initial_gate_state = page.evaluate(
            """() => {
                const overlay = document.querySelector('.tlad .sim-gate-overlay');
                const style = getComputedStyle(overlay);
                return {opacity: Number(style.opacity), visibility: style.visibility};
            }"""
        )
        assert initial_gate_state == {"opacity": 0, "visibility": "hidden"}
        first_locked_box = locked.first.bounding_box()
        assert first_locked_box is not None
        page.mouse.move(
            first_locked_box["x"] + first_locked_box["width"] / 2,
            first_locked_box["y"] + first_locked_box["height"] / 2,
        )
        page.wait_for_timeout(150)
        disabled_style = page.evaluate(
            """() => {
                const group = document.querySelector('.tlad .wgroup.wlocked');
                const box = group.querySelector('.wbox');
                const overlay = document.querySelector('.tlad .sim-gate-overlay');
                const overlayRect = overlay.getBoundingClientRect();
                const groupRect = group.getBoundingClientRect();
                return {
                    opacity: Number(getComputedStyle(group).opacity),
                    background: getComputedStyle(box).backgroundColor,
                    overlayPosition: getComputedStyle(overlay).position,
                    overlayOpacity: Number(getComputedStyle(overlay).opacity),
                    overlayVisibility: getComputedStyle(overlay).visibility,
                    overlapsBoxes: overlayRect.right >= groupRect.left
                        && overlayRect.left <= groupRect.right
                        && overlayRect.bottom >= groupRect.top
                };
            }"""
        )
        assert disabled_style["opacity"] >= 0.5
        assert disabled_style["background"] != "rgba(0, 0, 0, 0)"
        assert disabled_style["overlayPosition"] == "absolute"
        assert disabled_style["overlayOpacity"] == 1
        assert disabled_style["overlayVisibility"] == "visible"
        assert disabled_style["overlapsBoxes"], (
            "The simulator explanation should visibly overlay the disabled controls"
        )
        assert "Next 5 Sim is available with Entenser Intel" in page.locator(
            "#laddernote"
        ).inner_text()
        assert "Projected ladder" not in page.locator("#view-outlook").inner_text()

    def test_epl_opening_run_uses_readable_bars_without_fixture_chips(
        self, page: Page, webapp_url: str
    ):
        _load_route(page, webapp_url, "epl")
        opening_run = page.locator(".plotpanel").filter(has_text="Opening run")
        assert opening_run.count() == 1
        assert opening_run.locator(".ri-row").count() > 0
        assert opening_run.locator(".ri-chip").count() == 0
        assert "chips =" not in opening_run.inner_text().lower()

    def test_entitled_epl_next_five_sim_remains_interactive(
        self, page: Page, webapp_url: str
    ):
        page.add_init_script(
            """(() => {
                const payload = btoa(JSON.stringify({exp: 4102444800, plan: 'intel'}))
                    .replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');
                localStorage.setItem('entenser.intel.access', `e30.${payload}.sig`);
            })()"""
        )
        _load_route(page, webapp_url, "epl")
        assert page.locator(".tlad .wgroup.wlocked").count() == 0
        assert page.locator(".tlad .thead .c-w5").inner_text() == "NEXT 5 SIM"
        first = page.locator(".tlad .wbox").first
        assert first.get_attribute("data-gid") is not None
        first.click()
        assert page.locator(".tlad .wbox.w").count() >= 1
        assert "use Next 5 Sim" in page.locator("#laddernote").inner_text()

    def test_epl_masthead_leads_with_identity_and_season_progress(
        self, page: Page, webapp_url: str
    ):
        _load_route(page, webapp_url, "epl")
        identity = page.locator(".brand")
        assert identity.locator("#leagueTitle").inner_text() == "Premier League"
        assert identity.locator("#sub > span:not(.data-clock)").all_inner_texts() == [
            "ENGLAND",
            "DIVISION 1",
        ]
        assert "Forecast" in identity.locator("#sub .data-clock").inner_text()
        status = page.locator("#acc")
        assert "PROJECTED SEASON\n26–27" in status.inner_text()
        assert "NEXT MATCH\nAug 21, 2026" in status.inner_text()
        assert "0.0 of 38" in status.inner_text()
        assert status.locator(".acc-nums").count() == 0, (
            "Model-performance metrics should no longer be in the league masthead"
        )
        assert (
            status.locator(".ss-track > span").get_attribute("style")
            == "width:0.0%"
        )

    def test_epl_model_performance_moves_to_trust(
        self, page: Page, webapp_url: str
    ):
        _load_route(page, webapp_url, "epl")
        page.get_by_role("tab", name="Trust").click()
        performance = page.locator(".trust-performance")
        assert performance.count() == 1
        text = performance.inner_text()
        assert "MODEL PERFORMANCE" in text
        assert "Model" in text
        assert "Naive" in text
        assert "Market" not in text

    def test_market_comparison_requires_entitlement_and_explicit_mode(
        self, page: Page, webapp_url: str
    ):
        page.add_init_script(
            """(() => {
                const payload = btoa(JSON.stringify({exp: 4102444800, plan: 'intel'}))
                    .replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');
                localStorage.setItem('entenser.intel.access', `e30.${payload}.sig`);
            })()"""
        )
        _load_route(page, webapp_url, "epl&market=1")
        page.get_by_role("tab", name="Trust").click()
        assert "Market" in page.locator(".trust-performance").inner_text()

    def test_market_query_without_valid_entitlement_stays_forecast_first(
        self, page: Page, webapp_url: str
    ):
        page.add_init_script(
            "localStorage.setItem('entenser.intel.access', 'not-a-token')"
        )
        _load_route(page, webapp_url, "epl&market=1")
        page.get_by_role("tab", name="Trust").click()
        assert "Market" not in page.locator(".trust-performance").inner_text()

    def test_midseason_masthead_uses_average_team_games_played(
        self, page: Page, webapp_url: str
    ):
        _load_route(page, webapp_url, "ireland-premier")
        gps = [int(v) for v in page.locator(".tlad .gpc").all_inner_texts()]
        assert len(set(gps)) > 1, "Fixture-imbalance test needs unequal GP values"
        expected = sum(gps) / len(gps)
        progress_text = page.locator("#acc .ss-progress-head b").inner_text()
        match = re.fullmatch(r"([0-9.]+) of ([0-9]+)", progress_text)
        assert match, f"Unexpected season-progress text: {progress_text!r}"
        displayed = float(match.group(1))
        assert displayed == pytest.approx(expected, abs=0.05)
        assert displayed < max(gps), "Header should use average GP, not the leader's GP"

    def test_epl_preseason_does_not_show_probability_point_movement(
        self, page: Page, webapp_url: str
    ):
        _load_route(page, webapp_url, "epl")
        assert page.locator(".race .rdelta").count() == 0
        movement = page.locator(".race-movement")
        deltas = movement.locator(".rm-delta").all_inner_texts()
        assert deltas and set(d.lower() for d in deltas) == {"preseason"}
        assert "pp" not in movement.inner_text().lower()
        assert "top six by current title" in movement.locator(".rm-foot").inner_text().lower()

    def test_epl_ladder_is_full_width_and_starts_in_first_viewport(
        self, page: Page, webapp_url: str
    ):
        page.set_viewport_size({"width": 1280, "height": 900})
        _load_route(page, webapp_url, "epl")
        layout = page.evaluate(
            """() => {
                const table = document.querySelector('.tlad').getBoundingClientRect();
                const outlook = document.querySelector('#view-outlook').getBoundingClientRect();
                return {
                    tableTop: table.top,
                    tableWidth: table.width,
                    outlookWidth: outlook.width,
                    viewportHeight: innerHeight
                };
            }"""
        )
        assert layout["tableTop"] < layout["viewportHeight"], (
            f"League ladder starts below the first viewport at {layout['tableTop']}px"
        )
        assert layout["tableWidth"] >= layout["outlookWidth"] * 0.98, (
            f"League ladder is not full width: {layout}"
        )

    def test_epl_trajectory_uses_isolated_contender_lanes(
        self, page: Page, webapp_url: str
    ):
        page.set_viewport_size({"width": 1280, "height": 900})
        _load_route(page, webapp_url, "epl")
        movement = page.locator(".race-movement")
        assert movement.count() == 1, "Expected one compact race-movement panel"
        lanes = movement.locator(".rm-row")
        assert 2 <= lanes.count() <= 6, (
            f"Expected at most six isolated contender lanes, got {lanes.count()}"
        )
        assert lanes.locator("svg").count() == lanes.count()
        assert movement.locator(".rm-axis").count() == lanes.count()
        assert movement.locator(".rm-axis").first.inner_text().splitlines() == [
            "Game 1",
            "Game 38",
        ]
        assert "0 of 38 games played" in movement.locator(
            ".panel-h .meta"
        ).inner_text()
        assert movement.locator(".rm-spark polyline").count() == 0, (
            "Preseason nightly snapshots should collapse to one dot, not form a line"
        )
        assert movement.locator(".rm-spark circle").count() == lanes.count()
        positions = page.evaluate(
            """() => {
                const table = document.querySelector('.tlad').getBoundingClientRect();
                const movement = document.querySelector('.race-movement').getBoundingClientRect();
                return {tableBottom: table.bottom, movementTop: movement.top};
            }"""
        )
        assert positions["movementTop"] >= positions["tableBottom"], (
            f"Trajectory should follow the ladder: {positions}"
        )

    def test_epl_trajectory_rotates_projection_categories(
        self, page: Page, webapp_url: str
    ):
        _load_route(page, webapp_url, "epl")
        movement = page.locator(".race-movement")
        switches = movement.locator(".rm-switch")
        assert switches.all_inner_texts() == ["TITLE", "CHAMPIONS LG", "RELEGATION"]
        assert "rotates every 7 sec" in movement.locator(
            ".rm-rotate-note"
        ).inner_text()

        movement.get_by_role("button", name="Relegation").click()
        assert "RELEGATION MOVEMENT" in movement.locator(
            ".panel-h h2"
        ).inner_text()
        assert "top six by current relegation likelihood" in movement.locator(
            ".rm-foot"
        ).inner_text().lower()

        # Outside preseason, non-title/relegation races prioritize the six
        # largest absolute changes rather than the six current leaders.
        page.evaluate(
            """() => {
                D.outlook.preseason = false;
                renderRaceHistory('ucl');
            }"""
        )
        assert "CHAMPIONS LG MOVEMENT" in movement.locator(
            ".panel-h h2"
        ).inner_text()
        assert "six largest champions lg likelihood changes" in movement.locator(
            ".rm-foot"
        ).inner_text().lower()

    def test_midseason_trajectory_stops_at_current_game_progress(
        self, page: Page, webapp_url: str
    ):
        page.set_viewport_size({"width": 1280, "height": 900})
        _load_route(page, webapp_url, "ireland-premier")
        movement = page.locator(".race-movement")
        assert movement.count() == 1
        progress = page.evaluate(
            """() => {
                const spark = document.querySelector('.race-movement .rm-spark svg');
                const marker = spark.querySelector('circle');
                const progress = spark.querySelector('.rm-progress');
                const width = Number(spark.getAttribute('viewBox').split(/\\s+/)[2]);
                return {
                    x: Number(marker.getAttribute('cx')),
                    progressX: Number(progress.getAttribute('x2')),
                    width,
                    meta: document.querySelector('.race-movement .panel-h .meta').textContent
                };
            }"""
        )
        assert 2 < progress["x"] < progress["width"] - 2, (
            f"Midseason trajectory marker should stop before season end: {progress}"
        )
        assert 2 < progress["progressX"] < progress["width"] - 2, (
            f"Midseason progress rail should be only partially filled: {progress}"
        )
        assert "games played" in progress["meta"]


class TestLeagueMatchProjectionControls:
    def test_epl_matches_default_to_today_with_compact_controls_and_calendar(
        self, page: Page, webapp_url: str
    ):
        page.set_viewport_size({"width": 1280, "height": 900})
        _load_route(page, webapp_url, "epl")
        page.get_by_role("tab", name="Match Projections").click()

        today = page.evaluate("() => localYMD(new Date())")
        assert page.locator("#teamDD").count() == 1
        assert page.locator("#resultFilter").count() == 0
        assert page.locator("#marketPanel").count() == 0
        assert page.locator(f'.date-btn[data-date="{today}"]').get_attribute(
            "aria-selected"
        ) == "true"

        calendar_button = page.locator("#calBtn")
        assert calendar_button.get_attribute("aria-expanded") == "false"
        calendar_button.click()
        assert calendar_button.get_attribute("aria-expanded") == "true"
        calendar = page.locator("#calMenu")
        assert calendar.is_visible()
        today_cell = calendar.locator(f'.cal-day[data-date="{today}"]')
        assert today_cell.count() == 1
        assert "active" in (today_cell.get_attribute("class") or "")

    def test_midseason_calendar_can_navigate_back_to_a_played_match(
        self, page: Page, webapp_url: str
    ):
        page.set_viewport_size({"width": 1280, "height": 900})
        _load_route(page, webapp_url, "ireland-premier")
        page.get_by_role("tab", name="Match Projections").click()
        past_date = page.evaluate(
            """() => {
                const today = localYMD(new Date());
                return D.games.filter(g => g.result != null)
                    .map(matchDate).filter(d => d < today).sort().at(-1) || null;
            }"""
        )
        assert past_date, "Midseason calendar test needs a completed match"
        expected_label = page.evaluate("(d) => longDate(d)", past_date)

        page.locator("#calBtn").click()
        target = page.locator(f'.cal-day[data-date="{past_date}"]')
        for _ in range(24):
            if target.count():
                break
            prev = page.locator("#calPrev")
            assert not prev.is_disabled(), (
                f"Could not navigate calendar back to played date {past_date}"
            )
            prev.click()
        assert target.count() == 1
        target.click()
        assert expected_label in page.locator("#calBtn").inner_text()
        assert int(page.locator("#gcount").inner_text().split()[0]) > 0


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


class TestTeamsDashboard:
    """Teams tab is a single-club dashboard with intentional selection priority."""

    def test_projection_leader_is_default_and_private_modules_are_absent(
        self, page: Page, webapp_url: str
    ):
        _load_route(page, webapp_url, "epl")
        page.locator('[data-view="teams"]').click()
        page.wait_for_timeout(300)
        view = page.locator("#view-teams")
        expected = page.evaluate(
            "() => [...D.standings].sort((a,b)=>(b.title??-1)-(a.title??-1))[0].team"
        )
        assert page.locator("#profileTeamSel").inner_text() == expected
        assert view.locator(".elo-grid, .elo-card, #matchupBox").count() == 0
        text = view.inner_text().lower()
        assert "trophies" not in text
        assert "model inputs" not in text
        assert "matchup odds" not in text
        assert "club news" in text

    def test_elo_chart_has_three_league_reference_lines(
        self, page: Page, webapp_url: str
    ):
        _load_route(page, webapp_url, "epl")
        page.locator('[data-view="teams"]').click()
        chart = page.locator("#view-teams .elo-svg")
        assert chart.locator(".elo-ref").count() == 3
        labels = chart.locator(".elo-ref-label").evaluate_all(
            "(els) => els.map(el => el.textContent)"
        )
        assert any("Top 25% starts" in label for label in labels)
        assert any("League average" in label for label in labels)
        assert any("Bottom 25% starts" in label for label in labels)

    def test_team_dropdown_changes_the_selected_club(
        self, page: Page, webapp_url: str
    ):
        _load_route(page, webapp_url, "epl")
        page.locator('[data-view="teams"]').click()
        page.locator("#profileTeamBtn").click()
        page.locator('#profileTeamMenu [data-team="Manchester City"]').click()
        assert page.locator("#profileTeamSel").inner_text() == "Manchester City"
        assert page.locator("#teamProfile .prof-hd h2").inner_text() == "Manchester City"

    def test_league_favorite_overrides_projection_leader(
        self, page: Page, webapp_url: str
    ):
        page.add_init_script(
            """localStorage.setItem(
                'pitchside.favTeams',
                JSON.stringify([{league: 'epl', team: 'Manchester City'}])
            )"""
        )
        _load_route(page, webapp_url, "epl")
        page.locator('[data-view="teams"]').click()
        assert page.locator("#profileTeamSel").inner_text() == "Manchester City"

    def test_team_deep_link_overrides_the_default(
        self, page: Page, webapp_url: str
    ):
        page.goto(
            f"{webapp_url}/index.html?league=epl&team=Manchester%20United",
            wait_until="networkidle",
        )
        page.wait_for_timeout(300)
        assert page.locator('[data-view="teams"]').get_attribute("aria-selected") == "true"
        assert page.locator("#profileTeamSel").inner_text() == "Manchester United"

    def test_squad_value_is_condensed_inside_season_outlook(
        self, page: Page, webapp_url: str
    ):
        _load_route(page, webapp_url, "epl")
        page.locator('[data-view="teams"]').click()
        panel = page.locator(".team-outlook .outlook-squad")
        text = panel.inner_text()
        assert "squad value" in text.lower()
        assert "€" in text
        for label in ["Attack", "Midfield", "Defense", "Goalkeeper"]:
            assert label in text
        assert panel.locator(".outlook-squad-row").count() == 4
        assert panel.locator(".outlook-squad-row i").count() == 0
        assert page.locator(".sv-panel").count() == 0

    def test_outlook_and_trajectory_match_and_trajectory_uses_season_axis(
        self, page: Page, webapp_url: str
    ):
        page.set_viewport_size({"width": 1280, "height": 900})
        _load_route(page, webapp_url, "epl")
        page.locator('[data-view="teams"]').click()
        cards = page.locator(".team-primary-card")
        assert cards.count() == 2
        heights = cards.evaluate_all(
            "(els) => els.map(el => el.getBoundingClientRect().height)"
        )
        assert abs(heights[0] - heights[1]) <= 1
        chart = page.locator(".team-traj-chart")
        season_games = int(chart.get_attribute("data-season-games"))
        assert season_games == 38
        chart_text = page.locator(".team-trajectory").inner_text()
        assert "Game 1" in chart_text
        assert "Game 38" in chart_text
        legend = page.locator(".team-traj-legend [data-projection]")
        assert legend.count() == 5
        assert legend.evaluate_all(
            "(els) => els.map(el => el.dataset.projection)"
        ) == ["title", "ucl", "europa", "conf", "releg"]
        assert page.locator(".team-trajectory svg circle").count() == legend.count()
        assert int(chart.get_attribute("data-trajectory-series")) == legend.count()

    def test_news_precedes_full_season_fixture_ledger(
        self, page: Page, webapp_url: str
    ):
        _load_route(page, webapp_url, "epl")
        page.locator('[data-view="teams"]').click()
        view_text = page.locator("#view-teams").inner_text()
        assert "Recent results" not in view_text
        order = page.locator(".prof-grid").evaluate(
            """el => [...el.children].map(child => {
                if (child.classList.contains('team-news')) return 'news';
                if (child.classList.contains('season-fixtures')) return 'fixtures';
                return 'other';
            })"""
        )
        assert order.index("news") < order.index("fixtures")
        fixture_count = page.locator(".sf-row").count()
        expected = page.evaluate(
            """() => {
                const team = document.querySelector('#profileTeamSel').textContent;
                return D.games.filter(g => g.home === team || g.away === team).length;
            }"""
        )
        assert fixture_count == expected
        assert page.locator(".sf-head").inner_text().splitlines()[-2:] == [
            "PRE-MATCH WIN",
            "RESULT",
        ]

    def test_fixture_probability_and_result_colors_follow_rules(
        self, page: Page, webapp_url: str
    ):
        _load_route(page, webapp_url, "mls")
        page.locator('[data-view="teams"]').click()
        errors = page.locator(".sf-row").evaluate_all(
            """rows => rows.flatMap(row => {
                const team = Number(row.dataset.teamWin);
                const opponent = Number(row.dataset.opponentWin);
                const expected = team > .5 ? 'favored'
                    : opponent > .5 ? 'tough' : 'balanced';
                return row.classList.contains(expected) ? [] : [row.dataset];
            })"""
        )
        assert not errors
        surface_styles = page.locator(".sf-row").evaluate_all(
            """rows => rows.map(row => {
                const probability = row.querySelector('.sf-prob');
                return {
                    rowBackground: getComputedStyle(row).backgroundColor,
                    probabilityBackground: getComputedStyle(probability).backgroundColor,
                    probabilityColor: getComputedStyle(probability).color,
                };
            })"""
        )
        assert {style["rowBackground"] for style in surface_styles} == {
            "rgba(0, 0, 0, 0)"
        }
        assert all(
            style["probabilityBackground"] != "rgba(0, 0, 0, 0)"
            for style in surface_styles
        )
        results = page.locator(".sf-result").evaluate_all(
            """els => els.map(el => ({
                text: el.textContent.trim(),
                cls: el.className
            })).filter(x => x.text !== '—')"""
        )
        assert results, "Expected completed MLS fixtures"
        for result in results:
            if result["text"] == "W":
                assert "win" in result["cls"]
            elif result["text"] == "T":
                assert "tie" in result["cls"]
            else:
                assert result["text"] == "L"
                assert "loss" in result["cls"]

    def test_mobile_dashboard_stacks_without_page_overflow(
        self, page: Page, webapp_url: str
    ):
        page.set_viewport_size({"width": 390, "height": 844})
        _load_route(page, webapp_url, "epl")
        page.locator('[data-view="teams"]').click()
        layout = page.evaluate(
            """() => ({
                width: document.documentElement.scrollWidth,
                viewport: window.innerWidth,
                columns: getComputedStyle(document.querySelector('.prof-grid'))
                    .gridTemplateColumns.split(' ').length
            })"""
        )
        assert layout["columns"] == 1
        assert layout["width"] <= layout["viewport"] + 1


class TestForecastFirstPublicLayer:
    _TRADING_TERMS = re.compile(
        r"\b(odds|bet|betting|edge|kelly|stake|staking|bookmaker|sportsbook|"
        r"wager|roi|clv|market)\b",
        re.IGNORECASE,
    )

    @pytest.mark.parametrize("route", ["command", "support", "account", "about"])
    def test_default_public_routes_are_forecast_first(
        self, page: Page, webapp_url: str, route: str
    ):
        _load_route(page, webapp_url, route)
        active = page.locator("#view-outlook")
        assert active.is_visible()
        match = self._TRADING_TERMS.search(active.inner_text())
        assert match is None, f"?league={route} exposes '{match.group(0)}'"

    def test_default_league_analysis_tabs_are_forecast_first(
        self, page: Page, webapp_url: str
    ):
        _load_route(page, webapp_url, "epl")
        for view, label in (
            ("outlook", "League Projections"),
            ("matches", "Match Projections"),
            ("teams", "Teams"),
            ("health", "Trust"),
        ):
            page.get_by_role("tab", name=label, exact=True).click()
            surface = page.locator(f"#view-{view}")
            text = surface.inner_text()
            match = self._TRADING_TERMS.search(text)
            assert match is None, (
                f"EPL {label} exposes '{match.group(0)}': "
                f"{text[max(0, match.start() - 80):match.end() + 80]}"
            )


class TestMatchesGroupedByDateAndLeague:
    """?league=command is a dense, prioritized matchday board."""

    def test_matches_view_has_day_strip_and_fixture_rows(self, page: Page, webapp_url: str):
        page.set_viewport_size({"width": 1280, "height": 900})
        page.goto(f"{webapp_url}/index.html?league=command", wait_until="networkidle")
        page.wait_for_timeout(400)
        title = page.title()
        assert title == "Entenser — Matches", f"Expected title 'Entenser — Matches', got {title!r}"
        assert page.locator(".cal-strip .cal-box").count() > 0, "Expected calendar day boxes"
        # fixture rows only render when the selected day has matches — skip
        # gracefully in a quiet data window rather than asserting on scraped state.
        if page.locator(".eb-empty").count() > 0:
            pytest.skip("no matches on the selected day in the current data window")
        assert page.locator(".mxcard").count() > 0, "Expected at least one compact fixture row"
        columns = page.locator(".fxp-columns").evaluate(
            "(el) => getComputedStyle(el).gridTemplateColumns.split(' ').length"
        )
        assert columns == 2, f"Expected two desktop fixture columns, got {columns}"

    def test_matches_are_prioritized_and_chronological(self, page: Page, webapp_url: str):
        page.set_viewport_size({"width": 1280, "height": 900})
        page.goto(f"{webapp_url}/index.html?league=command", wait_until="networkidle")
        page.wait_for_timeout(400)
        groups = page.locator(".fxp-columns .mx-group")
        if groups.count() < 2:
            pytest.skip("not enough league groups on the selected day")

        priorities = groups.evaluate_all(
            "(els) => els.map(el => Number(el.dataset.priority))"
        )
        column_tops = page.locator(".fxp-columns .fxp-col").evaluate_all(
            """(cols) => cols.map(col => {
                const group = col.querySelector('.mx-group');
                return group ? {
                    league: group.dataset.league,
                    priority: Number(group.dataset.priority)
                } : null;
            }).filter(Boolean)"""
        )
        assert sorted(item["priority"] for item in column_tops) == sorted(priorities)[:2]

        out_of_order = groups.evaluate_all(
            """(els) => els.flatMap(group => {
                const times = [...group.querySelectorAll('.mxcard')]
                    .map(row => Date.parse(row.dataset.ko))
                    .filter(Number.isFinite);
                return times.some((time, i) => i && time < times[i - 1])
                    ? [group.dataset.league] : [];
            })"""
        )
        assert out_of_order == [], f"Fixtures not chronological in: {out_of_order}"

        favorite = groups.evaluate_all("(els) => els[els.length - 1].dataset.league")
        page.evaluate(
            """(league) => localStorage.setItem(
                'pitchside.favLeagues', JSON.stringify([league])
            )""",
            favorite,
        )
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(300)
        top_leagues = page.locator(".fxp-columns .fxp-col").evaluate_all(
            """(cols) => cols.map(col => {
                const group = col.querySelector('.mx-group');
                return group && group.dataset.league;
            }).filter(Boolean)"""
        )
        assert favorite in top_leagues

    @pytest.mark.parametrize("width", [1280, 390], ids=["desktop", "mobile"])
    def test_matches_board_has_no_page_overflow(
        self, page: Page, webapp_url: str, width: int
    ):
        page.set_viewport_size({"width": width, "height": 900})
        page.goto(f"{webapp_url}/index.html?league=command", wait_until="networkidle")
        page.wait_for_timeout(400)
        assert not _scrolls_wider_than_viewport(page), (
            f"Matches board overflows horizontally at {width}px"
        )


class TestUiFeedbackRound2:
    """2026-07-09 feedback batch: finish-axis alignment + untruncated club names."""

    @pytest.mark.parametrize("width", [1280, 390], ids=["desktop", "mobile"])
    def test_finish_axis_ticks_align_with_bar_track(self, page: Page, webapp_url: str, width: int):
        page.set_viewport_size({"width": width, "height": 900})
        _load_route(page, webapp_url, "epl")
        offsets = page.evaluate(
            """() => {
                const ticks = document.querySelectorAll('.plot .faxis .fax span');
                const track = document.querySelector('.plot .ftrack');
                if (!ticks.length || !track) return null;
                const tr = track.getBoundingClientRect();
                const first = ticks[0].getBoundingClientRect();
                const last = ticks[ticks.length - 1].getBoundingClientRect();
                return {first: Math.abs(first.left - tr.left),
                        last: Math.abs(last.right - tr.right)};
            }"""
        )
        assert offsets is not None, "projected-finish plot did not render"
        assert offsets["first"] <= 6, f"tick '1' is {offsets['first']:.0f}px off the track start"
        assert offsets["last"] <= 6, f"last tick is {offsets['last']:.0f}px off the track end"

    @pytest.mark.parametrize("route", ["epl", "championship", "mls"])
    @pytest.mark.parametrize("width", [1280, 390], ids=["desktop", "mobile"])
    def test_no_truncated_club_names(self, page: Page, webapp_url: str, route: str, width: int):
        page.set_viewport_size({"width": width, "height": 900})
        _load_route(page, webapp_url, route)
        clipped = page.evaluate(
            """() => [...document.querySelectorAll('.ladder .tname')]
                .filter(el => el.scrollWidth > el.clientWidth + 1)
                .map(el => el.textContent)"""
        )
        assert clipped == [], f"truncated club names at {width}px: {clipped}"
