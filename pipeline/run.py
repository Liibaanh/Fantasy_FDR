"""Run the whole pipeline: extract new gameweeks, then load everything.

Usage: python -m pipeline.run
"""
from __future__ import annotations

import argparse
import logging

from pipeline import extract as extract_step
from pipeline import load as load_step

log = logging.getLogger(__name__)


def run(raw_dir: str = "data/raw", db_path: str = "fpl_data.db") -> None:
    # Ask the database which gameweeks it already has, so we only fetch new ones.
    conn = load_step.connect(db_path)
    try:
        already_loaded = load_step.loaded_gameweeks(conn)
    finally:
        conn.close()
    log.info("Already loaded gameweeks: %s", sorted(already_loaded))

    payload = extract_step.extract(skip=already_loaded)
    extract_step.save_raw(payload, raw_dir)
    load_step.load(raw_dir, db_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the FPL pipeline")
    parser.add_argument("--raw", default="data/raw")
    parser.add_argument("--db", default="fpl_data.db")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.raw, args.db)


if __name__ == "__main__":
    main()