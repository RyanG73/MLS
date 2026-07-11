#!/usr/bin/env python3
"""Build the public-launch execution report from current local artifacts."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parent.parent.resolve()
OUT = REPO_ROOT / "docs" / "public-launch-execution-report-2026-07-11.md"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.exists() else {}


def _load_js(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text()
    match = re.match(r"window\.\w+\s*=\s*(.*?);?\s*$", text, re.S)
    return json.loads(match.group(1)) if match else {}


def _family(data: dict[str, Any], fid: str) -> dict[str, Any]:
    return next((f for f in data.get("families", []) if f.get("id") == fid), {})


def _pct(v: Any) -> str:
    return "pending" if v is None else f"{float(v) * 100:.1f}%"


def _brier(v: Any) -> str:
    return "pending" if v is None else f"{float(v):.4f}"


def main() -> int:
    model = _load_js(REPO_ROOT / "webapp" / "data" / "model-slices.js")
    edge = _load_js(REPO_ROOT / "webapp" / "data" / "edge-board.js")
    champion = _load_json(REPO_ROOT / "experiments" / "challenger-bag5.report.json")
    bridge = _load_json(REPO_ROOT / "experiments" / "r2-hybrid-bridge-decay.report.json")
    mls = _family(model, "mls")
    tiers = _family(model, "eur_tiers")

    mls_under = (mls.get("underdog_calibration") or {}).get("significant") or {}
    market = ((tiers.get("forward_summary") or {}).get("market_disagreement") or {})
    draw_total = (tiers.get("forward_summary") or {}).get("total_goals_draw") or []
    windows = bridge.get("pooled_early_windows") or tiers.get("promoted_relegated_windows") or []
    risk_counts = edge.get("risk_counts") or {}
    edge_window = edge.get("upcoming_7d") or {}

    lines = [
        "# Public Launch Execution Report",
        "",
        "Date: 2026-07-11",
        "",
        "## Summary",
        "",
        f"- Refreshed MLS champion report Brier: {_brier(champion.get('avg_brier'))}. Previous checkpoint was 0.632977, so this is flat/slightly worse by +0.000106 and not a model improvement.",
        f"- MLS significant underdogs: {_pct(mls_under.get('mean_prob'))} predicted vs {_pct(mls_under.get('hit_rate'))} observed, n={mls_under.get('n', 0)}.",
        f"- Edge-board 7-day slate: {edge_window.get('match_count', 0)} matches across {edge_window.get('league_count', 0)} leagues.",
        f"- Current risk flags: {', '.join(f'{k}={v}' for k, v in sorted(risk_counts.items())) or 'none in current edge window'}.",
        f"- Tier-family row-level market buckets: {len(market.get('by_edge') or [])} buckets; market status {market.get('status', 'pending')}.",
        "",
        "## 18-Step Execution Status",
        "",
        "1. European Market-Disagreement Buckets — Completed for available row-level market payload rows. Family-level buckets now flow through `model-slices.js`; broader historical depth still depends on row-level odds history beyond aggregate `perf_by_year`.",
        "2. Promoted/Relegated Early-Window Slice — Completed in `scripts/eval/unified_tier_elo.py` with pooled windows `0-5`, `6-15`, and `16+`.",
    ]
    for row in windows:
        lines.append(
            f"   - {row.get('window')}: seeded {_brier(row.get('brier_seeded') or row.get('seeded'))}, "
            f"league {_brier(row.get('brier_per_league') or row.get('league'))}, "
            f"decay8 {_brier(row.get('brier_bridge_decay_8') or row.get('decay8'))}."
        )
    lines += [
        "3. Historical Draw Calibration by Goal Total — Completed for played rows carrying `lam`/`mu`; surfaced by family in `model-slices.js`.",
    ]
    for row in draw_total:
        lines.append(
            f"   - {row.get('bucket')}: draw {_pct(row.get('mean_draw_prob'))} predicted vs "
            f"{_pct(row.get('draw_hit_rate'))} observed, played_n={row.get('played_n', 0)}."
        )
    lines += [
        "4. Trust UI: Market Disagreement Card — Completed as a conditional evidence tape. It appears only when row-level market buckets exist.",
        "5. Trust UI: Promoted/Relegated Caution Card — Completed for the Europe tiers family using early-window replay results.",
        "6. Draw-Side Policy Gate — Completed as policy: draw recommendations remain suppressed; draw rows are diagnostics only until a future gate explicitly promotes them.",
        "7. Current Slate Risk Scoring — Completed in `scripts/build_edge_board.py` with no-line, draw-heavy, low-total draw setup, model-underdog, and qualifying-edge flags.",
        "8. Command Center Risk Tape — Completed in the landing Command Center and match rows.",
        "9. Paper Ledger + CLV Upgrade — Build chain now runs `scripts/bet_ledger.py`; real CLV still depends on opener/closer odds files accumulating.",
        "10. Odds Coverage Expansion — Repo-side decision artifact remains: current implementation is ready for broader odds, but provider selection/payment is external and unresolved.",
        "11. European Launch QA Pass — Payload validation and static syntax checks are wired; visual QA should still be repeated before deploy on the target host.",
        "12. SEO / Share Pages — Completed basic title, description, Open Graph, and Twitter metadata in `webapp/index.html`.",
        "13. Email Capture / Weekly Digest — Static UI scaffold completed. Real capture requires selecting an email backend or form endpoint.",
        "14. Weekly Content Workflow — This report is the first generated content artifact; recurring weekly generation can reuse the same source payloads.",
        "15. Post-Launch Calibration Review — Not due until 2026-27 matches accrue; report surfaces the fields needed for review.",
        "16. Model Feature Hunt Resumption — Deferred by design; diagnostics showed no Brier improvement yet and no production model change.",
        "17. Promotion Gate Extensions — Completed as advisory `trust_diagnostics` output in `scripts/promotion_gate.py`.",
        "18. Production Build Discipline — `build_all.sh` now includes model slices, paper ledger, edge board, and this public-launch report after payload validation.",
        "",
        "## Findings",
        "",
        "- Brier did not improve. The work improved auditability and launch readiness, not model accuracy.",
        "- MLS underdog calibration is strong enough to show publicly: significant underdogs are close to calibrated.",
        "- Promoted/relegated bridge-decay remains a no-change result. The early-window replay did not reveal a hidden first-five-match win.",
        "- Market-disagreement evidence is now structurally available, but current row-level market depth is thin and concentrated in leagues with played market rows.",
        "- Draw-side betting should remain suppressed. Draw-by-total diagnostics are visible, but there is no promotion gate result that justifies draw recommendations.",
        "",
        "## Remaining External Dependencies",
        "",
        "- Paid/live odds coverage for broader row-level model-vs-market and CLV history.",
        "- Email collection backend or static form provider.",
        "- Final hosted-domain URL for canonical/share metadata.",
        "- Manual visual QA on production deployment after build.",
        "",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines))
    print(f"[launch-report] wrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
