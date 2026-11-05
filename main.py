import base64
import io
import sqlite3
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")

DB_NAME = "fpl_data.db"
POS = ["GK", "DEF", "MID", "FWD"]


def get_db_connection():
  conn = sqlite3.connect(DB_NAME)
  conn.row_factory = sqlite3.Row
  return conn


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
  return templates.TemplateResponse(
      request,
      "index.html",
      {
          "plot_url": None,
          "upcoming_gws": 5,
          "form_gws": 4,
          "position": "ALL",
          "season_weight": 0.5,
      },
  )


@app.post("/", response_class=HTMLResponse)
async def generate_fdr(
    request: Request,
    upcoming_gws: int = Form(5),
    form_gws: int = Form(4),
    position: str = Form("ALL"),
    season_weight: float = Form(0.5),
):
  position = position.upper()

  # --- 1. Fetch data from database instead of API ---
  conn = get_db_connection()

  teams_df = pd.read_sql("SELECT * FROM teams", conn)
  events_df = pd.read_sql("SELECT * FROM events", conn)
  fixtures = pd.read_sql("SELECT * FROM fixtures", conn).set_index("id")
  players = pd.read_sql("SELECT * FROM players", conn)
  points_df = pd.read_sql("SELECT * FROM player_points", conn)

  conn.close()

  # Mapping dictionaries for teams and positions
  teams = dict(zip(teams_df["id"], teams_df["name"]))
  short = dict(zip(teams_df["id"], teams_df["short_name"]))

  players["pos"] = players["element_type"].map(dict(zip(range(1, 5), POS)))

  finished = events_df[events_df["finished"]]["id"].tolist()
  upcoming = events_df[~events_df["finished"]]["id"].head(upcoming_gws).tolist()

  if points_df.empty:
    raise ValueError(
        "No points data found in database. Please run the pipeline first!"
    )

  # --- 2. Merge tables for analysis ---
  df = (
      points_df.merge(players[["id", "team", "pos"]], on="id")
      .merge(fixtures[["team_h", "team_a"]], left_on="fixture", right_index=True)
  )

  df["opp"] = df.apply(
      lambda r: r.team_a if r.team == r.team_h else r.team_h, axis=1
  )

  # --- 3. Calculate weakness and FDR ---
  match = (
      df.groupby(["opp", "fixture", "gw", "pos"])
      .points.sum()
      .unstack("pos")
      .reset_index()
  )

  for p in POS:
    if p not in match.columns:
      match[p] = 0

  match["ALL"] = match[POS].sum(axis=1)
  cols = POS + ["ALL"]

  max_finished_gw = max(finished) if finished else 1
  season = match.groupby("opp")[cols].median()
  form = (
      match[match.gw > max_finished_gw - form_gws].groupby("opp")[cols].mean()
  )

  weak = season_weight * season + (1 - season_weight) * form
  weak_fdr = 1 + 4 * (weak.max() - weak) / (weak.max() - weak.min())

  # --- 4. Prepare upcoming fixtures ---
  fut_rows = []
  for f in fixtures[fixtures["event"].isin(upcoming)].itertuples():
    fut_rows.append((f.event, f.team_h, f.team_a, True))
    fut_rows.append((f.event, f.team_a, f.team_h, False))

  future = pd.DataFrame(fut_rows, columns=["gw", "team", "opp", "home"])
  future["label"] = future.apply(
      lambda r: f"{short.get(r.opp, 'Unknown')} ({'H' if r.home else 'A'})",
      axis=1,
  )

  future["value"] = future["opp"].map(weak_fdr[position])

  value = future.pivot_table(
      index="team", columns="gw", values="value", aggfunc="mean"
  )
  text = future.groupby(["team", "gw"])["label"].agg("\n".join).unstack("gw")

  order = (
      future.groupby("team")["value"].sum().sort_values(ascending=True).index
  )
  value = value.reindex(index=order, columns=upcoming)
  text = text.reindex(index=order, columns=upcoming).fillna("-")

  value.index = value.index.map(teams)
  text.index = text.index.map(teams)

  # --- 5. Generate Heatmap ---
  fig, ax = plt.subplots(
      figsize=(1.6 * len(upcoming) + 3, 0.5 * len(value) + 2)
  )
  sns.heatmap(
      value,
      annot=text.values,
      fmt="",
      cmap="RdYlGn_r",
      linewidths=1,
      linecolor="white",
      cbar_kws={"label": "FDR (1 = easy, 5 = hard)"},
      xticklabels=[f"GW{c}" for c in upcoming],
      yticklabels=True,
      ax=ax,
  )

  ax.set_xlabel("")
  ax.set_ylabel("")
  ax.xaxis.tick_top()
  ax.set_title(
      f"Custom FDR ({position}) — Next {upcoming_gws} GWs",
      pad=30,
      fontsize=14,
      fontweight="bold",
  )
  plt.tight_layout()

  buf = io.BytesIO()
  plt.savefig(buf, format="png", dpi=150)
  buf.seek(0)
  plot_url = base64.b64encode(buf.read()).decode("utf-8")
  plt.close(fig)

  return templates.TemplateResponse(
      request,
      "index.html",
      {
          "plot_url": plot_url,
          "upcoming_gws": upcoming_gws,
          "form_gws": form_gws,
          "position": position,
          "season_weight": season_weight,
      },
  )