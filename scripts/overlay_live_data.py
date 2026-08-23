#!/usr/bin/env python3
"""Overlay the prior live-data snapshot onto webapp/data — newest stamp wins.

The fast refresh builds on top of the previous snapshot rather than on the
daily commit, so that results applied at 14:15 are still there at 14:30. It got
that snapshot by piping the whole branch over the checkout::

    git archive origin/live-data webapp/data | tar -x || true

which assumes `live-data` is always fresher than `main`. That is true only
while the job that publishes `live-data` is actually running, and on
2026-08-23 it had not run since 2026-08-04. The blanket overlay then rolled 19
days of committed payloads backwards, `webapp/leagues.js` stayed on `main`, and
`validate_payloads.py` failed the run on the resulting disagreement — before
the step that would have refreshed the branch, so it could not self-heal.

Every payload already carries a top-level `generated` stamp. This module reads
both and takes the live-data copy **only when it is provably newer**:

  * both sides must parse, and both must carry a readable `generated`;
  * the incoming stamp must be strictly greater than the committed one.

Anything else keeps what is committed. An unreadable stamp therefore loses
rather than wins, so the overlay can only ever move a payload forward in time —
a stale or corrupt branch degrades to "no overlay", which is a slower dashboard
rather than a failed run and a rolled-back site.

Two deliberate scope limits:

  * Only top-level ``webapp/data/*.js`` is considered. The fast path writes
    nothing else, and the branch's `news/`, `drift-traj/`, `intel-events/` and
    `momentum/` subtrees are just a copy of `main` at the time of the push, so
    keeping the checkout's copy is always the fresher choice.
  * Only files that exist in the checkout are considered. `main` is the
    authority on which leagues exist; a payload present only on the branch is a
    league `main` has since removed, and must not be resurrected.

Usage::

    python3 scripts/overlay_live_data.py --from <extracted>/webapp/data
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.payload_utils import read_js_payload

PAYLOAD_DIR = Path("webapp/data")

# "2026-08-23 11:20 UTC" is what every builder writes. Seconds and a "Z" suffix
# are accepted so a future format tweak degrades to "still readable" rather
# than to "nothing is ever newer". Anything else is unreadable on purpose:
# lexicographic comparison of the raw string would rank the garbage value
# "unknown" above every real date and hand the overlay a permanent win.
_STAMP_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?\s*(?:UTC|Z)?$")


def stamp(payload: object) -> dt.datetime | None:
    """Return a payload's `generated` time, or None when it is unreadable."""
    if not isinstance(payload, dict):
        return None
    match = _STAMP_RE.match(str(payload.get("generated", "")).strip())
    if not match:
        return None
    year, month, day, hour, minute, second = (
        int(g) if g else 0 for g in match.groups())
    try:
        return dt.datetime(year, month, day, hour, minute, second,
                           tzinfo=dt.timezone.utc)
    except ValueError:      # 2026-02-30 and friends
        return None


class Decision(NamedTuple):
    """One file's verdict, kept inspectable so the CI log explains itself."""
    name: str
    take: bool
    reason: str
    incoming: dt.datetime | None
    current: dt.datetime | None

    def describe(self) -> str:
        def fmt(value: dt.datetime | None) -> str:
            return value.strftime("%Y-%m-%d %H:%M UTC") if value else "unreadable"
        verb = "take" if self.take else "keep"
        return (f"  {verb:4}  {self.name:<28} "
                f"live={fmt(self.incoming)}  main={fmt(self.current)}  "
                f"({self.reason})")


def decide(name: str, incoming: object, current: object) -> Decision:
    """Fail closed: the live-data copy wins only when provably newer."""
    live, main = stamp(incoming), stamp(current)
    if live is None:
        return Decision(name, False, "live-data stamp unreadable", live, main)
    if main is None:
        return Decision(name, False, "committed stamp unreadable", live, main)
    if live > main:
        return Decision(name, True, "live-data is newer", live, main)
    reason = "same stamp" if live == main else "live-data is older"
    return Decision(name, False, reason, live, main)


def plan(live_dir: Path, dest_dir: Path = PAYLOAD_DIR) -> list[Decision]:
    """Decide every payload, iterating the checkout rather than the branch."""
    decisions = []
    for current_path in sorted(Path(dest_dir).glob("*.js")):
        incoming_path = Path(live_dir) / current_path.name
        if not incoming_path.exists():
            continue        # not on the branch — nothing to overlay
        decisions.append(decide(current_path.name,
                                read_js_payload(incoming_path),
                                read_js_payload(current_path)))
    return decisions


def apply(decisions: list[Decision], live_dir: Path,
          dest_dir: Path = PAYLOAD_DIR) -> int:
    taken = 0
    for decision in decisions:
        if decision.take:
            shutil.copyfile(Path(live_dir) / decision.name,
                            Path(dest_dir) / decision.name)
            taken += 1
    return taken


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="live_dir", required=True,
                        help="extracted webapp/data from origin/live-data")
    parser.add_argument("--into", dest="dest_dir", default=str(PAYLOAD_DIR))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    live_dir, dest_dir = Path(args.live_dir), Path(args.dest_dir)
    if not live_dir.is_dir():
        # No branch yet, or the fetch failed. The old step swallowed this with
        # `|| true`; keep that, because a first run must not be a failed run.
        print(f"No live-data snapshot at {live_dir} — keeping the checkout.")
        return 0

    decisions = plan(live_dir, dest_dir)
    for decision in decisions:
        print(decision.describe())
    taken = (sum(d.take for d in decisions) if args.dry_run
             else apply(decisions, live_dir, dest_dir))
    print(f"live-data overlay: {taken} newer of {len(decisions)} compared"
          f"{' (dry run — nothing written)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
