# FPL Custom Fixture Difficulty Rating (FDR) Dashboard

A web-based dashboard built with **FastAPI**, **Docker**, and **Pandas** that calculates a custom **Fixture Difficulty Rating (FDR)** for Fantasy Premier League (FPL). 

Instead of relying on official FPL ratings, this tool evaluates opponent vulnerability based on **actual historical points conceded** to specific player positions. It combines long-term season trends with short-term recent form, presenting the fixtures in an interactive, color-coded heatmap.

---

## Features

* **Custom FDR Engine:** Calculates opponent difficulty dynamically using official FPL API data (`bootstrap-static`, `fixtures`, and live event data).
* **Interactive Web Interface:** Built with FastAPI and Jinja2 templates, allowing you to adjust parameters on the fly without touching code.
* **Dockerized:** Fully containerized for seamless setup and execution across different operating systems.
* **Visual Heatmap:** Generates an easy-to-read, color-coded matrix displaying upcoming fixtures ranked by overall difficulty.

---

## Parameters Explained

You can adjust the following parameters directly in the web dashboard:

1. **Upcoming Gameweeks (`upcoming_gws`):**
   * **Description:** Controls how many future gameweeks are displayed on the heatmap (e.g., looking ahead at the next 5 or 10 rounds).
   
2. **Form Gameweeks (`form_gws`):**
   * **Description:** Determines the window of recent matches used to evaluate a team's current defensive/conceding momentum (e.g., the last 4 gameweeks).

3. **Position (`position`):**
   * **Description:** Filters the points conceded data by specific player positions. 
   * **Options:** `ALL` (Total points), `GK` (Goalkeepers), `DEF` (Defenders), `MID` (Midfielders), or `FWD` (Forwards). This lets you tailor the FDR to the exact type of players in your fantasy squad.

4. **Season Weight (`season_weight` — range 0.0 to 1.0):**
   * **Description:** Balances long-term season performance against recent form. 
   * **Details:** 
     * A value of **0.8** heavily weighs full-season performance (valuing overall defensive solidity).
     * A value of **0.2** prioritizes recent momentum (punishing teams going through a bad patch right now).
     * **0.5** gives an even 50/50 split between season medians and recent form averages.

---

## Output (The Heatmap)

When you click **"Generate FDR"**, the application processes the data and outputs a visual heatmap:

* **Color Coding:** Uses a reversed Red-Yellow-Green scale (`RdYlGn_r`):
  * **Green cells:** Indicate easy fixtures (opponents conceding many points).
  * **Red cells:** Indicate difficult fixtures (opponents conceding few points).
* **Cell Content:** Each cell displays the opponent's short name along with whether the match is home or away—for example, `MUN (H)` for a home match against Manchester United, or `CHE (A)` for an away match against Chelsea.
* **Team Sorting:** Teams on the vertical axis are automatically sorted based on the cumulative fixture difficulty of the selected upcoming gameweeks, putting teams with the easiest run at the top.

---

## Getting Started with Docker

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd Fantasy_FDR
