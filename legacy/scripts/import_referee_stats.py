#!/usr/bin/env python3
"""Run the worldfootballR referee export and import it into PostgreSQL."""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from config import SETTINGS
from data_pipeline import db_utils
from features.referee_features import update_referee_stats_from_r


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=SETTINGS["data"]["current_season"])
    args = parser.parse_args()

    season = str(args.season)
    repo_root = Path(SETTINGS["_repo_root"])
    out_path = repo_root / "data" / f"referee_stats_{season}.csv"
    script = repo_root / "models" / "r_bridge" / "referee_stats_worldfootballR.R"

    result = subprocess.run(
        ["Rscript", "--vanilla", str(script), season, str(out_path)],
        capture_output=True,
        text=True,
        timeout=3600,
    )
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode

    db_utils.initialize_schema()
    update_referee_stats_from_r(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
