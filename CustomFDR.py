import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import requests
import seaborn as sns
import time

def generate_custom_fdr(upcoming_gws=5, form_gws=4, position="ALL", season_weight=0.5, filename=None):
    """
    Generates a custom FPL Fixture Difficulty Rating (FDR) heatmap based on actual historical points conceded.
    
    Parameters:
    - upcoming_gws (int): Number of future gameweeks to analyze (e.g., 3 or 5).
    - form_gws (int): Number of recent gameweeks to consider as current form (e.g., 3, 4, or 5).
    - position (str): Position filter ("GK", "DEF", "MID", "FWD", or "ALL"). Case-insensitive.
    - season_weight (float): Weight given to overall season median vs recent form (default 0.5).
    - filename (str, optional): File path to save the generated plot image.
    """
    
    BASE = "https://fantasy.premierleague.com/api"
    POS = ["GK", "DEF", "MID", "FWD"]
    
    # Normalize position string to match format
    position = position.upper()
    if position not in POS and position != "ALL":
        raise ValueError(f"Invalid position '{position}'. Must be one of: 'GK', 'DEF', 'MID', 'FWD', or 'ALL'.")

    print(f"Fetching FPL data (Upcoming GWs: {upcoming_gws}, Form GWs: {form_gws}, Position: {position})...")

    # 1. Fetch static data (teams, players, fixtures)
    static = requests.get(f"{BASE}/bootstrap-static/").json()

    teams = {t["id"]: t["name"] for t in static["teams"]}
    short = {t["id"]: t["short_name"] for t in static["teams"]}

    players = pd.DataFrame(static["elements"])[["id", "team", "element_type"]]
    players["pos"] = players.element_type.map(dict(zip(range(1, 5), POS)))

    fixtures = pd.DataFrame(requests.get(f"{BASE}/fixtures/").json())
    fixtures = fixtures[["id", "event", "team_h", "team_a"]].set_index("id")

    # Determine finished and upcoming gameweeks
    finished = [e["id"] for e in static["events"] if e["finished"]]
    upcoming = [e["id"] for e in static["events"] if not e["finished"]][:upcoming_gws]

    # 2. Fetch match data for finished gameweeks (one row per player per match)
    rows = []
    for gw in finished:
        live = requests.get(f"{BASE}/event/{gw}/live/").json()["elements"]
        for el in live:
            for ex in el["explain"]:
                rows.append((el["id"], gw, ex["fixture"], sum(s["points"] for s in ex["stats"])))
        time.sleep(0.2)  # Gentle delay for API

    df = (pd.DataFrame(rows, columns=["id", "gw", "fixture", "points"])
            .merge(players, on="id")
            .merge(fixtures[["team_h", "team_a"]], left_on="fixture", right_index=True))

    # Identify the conceding opponent team
    df["opp"] = df.apply(lambda r: r.team_a if r.team == r.team_h else r.team_h, axis=1)

    # 3. Calculate weakness (season) and form (recent gameweeks)
    match = (df.groupby(["opp", "fixture", "gw", "pos"]).points.sum()
               .unstack("pos").reset_index())
    
    # Ensure all position columns exist even if empty
    for p in POS:
        if p not in match.columns:
            match[p] = 0
            
    match["ALL"] = match[POS].sum(axis=1)
    cols = POS + ["ALL"]

    season = match.groupby("opp")[cols].median()
    form = match[match.gw > max(finished) - form_gws].groupby("opp")[cols].mean()

    # Combine season and form weights
    weak = season_weight * season + (1 - season_weight) * form

    # Compute continuous 1-5 FDR scale (1 = easiest, 5 = hardest)
    weak_fdr = 1 + 4 * (weak.max() - weak) / (weak.max() - weak.min())

    # 4. Prepare upcoming fixtures
    fut_rows = []
    for f in fixtures[fixtures.event.isin(upcoming)].itertuples():
        fut_rows.append((f.event, f.team_h, f.team_a, True))    # Home view
        fut_rows.append((f.event, f.team_a, f.team_h, False))   # Away view

    future = pd.DataFrame(fut_rows, columns=["gw", "team", "opp", "home"])
    future["label"] = future.apply(lambda r: f"{short[r.opp]} ({'H' if r.home else 'A'})", axis=1)

    # 5. Generate Heatmap
    scale = weak_fdr
    future["value"] = future.opp.map(scale[position])

    value = future.pivot_table(index="team", columns="gw", values="value", aggfunc="mean")
    text = future.groupby(["team", "gw"]).label.agg("\n".join).unstack("gw")

    ascending = True  # Lower FDR sum = easier run
    order = future.groupby("team").value.sum().sort_values(ascending=ascending).index
    value = value.reindex(index=order, columns=upcoming)
    text = text.reindex(index=order, columns=upcoming).fillna("-")

    value.index = value.index.map(teams)
    text.index = text.index.map(teams)

    fig, ax = plt.subplots(figsize=(1.6 * len(upcoming) + 3, 0.5 * len(value) + 2))
    sns.heatmap(value, annot=text.values, fmt="", cmap="RdYlGn_r",
                linewidths=1, linecolor="white",
                cbar_kws={"label": "FDR (1 = easy, 5 = hard)"},
                xticklabels=[f"GW{c}" for c in upcoming], yticklabels=True, ax=ax)
    
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.xaxis.tick_top()
    ax.set_title(f"Custom FDR ({position}) — Next {upcoming_gws} GWs", pad=30, fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    if filename:
        plt.savefig(filename, dpi=150)
        print(f"Plot saved successfully as '{filename}'")
        
    plt.show()
    return fig

generate_custom_fdr(upcoming_gws=5, form_gws=3, position="DEF")