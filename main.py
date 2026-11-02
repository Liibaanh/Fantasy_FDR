import io
import os
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import seaborn as sns
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")

BASE = "https://fantasy.premierleague.com/api"
POS = ["GK", "DEF", "MID", "FWD"]

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {
            "plot_url": None,
            "upcoming_gws": 5,
            "form_gws": 4,
            "position": "ALL",
            "season_weight": 0.5
        }
    )

@app.post("/", response_class=HTMLResponse)
async def generate_fdr(
    request: Request,
    upcoming_gws: int = Form(5),
    form_gws: int = Form(4),
    position: str = Form("ALL"),
    season_weight: float = Form(0.5)
):
    position = position.upper()
    
    # --- 1. Fetch static data ---
    static = requests.get(f"{BASE}/bootstrap-static/").json()
    teams = {t["id"]: t["name"] for t in static["teams"]}
    short = {t["id"]: t["short_name"] for t in static["teams"]}

    players = pd.DataFrame(static["elements"])[["id", "team", "element_type"]]
    players["pos"] = players.element_type.map(dict(zip(range(1, 5), POS)))

    fixtures = pd.DataFrame(requests.get(f"{BASE}/fixtures/").json())
    fixtures = fixtures[["id", "event", "team_h", "team_a"]].set_index("id")

    finished = [e["id"] for e in static["events"] if e["finished"]]
    upcoming = [e["id"] for e in static["events"] if not e["finished"]][:upcoming_gws]

    # --- 2. Fetch match data ---
    rows = []
    for gw in finished:
        url_live = f"{BASE}/event/{gw}/live/"
        res = requests.get(url_live)
        if res.status_code != 200:
            continue
        
        live_data = res.json().get("elements", [])
        for el in live_data:
            player_id = el["id"]
            for ex in el.get("explain", []):
                fixture_id = ex.get("fixture")
                total_pts = sum(s.get("points", 0) for s in ex.get("stats", []))
                
                rows.append({
                    "id": player_id,
                    "gw": gw,
                    "fixture": fixture_id,
                    "points": total_pts
                })

    df = pd.DataFrame(rows)
    
    if not df.empty:
        df = df.merge(players, on="id").merge(fixtures[["team_h", "team_a"]], left_on="fixture", right_index=True)
    else:
        raise ValueError("No points data found for finished gameweeks.")

    df["opp"] = df.apply(lambda r: r.team_a if r.team == r.team_h else r.team_h, axis=1)

    # --- 3. Calculate weakness and form ---
    match = (df.groupby(["opp", "fixture", "gw", "pos"]).points.sum()
               .unstack("pos").reset_index())
    
    for p in POS:
        if p not in match.columns:
            match[p] = 0
            
    match["ALL"] = match[POS].sum(axis=1)
    cols = POS + ["ALL"]

    season = match.groupby("opp")[cols].median()
    form = match[match.gw > max(finished) - form_gws].groupby("opp")[cols].mean()

    weak = season_weight * season + (1 - season_weight) * form
    weak_fdr = 1 + 4 * (weak.max() - weak) / (weak.max() - weak.min())

    # --- 4. Prepare upcoming fixtures ---
    fut_rows = []
    for f in fixtures[fixtures.event.isin(upcoming)].itertuples():
        fut_rows.append((f.event, f.team_h, f.team_a, True))
        fut_rows.append((f.event, f.team_a, f.team_h, False))

    future = pd.DataFrame(fut_rows, columns=["gw", "team", "opp", "home"])
    future["label"] = future.apply(lambda r: f"{short[r.opp]} ({'H' if r.home else 'A'})", axis=1)

    scale = weak_fdr
    future["value"] = future.opp.map(scale[position])

    value = future.pivot_table(index="team", columns="gw", values="value", aggfunc="mean")
    text = future.groupby(["team", "gw"]).label.agg("\n".join).unstack("gw")

    order = future.groupby("team").value.sum().sort_values(ascending=True).index
    value = value.reindex(index=order, columns=upcoming)
    text = text.reindex(index=order, columns=upcoming).fillna("-")

    value.index = value.index.map(teams)
    text.index = text.index.map(teams)

    # --- 5. Generate Heatmap ---
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

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150)
    buf.seek(0)
    plot_url = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)

    return templates.TemplateResponse(
        request, "index.html", {
            "plot_url": plot_url,
            "upcoming_gws": upcoming_gws,
            "form_gws": form_gws,
            "position": position,
            "season_weight": season_weight
        }
    )