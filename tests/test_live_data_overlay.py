"""Recency guard on both `live-data` overlays.

Two consumers replace payloads with the `live-data` branch's copy, and until
2026-08-23 neither compared the `generated` stamp both sides already carry:

  * `.github/workflows/refresh-fast.yml` piped the whole branch over the
    checkout, so a frozen branch rolled committed payloads backwards while
    `webapp/leagues.js` stayed on `main`. `validate_payloads.py` then failed the
    run on the disagreement it had just manufactured — before the publish step,
    so the run that would have refreshed the branch was the run that died.
    `canadian-pl` and `k-league-1` were stuck that way for 19 days.

  * `webapp/index.html` assigns the branch copy over `window.<VAR>` for readers
    on entenser.com. That one carried a second defect the stamp check makes
    visible: it ran BEFORE the document.write()n same-origin payload rather than
    after it, so the deployed file overwrote the overlay and it had never once
    applied. Measured live on 2026-08-23 — `?league=epl` served the deployed
    2026-08-03 06:53 UTC payload while a 2026-08-23 14:17 UTC copy sat on the
    branch.

The rule both now share is one sentence: a `live-data` payload is used only when
its stamp is provably newer. Unreadable loses, so an overlay can only ever move
a payload forward in time.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts import overlay_live_data as overlay

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "webapp" / "index.html"
WORKFLOW = ROOT / ".github" / "workflows" / "refresh-fast.yml"

FROZEN = "2026-08-04 13:05 UTC"      # the branch tip that sat there for 19 days
COMMITTED = "2026-08-23 11:16 UTC"   # what `main` carried while it did
FRESH = "2026-08-23 14:17 UTC"       # a branch that is actually being published


def _payload(path: Path, generated: str | None, **extra) -> None:
    body = dict(extra)
    if generated is not None:
        body["generated"] = generated
    path.write_text(f"window.LEAGUE_DATA = {json.dumps(body)};")


@pytest.fixture()
def trees(tmp_path):
    """(branch snapshot, checkout) — the two sides the CI step reconciles."""
    live, dest = tmp_path / "live", tmp_path / "dest"
    live.mkdir()
    dest.mkdir()
    return live, dest


def _status(path: Path) -> str:
    return overlay.read_js_payload(path)["data_status"]


# ── the stamp itself ────────────────────────────────────────────────────────
@pytest.mark.parametrize("value,expected", [
    ("2026-08-23 11:20 UTC", dt.datetime(2026, 8, 23, 11, 20, tzinfo=dt.timezone.utc)),
    ("2026-08-23 11:20:07 UTC", dt.datetime(2026, 8, 23, 11, 20, 7, tzinfo=dt.timezone.utc)),
    ("2026-08-23T11:20Z", dt.datetime(2026, 8, 23, 11, 20, tzinfo=dt.timezone.utc)),
    ("2026-08-23 11:20", dt.datetime(2026, 8, 23, 11, 20, tzinfo=dt.timezone.utc)),
])
def test_stamp_reads_the_published_format(value, expected):
    assert overlay.stamp({"generated": value}) == expected


@pytest.mark.parametrize("payload", [
    {"generated": "unknown"},          # garbage that string-compares ABOVE any date
    {"generated": "2026-02-30 10:00 UTC"},   # well-formed, not a real day
    {"generated": ""},
    {"generated": None},
    {},                                 # logos.js / search-index.js carry no stamp
    None,                               # unparseable file
    "not a payload",
])
def test_an_unreadable_stamp_is_none_rather_than_a_guess(payload):
    assert overlay.stamp(payload) is None


# ── the decision ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("live,committed,take", [
    (FRESH, "2026-08-03 06:53 UTC", True),    # the branch is doing its job
    (FROZEN, COMMITTED, False),               # the branch is frozen
    (COMMITTED, COMMITTED, False),            # nothing to gain, don't churn
    ("unknown", COMMITTED, False),            # incoming unreadable — fail closed
    (None, COMMITTED, False),
    (FRESH, "unknown", False),                # can't prove newer — fail closed
    (None, None, False),
])
def test_the_branch_copy_wins_only_when_provably_newer(live, committed, take):
    decision = overlay.decide("x.js", {"generated": live}, {"generated": committed})
    assert decision.take is take, decision.describe()


# ── the 19-day deadlock, both halves ───────────────────────────────────────
def test_the_blanket_overlay_is_what_rolled_the_payload_backwards(trees):
    """Pin the defect this replaces.

    `git archive origin/live-data webapp/data | tar -x` takes the branch copy
    unconditionally. That is exactly how a `historical` payload from a branch
    frozen on 2026-08-04 landed on top of a committed `full_forecast` one and
    put the payload at odds with `webapp/leagues.js`.
    """
    live, dest = trees
    _payload(live / "canadian-pl.js", FROZEN, data_status="historical")
    _payload(dest / "canadian-pl.js", COMMITTED, data_status="full_forecast")

    shutil.copyfile(live / "canadian-pl.js", dest / "canadian-pl.js")   # the old step

    assert _status(dest / "canadian-pl.js") == "historical", (
        "the unguarded overlay must reproduce the regression, or this test is "
        "not pinning the defect the guard exists to prevent")


def test_the_guard_keeps_the_committed_payload_when_the_branch_is_frozen(trees):
    live, dest = trees
    _payload(live / "canadian-pl.js", FROZEN, data_status="historical")
    _payload(live / "k-league-1.js", FROZEN, data_status="historical")
    _payload(dest / "canadian-pl.js", COMMITTED, data_status="full_forecast")
    _payload(dest / "k-league-1.js", COMMITTED, data_status="full_forecast")

    decisions = overlay.plan(live, dest)
    assert overlay.apply(decisions, live, dest) == 0
    assert _status(dest / "canadian-pl.js") == "full_forecast"
    assert _status(dest / "k-league-1.js") == "full_forecast"
    assert all("older" in d.reason for d in decisions), [d.reason for d in decisions]


def test_a_branch_that_is_being_published_still_overlays(trees):
    """The guard must not cost the fast path its whole reason for existing."""
    live, dest = trees
    _payload(live / "epl.js", FRESH, data_status="full_forecast")
    _payload(dest / "epl.js", "2026-08-03 06:53 UTC", data_status="full_forecast")

    assert overlay.apply(overlay.plan(live, dest), live, dest) == 1
    assert overlay.read_js_payload(dest / "epl.js")["generated"] == FRESH


def test_a_payload_only_on_the_branch_is_not_resurrected(trees):
    """`main` is the authority on which leagues exist."""
    live, dest = trees
    _payload(live / "retired-league.js", FRESH, data_status="historical")
    _payload(dest / "epl.js", COMMITTED, data_status="full_forecast")

    overlay.apply(overlay.plan(live, dest), live, dest)
    assert not (dest / "retired-league.js").exists()


def test_a_stampless_payload_keeps_the_checkout_copy(trees):
    """logos.js / search-index.js / europe-map.js carry no `generated`."""
    live, dest = trees
    (live / "logos.js").write_text('window.TEAM_LOGOS = {"a":"branch"};')
    (dest / "logos.js").write_text('window.TEAM_LOGOS = {"a":"checkout"};')

    overlay.apply(overlay.plan(live, dest), live, dest)
    assert overlay.read_js_payload(dest / "logos.js") == {"a": "checkout"}


def test_a_missing_snapshot_is_not_a_failed_run(trees):
    """The old step swallowed a failed fetch with `|| true`; keep that."""
    live, dest = trees
    _payload(dest / "epl.js", COMMITTED, data_status="full_forecast")

    assert overlay.main(["--from", str(live / "nope"), "--into", str(dest)]) == 0
    assert _status(dest / "epl.js") == "full_forecast"


def test_the_cli_reports_what_it_did(trees, capsys):
    live, dest = trees
    _payload(live / "epl.js", FRESH, data_status="full_forecast")
    _payload(live / "canadian-pl.js", FROZEN, data_status="historical")
    _payload(dest / "epl.js", "2026-08-03 06:53 UTC", data_status="full_forecast")
    _payload(dest / "canadian-pl.js", COMMITTED, data_status="full_forecast")

    assert overlay.main(["--from", str(live), "--into", str(dest)]) == 0
    out = capsys.readouterr().out
    assert "live-data overlay: 1 newer of 2 compared" in out
    assert "keep  canadian-pl.js" in out and "take  epl.js" in out


def test_dry_run_reports_without_writing(trees, capsys):
    live, dest = trees
    _payload(live / "epl.js", FRESH, data_status="full_forecast")
    _payload(dest / "epl.js", COMMITTED, data_status="full_forecast")

    assert overlay.main(["--from", str(live), "--into", str(dest), "--dry-run"]) == 0
    assert "1 newer of 1 compared" in capsys.readouterr().out
    assert overlay.read_js_payload(dest / "epl.js")["generated"] == COMMITTED


# ── the CI step actually calls it ──────────────────────────────────────────
def _overlay_step() -> dict:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["refresh"]["steps"]
    matches = [s for s in steps if "live-data snapshot" in s.get("name", "")]
    assert len(matches) == 1, [s.get("name") for s in steps]
    return matches[0]


def test_the_workflow_routes_the_snapshot_through_the_guard():
    run = _overlay_step()["run"]
    assert "scripts/overlay_live_data.py" in run
    assert "git archive origin/live-data" in run, "still needs the snapshot"


def test_nothing_untars_the_branch_straight_over_the_checkout():
    """`tar -x` without `-C` lands in the working tree — the original defect."""
    run = _overlay_step()["run"]
    assert re.search(r"tar\s+-x(?!\s+-C)", run) is None, run
    assert "RUNNER_TEMP" in run, "extract to a scratch dir, not over webapp/data"


def test_the_guard_runs_after_the_runtime_is_installed():
    """It imports scripts.payload_utils; the `--select` step's bare-python
    constraint (test_refresh_ci_contract) does not extend to this one."""
    names = [s.get("name", "") or s.get("uses", "")
             for s in yaml.safe_load(WORKFLOW.read_text())["jobs"]["refresh"]["steps"]]
    assert names.index("Install fast-path runtime") < names.index(
        "Overlay prior live-data snapshot")


# ── the browser half ───────────────────────────────────────────────────────
def _overlay_js() -> str:
    """The shipped implementation, verbatim. Tests the file, not a copy."""
    src = INDEX.read_text()
    start = src.index("const _LIVE_FILE_RE=")
    end = src.index("};", src.index("const _writeOverlay=")) + 2
    return src[start:end]


def test_no_call_site_runs_the_overlay_inline():
    """The ordering defect, pinned.

    A document.write()n <script> executes when the parser resumes — after the
    whole inline block. Calling `_overlayLiveData` directly from that block
    therefore assigns `window.LEAGUE_DATA` a moment before the deployed payload
    overwrites it. Every call site must defer through `_writeOverlay`, which
    puts the call into the stream behind the payload script.
    """
    offenders = [
        line.strip() for line in INDEX.read_text().splitlines()
        if "_overlayLiveData(" in line
        and "const _overlayLiveData" not in line
        and "document.write" not in line
    ]
    assert offenders == [], offenders


def test_the_payload_script_is_written_before_the_overlay():
    src = INDEX.read_text()
    assert (src.index("""document.write('<scr'+'ipt src="data/'""")
            < src.index("_writeOverlay((_homeDataRoute"))


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_the_browser_guard_compares_the_generated_stamp():
    """Drive the shipped `_overlayLiveData` in a real JS engine.

    Stubs only the two host objects it touches (XMLHttpRequest, document) so
    the parsing, the comparison and the assignment under test are the real
    ones.
    """
    cases = [
        # (branch stamp, deployed stamp, expected winner)
        (FRESH, "2026-08-03 06:53 UTC", "live"),     # branch publishing normally
        ("2026-08-02 09:14 UTC", "2026-08-23 11:20 UTC", "deployed"),   # frozen
        ("2026-08-23 11:20 UTC", "2026-08-23 11:20 UTC", "deployed"),   # equal
        ("unknown", "2026-08-23 11:20 UTC", "deployed"),                # garbage
        (None, "2026-08-23 11:20 UTC", "deployed"),                     # absent
        (FRESH, "unknown", "deployed"),          # can't prove newer — fail closed
        (FRESH, None, "live"),          # nothing deployed: anything beats nothing
    ]
    script = """
    const CASES = %s;
    const _LIVE_DATA_BASE = 'https://live.test/';
    let RESPONSE = '';
    const document = { write() {} };
    const window = {};
    function XMLHttpRequest() {
      this.open = function () {};
      this.send = function () { this.status = 200; this.responseText = RESPONSE; };
    }
    %s
    const out = CASES.map(([live, deployed]) => {
      const branch = {who: 'live'};
      if (live !== null) branch.generated = live;
      RESPONSE = 'window.LEAGUE_DATA = ' + JSON.stringify(branch) + ';';
      if (deployed === null) { delete window.LEAGUE_DATA; }
      else {
        const d = {who: 'deployed'};
        if (deployed !== 'ABSENT') d.generated = deployed;
        window.LEAGUE_DATA = d;
      }
      const applied = _overlayLiveData('epl.js');
      return {who: window.LEAGUE_DATA.who, applied: applied};
    });
    console.log(JSON.stringify(out));
    """ % (json.dumps([[live, deployed] for live, deployed, _ in cases]),
           _overlay_js())

    result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    got = json.loads(result.stdout)
    for (live, deployed, expected), actual in zip(cases, got):
        assert actual["who"] == expected, (
            f"branch={live!r} deployed={deployed!r}: expected {expected} to win, "
            f"got {actual['who']}")
        assert actual["applied"] is (expected == "live")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_the_browser_overlay_refuses_a_filename_it_did_not_expect():
    """`?league=` reaches this unsanitised and names both a fetch URL and a
    document.write()n script."""
    script = """
    const _LIVE_DATA_BASE = 'https://live.test/';
    const written = [];
    const document = { write(s) { written.push(s); } };
    const window = {};
    let fetched = 0;
    function XMLHttpRequest() {
      this.open = function () { fetched += 1; };
      this.send = function () { this.status = 200; this.responseText = ''; };
    }
    %s
    const hostile = ['../../../secrets.js', '</scr' + 'ipt><img src=x>.js',
                     'epl.js?x=1', 'EPL.js'];
    hostile.forEach(f => { _overlayLiveData(f); _writeOverlay(f); });
    _writeOverlay('epl.js');
    console.log(JSON.stringify({fetched: fetched, written: written}));
    """ % _overlay_js()
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    got = json.loads(result.stdout)
    assert got["fetched"] == 0, "a hostile filename must never reach the network"
    assert got["written"] == ['<scr' + 'ipt>_overlayLiveData("epl.js")</scr' + 'ipt>']
