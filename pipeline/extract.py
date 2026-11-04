"""Extract: fetch raw data from the official FPL API.

This step does one thing only: fetch the data and return it unchanged.
No cleaning or calculations happen here. That is left to the transform
step (SQL) later in the pipeline.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://fantasy.premierleague.com/api"
REQUEST_PAUSE_SECONDS = 0.3  # pause between API  requests

log = logging.getLogger(__name__)


def make_session() -> requests.Session:
    """Create a session that retries automatically on transient errors."""
    retry = Retry(
        total=5,
        backoff_factor=1.0,  # waits 1s, 2s, 4s, ... between retries
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "fantasy-fdr-pipeline/0.1"})
    return session


def get_json(session: requests.Session, path: str, timeout: int = 30) -> dict | list:
    """GET a path on the FPL API and return the parsed JSON.

    Raises requests.HTTPError on a non-2xx response once retries are exhausted.
    """
    url = f"{BASE_URL}/{path.lstrip('/')}"
    log.info("GET %s", url)
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_bootstrap(session: requests.Session) -> dict:
    """Fetch players, teams, positions and gameweeks."""
    return get_json(session, "bootstrap-static/")


def fetch_fixtures(session: requests.Session) -> list:
    """Fetch every fixture in the season."""
    return get_json(session, "fixtures/")


def fetch_live(session: requests.Session, gameweek: int) -> dict:
    """Fetch points per player for a single gameweek."""
    return get_json(session, f"event/{gameweek}/live/")


def finished_gameweeks(bootstrap: dict) -> list[int]:
    """Return the ids of gameweeks that have finished."""
    return [event["id"] for event in bootstrap["events"] if event.get("finished")]


def extract(
    session: requests.Session | None = None,
    gameweeks: list[int] | None = None,
    skip: set[int] | frozenset[int] = frozenset(),
) -> dict:
    """Fetch raw data.

    gameweeks: only fetch these. Defaults to all finished gameweeks.
    skip: gameweeks that are already loaded (enables incremental extraction).
    """
    session = session or make_session()

    bootstrap = fetch_bootstrap(session)
    fixtures = fetch_fixtures(session)

    to_fetch = gameweeks if gameweeks is not None else finished_gameweeks(bootstrap)
    to_fetch = [gw for gw in to_fetch if gw not in skip]
    log.info("Fetching live data for %d gameweeks: %s", len(to_fetch), to_fetch)

    live: dict[int, dict] = {}
    for gw in to_fetch:
        live[gw] = fetch_live(session, gw)
        time.sleep(REQUEST_PAUSE_SECONDS)

    return {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "bootstrap": bootstrap,
        "fixtures": fixtures,
        "live": live,
    }


def save_raw(payload: dict, out_dir: str | Path) -> None:
    """Write the raw data to disk as JSON (useful for local development and debugging)."""
    out = Path(out_dir)
    (out / "live").mkdir(parents=True, exist_ok=True)  # also creates out_dir itself
    (out / "bootstrap-static.json").write_text(json.dumps(payload["bootstrap"]))
    (out / "fixtures.json").write_text(json.dumps(payload["fixtures"]))
    for gw, data in payload["live"].items():
        (out / "live" / f"gw{gw}.json").write_text(json.dumps(data))
    log.info("Saved raw data to %s", out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch raw data from the FPL API")
    parser.add_argument("--out", default="data/raw", help="folder for the raw JSON files")
    parser.add_argument("--gw", type=int, nargs="*", help="only fetch these gameweeks")
    parser.add_argument("--skip", type=int, nargs="*", default=[], help="skip these gameweeks")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    payload = extract(gameweeks=args.gw, skip=set(args.skip))
    save_raw(payload, args.out)


if __name__ == "__main__":
    main()