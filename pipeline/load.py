"""Load: read the raw JSON written by extract.py and upsert it into SQLite.

The raw files are the landing zone. This step reshapes them into the tables
the app reads (see sql/schema.sql). Every write is an upsert, so running the
load several times never creates duplicates (it is idempotent).
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
LIVE_FILE_PATTERN = re.compile(r"gw(\d+)\.json$")


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open the database and make sure all tables exist."""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


def read_json(path: Path):
    return json.loads(path.read_text())


def loaded_gameweeks(conn: sqlite3.Connection) -> set[int]:
    """Gameweeks that already have points in the database.

    Pass this to extract(skip=...) to fetch only new gameweeks.
    """
    rows = conn.execute("SELECT DISTINCT gw FROM player_points").fetchall()
    return {row[0] for row in rows}


def load_teams(conn: sqlite3.Connection, bootstrap: dict) -> int:
    rows = [(t["id"], t["name"], t["short_name"]) for t in bootstrap["teams"]]
    conn.executemany(
        """
        INSERT INTO teams (id, name, short_name) VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            short_name = excluded.short_name
        """,
        rows,
    )
    return len(rows)


def load_events(conn: sqlite3.Connection, bootstrap: dict) -> int:
    rows = [
        (e["id"], e.get("name"), e.get("deadline_time"), int(bool(e["finished"])))
        for e in bootstrap["events"]
    ]
    conn.executemany(
        """
        INSERT INTO events (id, name, deadline_time, finished) VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            deadline_time = excluded.deadline_time,
            finished = excluded.finished
        """,
        rows,
    )
    return len(rows)


def load_players(conn: sqlite3.Connection, bootstrap: dict) -> int:
    rows = [
        (p["id"], p["web_name"], p["team"], p["element_type"])
        for p in bootstrap["elements"]
    ]
    conn.executemany(
        """
        INSERT INTO players (id, web_name, team, element_type) VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            web_name = excluded.web_name,
            team = excluded.team,
            element_type = excluded.element_type
        """,
        rows,
    )
    return len(rows)


def load_fixtures(conn: sqlite3.Connection, fixtures: list) -> int:
    rows = [
        (
            f["id"],
            f.get("event"),  # None for fixtures without a gameweek yet
            f["team_h"],
            f["team_a"],
            f.get("kickoff_time"),
            int(bool(f.get("finished"))),
        )
        for f in fixtures
    ]
    conn.executemany(
        """
        INSERT INTO fixtures (id, event, team_h, team_a, kickoff_time, finished)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            event = excluded.event,
            team_h = excluded.team_h,
            team_a = excluded.team_a,
            kickoff_time = excluded.kickoff_time,
            finished = excluded.finished
        """,
        rows,
    )
    return len(rows)


def player_points_rows(live: dict, gameweek: int) -> list[tuple]:
    """Turn one gameweek of live data into (player, fixture, gw, points) rows.

    Each element has an "explain" list with one entry per fixture the player
    was involved in. Points per fixture are the sum of the points of its stats.
    Players with no stats in a fixture (did not play) are skipped; they add
    nothing to the points totals.
    """
    rows = []
    for element in live.get("elements", []):
        for entry in element.get("explain", []):
            stats = entry.get("stats", [])
            if not stats:
                continue
            points = sum(stat["points"] for stat in stats)
            rows.append((element["id"], entry["fixture"], gameweek, points))
    return rows


def load_player_points(conn: sqlite3.Connection, live: dict, gameweek: int) -> int:
    rows = player_points_rows(live, gameweek)
    conn.executemany(
        """
        INSERT INTO player_points (id, fixture, gw, points) VALUES (?, ?, ?, ?)
        ON CONFLICT(id, fixture) DO UPDATE SET
            gw = excluded.gw,
            points = excluded.points
        """,
        rows,
    )
    return len(rows)


def load(raw_dir: str | Path = "data/raw", db_path: str | Path = "fpl_data.db") -> None:
    """Load everything found in raw_dir into the database, in one transaction."""
    raw = Path(raw_dir)
    bootstrap = read_json(raw / "bootstrap-static.json")
    fixtures = read_json(raw / "fixtures.json")

    conn = connect(db_path)
    try:
        with conn:  # commits on success, rolls back if anything raises
            log.info("teams: %d", load_teams(conn, bootstrap))
            log.info("events: %d", load_events(conn, bootstrap))
            log.info("players: %d", load_players(conn, bootstrap))
            log.info("fixtures: %d", load_fixtures(conn, fixtures))

            for path in sorted((raw / "live").glob("gw*.json")):
                match = LIVE_FILE_PATTERN.search(path.name)
                if not match:
                    continue
                gameweek = int(match.group(1))
                count = load_player_points(conn, read_json(path), gameweek)
                log.info("player_points gw%d: %d rows", gameweek, count)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load raw FPL JSON into SQLite")
    parser.add_argument("--raw", default="data/raw", help="folder with raw JSON files")
    parser.add_argument("--db", default="fpl_data.db", help="SQLite database file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load(args.raw, args.db)


if __name__ == "__main__":
    main()