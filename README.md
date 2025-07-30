# FPL Squad Optimizer

This project provides a Python-based solution to optimize your Fantasy Premier League (FPL) squad selection using Integer Linear Programming (ILP). It fetches real-time player, team, and fixture data from the official FPL API, calculates Expected Points (xP) for all players, and then uses an optimization algorithm to build the highest-scoring 15-player squad within a specified budget and team limits.

## ✨ Features

* **Real-time FPL Data Integration:** Fetches up-to-date player, team, and fixture information directly from the official FPL API.

* **Expected Points (xP) Prediction:** Calculates a player's expected points based on historical performance, team strengths, opponent difficulty (Fixture Difficulty Rating - FDR), and expected minutes played.

* **Granular Expected Minutes:** Refined logic to predict player minutes, especially for those with low historical play, ensuring more realistic xP values.

* **Multi-Gameweek Optimization:** Optimize your squad over multiple upcoming gameweeks to plan for future fixtures.

* **Budget Constraints:** Ensures the selected squad adheres to your FPL budget.

* **Team Limits:** Respects the FPL rule of a maximum number of players from any single Premier League team.

* **Position Requirements:** Automatically selects the correct number of Goalkeepers, Defenders, Midfielders, and Forwards.

* **Configurable Parameters:** Easily adjust FPL scoring rules, xP thresholds, budget, and team limits via a dedicated configuration file.

## 🚀 How It Works

The project is structured into three main components:

1.  **`fpl_config.py`**:
    This file centralizes all configurable parameters for the predictor and the optimizer. You can adjust FPL point values, minute thresholds for xP calculation, the optimization horizon (number of gameweeks), total budget, and the maximum players allowed per team here.

2.  **`fpl_xp_predictor.py`**:
    This module is responsible for:

    * Fetching raw FPL data from the API.

    * Processing team and fixture data, including calculating team strengths and incorporating FDR.

    * Calculating each player's Expected Points (xP) for upcoming gameweeks. This involves logic for goals, assists, clean sheets, saves (for GKs), bonus points (using BPS as a proxy), and even minor negative events like cards.

    * Crucially, it includes refined logic for `expected_minutes` to accurately assess playing time, especially for players with limited past appearances.

3.  **`fpl_solver.py`**:
    This is the core optimization engine. It takes the xP-calculated player data from `fpl_xp_predictor.py` and:

    * Sets up an Integer Linear Programming (ILP) problem using the `PuLP` library.

    * Defines constraints for squad size (15 players), position counts (2 GKs, 5 DEFs, 5 MIDs, 3 FWDs), total budget, and maximum players per team.

    * Maximizes the total expected points of the selected squad.

    * Prints a detailed summary of the optimal squad, including costs and xP breakdown by position, and a team-by-team player count.

## 🛠️ Setup and Installation

To get the FPL Squad Optimizer running on your local machine, follow these steps:

1.  **Clone the Repository (if applicable):**

    ```bash
    git clone git@github.com:thomaszwagerman/fpl-solver.git
    cd fpl-solver
    ```

    (If you don't have a repo, just ensure all three `.py` files are in the same directory.)

2.  **Create a Virtual Environment (Recommended):**

    ```bash
    python -m venv venv
    source venv/bin/activate
    ```

3.  **Install locally:**
    Install `fpl-solver` locally:

    ```bash
    pip install .
    ```


## 🚀 Usage

Once you have set up the environment and installed the dependencies, you can run the optimizer from your terminal:

```bash
python fpl_solver.py
```

The script will:

1.  Initialize the FPL Predictor to fetch the latest data.

2.  Calculate expected points for all players over the number of gameweeks specified in `fpl_config.py`.

3.  Run the optimization solver.

4.  Print the optimal 15-player squad, its total cost, and total expected points.

## ⚙️ Configuration

All key parameters are located in `fpl_config.py`. You can modify these values to experiment with different scenarios:

* **`OPTIMIZATION_GAMEWEEKS`**: The number of upcoming gameweeks the solver should consider for xP calculation (e.g., `1` for the next gameweek, `3` for the next three).

* **`BUDGET`**: Your total FPL budget in millions of pounds (e.g., `100.0`).

* **`MAX_PLAYERS_PER_TEAM`**: The maximum number of players you want from any single Premier League team (FPL limit is usually `3`).

* **`FPL_POINTS`**: A dictionary defining the points awarded for various FPL events (goals, assists, clean sheets, etc.).

* **`MIN_MINUTES_THRESHOLD`**: Minimum minutes played for a player's per-90 stats to be considered fully reliable.

* **`VERY_LOW_MINUTES_THRESHOLD`**: Minutes threshold below which per-90 stats are heavily regressed.

* `YELLOW_CARD_PROB`, `RED_CARD_PROB`, `PENALTY_MISS_PROB`, **`OWN_GOAL_PROB`**: Heuristic probabilities for negative events.

* **`DEFAULT_SUB_MINUTES`**: Assumed average minutes for players who get some minutes but rarely start.

* **`DEFAULT_UNKNOWN_PLAYER_MINUTES`**: Very low default minutes for players with almost no historical data.

## 📊 Output

The script will output a detailed summary of your optimized FPL squad to the console, similar to this:

```
--- FPL Optimized Squad ---
Total Cost: £XX.Xm
Total Expected Points: XXX.XX

--- Goalkeepers ---
   name        team  cost  expected_points
...

--- Defenders ---
   name        team  cost  expected_points
...

--- Midfielders ---
   name        team  cost  expected_points
...

--- Forwards ---
   name        team  cost  expected_points
...

--- Team Breakdown ---
team
Team A    3
Team B    2
...
```

## 💡 Future Improvements
* **Improved Data Source:** The FPL API is limited in the type of data it provides, we cannot really calculate defensive contributions.

* **Captaincy and Vice-Captaincy Selection:** Integrate logic to select the best captain and vice-captain for double points.

* **Transfer Optimization:** Add functionality to suggest optimal transfers week-to-week, considering free transfers and hits.

* **Chip Uses:** Chip usage is currently not a feature.
