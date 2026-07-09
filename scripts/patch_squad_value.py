#!/usr/bin/env python3
"""One-off: refresh only the `squad_value` key of already-built webapp/data/*.js
payloads from freshly-regenerated transfermarkt CSVs (Task 7-9), without re-running
the full model pipeline (ELO/DC/XGB/sims — ~18 min per league per project memory).

Usage: venv/bin/python scripts/patch_squad_value.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_league_data import build_squad_value_league
from scripts.build_dashboard_data import build_squad_value_mls
from scripts.payload_utils import write_js_payload
from scripts.import_transfermarkt import TM_CODE_TO_LEAGUE_ID

WEBAPP_DATA = Path(__file__).parent.parent / "webapp" / "data"


def _load(lid: str) -> dict:
    path = WEBAPP_DATA / f"{lid}.js"
    text = re.sub(r"^[\s\S]*?=\s*", "", path.read_text(encoding="utf-8")).rstrip().rstrip(";")
    return json.loads(text)


def patch_non_mls(lid: str) -> bool:
    data = _load(lid)
    team_names = {s["team"] for s in data.get("standings", [])}
    if not team_names:
        print(f"[{lid}] no standings/team names found, skipping")
        return False
    sv = build_squad_value_league(lid, team_names)
    if sv is None:
        print(f"[{lid}] no squad-value data available, leaving unchanged")
        return False
    data["squad_value"] = sv
    write_js_payload(WEBAPP_DATA / f"{lid}.js", "LEAGUE_DATA", data)
    print(f"[{lid}] patched squad_value for {len(sv)} teams")
    return True


def patch_mls() -> bool:
    from data_pipeline.asa_cache import get_teams
    data = _load("mls")
    team_names = {s["team"] for s in data.get("standings", [])}
    teams = get_teams("mls")
    id2name = {r.team_id: r.team_name for r in teams.itertuples()}
    abbr2id = {r.team_abbreviation: r.team_id for r in teams.itertuples()}
    tids = [tid for tid, name in id2name.items() if name in team_names]
    sv = build_squad_value_mls(tids, id2name, abbr2id, 2026)
    if sv is None:
        print("[mls] no squad-value data available, leaving unchanged")
        return False
    data["squad_value"] = sv
    write_js_payload(WEBAPP_DATA / "mls.js", "LEAGUE_DATA", data)
    print(f"[mls] patched squad_value for {len(sv)} teams")
    return True


def main():
    patch_mls()
    for lid in sorted(set(TM_CODE_TO_LEAGUE_ID.values()) - {"canadian-pl"}):
        if (WEBAPP_DATA / f"{lid}.js").exists():
            patch_non_mls(lid)


if __name__ == "__main__":
    main()
