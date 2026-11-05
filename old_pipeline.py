import sqlite3
import pandas as pd
import requests

BASE = "https://fantasy.premierleague.com/api"
DB_NAME = "fpl_data.db"


def run_pipeline():
  print("Fetching data from FPL API...")

  # Fetch static data
  static_data = requests.get(f"{BASE}/bootstrap-static/").json()
  fixtures_raw = requests.get(f"{BASE}/fixtures/").json()

  # 1. Save Teams to Database
  df_teams = pd.DataFrame(static_data["teams"])
  team_id_to_name = dict(zip(df_teams["id"], df_teams["name"]))

  # 2. Save Players to Database (including web_name)
  df_players_raw = pd.DataFrame(static_data["elements"])
  df_players = df_players_raw[["id", "web_name", "team", "element_type"]]

  # Player info for merging later in the loop
  df_players_info = df_players[["id", "web_name", "team"]]

  conn = sqlite3.connect(DB_NAME)
  
  # Lagre teams og players fast i databasen med én gang
  df_teams.to_sql("teams", conn, if_exists="replace", index=False)
  df_players.to_sql("players", conn, if_exists="replace", index=False)
  print("Teams and players saved to database.")

  # Get list of finished gameweeks
  finished_gws = [e["id"] for e in static_data["events"] if e["finished"]]

  scored_rows = []
  conceded_rows = []

  # Loop through each finished gameweek
  for gw in finished_gws:
    try:
      # Fetch fixtures for the specific gameweek
      fixtures_url = f"{BASE}/fixtures/?event={gw}"
      fixtures = requests.get(fixtures_url).json()

      team_opponent = {}
      for f in fixtures:
        h = f["team_h"]
        a = f["team_a"]
        team_opponent[h] = a
        team_opponent[a] = h

      # Fetch live data for the gameweek
      url_live = f"{BASE}/event/{gw}/live/"
      live_res = requests.get(url_live)
      if live_res.status_code != 200:
        continue

      live_data = live_res.json()

      stats_list = []
      for el in live_data.get("elements", []):
        player_id = el["id"]
        stat_dict = el["stats"].copy()
        stat_dict["id"] = player_id
        stats_list.append(stat_dict)

      df_gw_stats = pd.DataFrame(stats_list)
      if df_gw_stats.empty:
        continue

      # Merge stats with player info
      df_final = pd.merge(df_gw_stats, df_players_info, on="id")

      # Group points by team
      df_team_points = (
          df_final.groupby("team")["total_points"].sum().reset_index()
      )
      df_team_points["Team"] = df_team_points["team"].map(team_id_to_name)

      # 1. Collect Scored Points data
      for _, row in df_team_points.iterrows():
        scored_rows.append(
            {
                "Team": row["Team"],
                "gw": gw,
                "points_scored": row["total_points"],
            }
        )

      # 2. Collect Conceded Points data
      df_team_points["opponent_id"] = df_team_points["team"].map(team_opponent)
      team_points_dict = dict(
          zip(df_team_points["team"], df_team_points["total_points"])
      )

      for _, row in df_team_points.iterrows():
        opp_id = row["opponent_id"]
        opp_points = team_points_dict.get(opp_id, 0) if pd.notnull(opp_id) else 0
        conceded_rows.append(
            {
                "Team": row["Team"],
                "gw": gw,
                "points_conceded": opp_points,
            }
        )

    except Exception as e:
      print(f"Could not process data for Gameweek {gw}: {e}")

  # Convert lists to DataFrames
  df_scored = pd.DataFrame(scored_rows)
  df_conceded = pd.DataFrame(conceded_rows)

  # Save aggregated stats to SQLite Database
  print(f"Saving aggregated stats to {DB_NAME}...")
  df_scored.to_sql("team_gw_scored", conn, if_exists="replace", index=False)
  df_conceded.to_sql("team_gw_conceded", conn, if_exists="replace", index=False)

  conn.close()
  print("Pipeline finished and metrics successfully saved to database!")


if __name__ == "__main__":
  run_pipeline()