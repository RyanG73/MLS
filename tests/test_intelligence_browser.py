from __future__ import annotations

import functools
import json
import os
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from api.index import handler as ApiHandler
from server.intel_auth import issue_access_token
from server.intel_store import get_or_create_user, set_plan
from server.kv_client import get_kv, reset_kv_for_tests

ROOT = Path(__file__).resolve().parent.parent
ARSENAL_ID = "v1:1c90591709108353"


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def intelligence_urls():
    reset_kv_for_tests()
    kv = get_kv()
    get_or_create_user(kv, "browser-user", "browser@example.test")
    set_plan(kv, "browser-user", "creator")
    token = issue_access_token(
        "dev-only-insecure-secret", "browser-user", "creator",
        ttl_seconds=3600)

    static_port, api_port = _port(), _port()
    static_origin = f"http://127.0.0.1:{static_port}"
    os.environ["ALLOWED_ORIGINS"] = static_origin

    static_handler = functools.partial(
        SimpleHTTPRequestHandler, directory=str(ROOT / "webapp"))
    static_server = ThreadingHTTPServer(("127.0.0.1", static_port), static_handler)
    api_server = ThreadingHTTPServer(("127.0.0.1", api_port), ApiHandler)
    threads = [
        threading.Thread(target=static_server.serve_forever, daemon=True),
        threading.Thread(target=api_server.serve_forever, daemon=True),
    ]
    for thread in threads:
        thread.start()
    query = (
        f"?league=intel&api=http%3A%2F%2F127.0.0.1%3A{api_port}%2Fv1"
        f"&intelLeague=epl&team={ARSENAL_ID}")
    try:
        yield {
            "page": static_origin + "/" + query,
            "token": token,
        }
    finally:
        static_server.shutdown()
        api_server.shutdown()
        reset_kv_for_tests()


def _open(page: Page, intelligence_urls, width=1280, height=900):
    page.set_viewport_size({"width": width, "height": height})
    page.add_init_script(
        "localStorage.setItem('entenser.intel.access', " +
        json.dumps(intelligence_urls["token"]) + ")")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(intelligence_urls["page"], wait_until="networkidle")
    expect(page.locator(".intel-command h1")).to_contain_text("Arsenal Intelligence")
    return errors


def test_all_26_features_render_across_hub_tabs(page: Page, intelligence_urls):
    errors = _open(page, intelligence_urls)
    seen = set()
    for tab in ("Today", "Explore", "History", "Studio"):
        page.get_by_role("button", name=tab, exact=True).click()
        page.wait_for_timeout(100)
        seen.update(
            int(value) for value in page.locator(".intel-feature").evaluate_all(
                "(nodes) => nodes.map((node) => node.id.replace('intel-feature-', ''))"))
    assert seen == set(range(1, 27))
    assert not errors
    assert "Sample" not in page.locator(".intel-app").inner_text()
    page.screenshot(path="/tmp/entenser-intelligence-desktop.png", full_page=True)


def test_scenario_card_and_journal_workflows(page: Page, intelligence_urls):
    _open(page, intelligence_urls)

    page.get_by_role("button", name="Explore", exact=True).click()
    first_home = page.locator("#intel-feature-5 [data-action=assume][data-outcome=H]").first
    first_home.click()
    page.locator("#intel-feature-5 [data-action=scenario-run]").click()
    expect(page.locator("#intel-feature-5 .intel-scenario-result")).to_contain_text(
        "Scenario", timeout=20_000)
    expect(page.locator(".intel-success")).to_contain_text("Scenario complete")

    page.get_by_role("button", name="Studio", exact=True).click()
    page.locator("#intel-feature-20 [data-action=create-card]").click()
    expect(page.locator("#intel-feature-20 .intel-success")).to_contain_text(
        "Verification URL", timeout=10_000)

    page.get_by_role("button", name="History", exact=True).click()
    page.locator("#intel-journal-notes").fill("Preseason checkpoint")
    page.locator("#intel-feature-26 [data-action=journal-save]").click()
    expect(page.locator("#intel-feature-26 .intel-journal-entry")).to_contain_text(
        "Preseason checkpoint", timeout=10_000)


def test_hub_mobile_has_no_document_overflow(page: Page, intelligence_urls):
    errors = _open(page, intelligence_urls, width=375, height=812)
    for tab in ("Today", "Explore", "History", "Studio"):
        page.get_by_role("button", name=tab, exact=True).click()
        page.wait_for_timeout(100)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth")
        assert overflow is False, tab
    assert not errors
    page.screenshot(path="/tmp/entenser-intelligence-mobile.png", full_page=True)
