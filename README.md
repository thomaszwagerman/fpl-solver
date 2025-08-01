# FPL Squad Optimizer

This project provides a Python-based solution to optimize Fantasy Premier League (FPL) squad selection using Integer Linear Programming (ILP). It fetches player, team, and fixture data from the official FPL API, calculates Expected Points (xP) for all players, and then uses an optimization algorithm to build the highest-scoring 15-player squad within a specified budget and team limits.

This project aims to provide a **free and open-source** xP prediction algorithm, that is directly
integrated with a solver. It only uses freely available data from the FPL API.

This has obvious limitations compared to algorithms and solvers which can use pay-walled data
(such as Opta, FBREF, FFH), but we give the user flexibility to adjust the algorithm using a
configuration file.

The introduction of **defensive contribution points** in 25/26, in particular, causes an issues
because FPL do not provide any sensible data from which this can be deduced. 

## ✨ Features

* **FPL Data Integration:** Fetches up-to-date player, team, and fixture information directly from the official FPL API.

* **Expected Points (xP) Prediction:** Calculates a player's expected points based on historical performance, team strengths, opponent difficulty (Fixture Difficulty Rating - FDR), and expected minutes played.

* **Granular Expected Minutes:** Refined logic to predict player minutes, especially for those with low historical play, ensuring more realistic xP values.

* **Multi-Gameweek Optimization:** Optimize your squad over multiple upcoming gameweeks to plan for future fixtures.

* **Configurable Parameters:** Easily adjust probabilities, low-minute penalties, chip usage, player exclusion, xP thresholds, budget, and team limits via a dedicated configuration file.

## 🚀 How It Works

The project is structured into three main components:

1. **`config.py`**:
   This file contains all the configuration variables needed by the solver and predictor, including:
   - FPL scoring rules
   - Player statistics
   - Squad constraints

2. **`xp_predictor.py`**:
   This code calculates expected points (xP) for each player over the next few gameweeks. It accounts for:
   - Minutes played probability (with confidence adjustments based on historical minutes)
   - Clean sheet probability
   - Goal-scoring probability
   - Assist probability
   - Bonus points probability
   - Defensive contributions (new for 2025/26 season)
   - Historical reliability (reduces xP for unproven players)

3. **`solver.py`**:
   This is the core optimization engine. It takes the xP-calculated player data from `xp_predictor.py` and:

   * Sets up an Integer Linear Programming (ILP) problem using the `PuLP` library.

   * Defines constraints for squad size (15 players), position counts (2 GKs, 5 DEFs, 5 MIDs, 3 FWDs), total budget, and maximum players per team.

   * Maximizes the total expected points of the selected squad.

   * Prints a detailed summary of the optimal squad, including costs and xP breakdown by position, and a team-by-team player count.

## 🛠️ Setup and Installation

To get the FPL Squad Optimizer running on your local machine, follow these steps:

1. **Clone the Repository (if applicable):**

   ```
   git clone git@github.com:thomaszwagerman/fpl-solver.git
   cd fpl-solver
   ```

2. **Create a Virtual Environment (Recommended):**

   ```
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install locally:**
   Install `fpl-solver` locally:

   ```
   pip install .
   ```

## 🚀 Usage

Once you have set up the environment and installed the dependencies, you can run the optimizer from your terminal:

```
python run_solver.py
```

The script will:

1. Initialize the FPL Predictor to fetch the latest data.

2. Calculate expected points for all players over the number of gameweeks specified in `config.py`.

3. Run the optimization solver.

4. Print the optimal 15-player squad, its total cost, and total expected points.

## ⚙️ Configuration

All key parameters are located in `config.py`. You can modify these values to experiment with different scenarios:

* **`OPTIMIZATION_GAMEWEEKS`**: The number of upcoming gameweeks the solver should consider for xP calculation (e.g., `1` for the next gameweek, `3` for the next three).

* **`BUDGET`**: Your total FPL budget in millions of pounds (e.g., `100.0`).

* **`MAX_PLAYERS_PER_TEAM`**: The maximum number of players you want from any single Premier League team (FPL limit is usually `3`).

* **`FPL_POINTS`**: A dictionary defining the points awarded for various FPL events (goals, assists, clean sheets, etc.).

* **`MIN_MINUTES_THRESHOLD`**: Minimum minutes played for a player's per-90 stats to be considered fully reliable.

* **`VERY_LOW_MINUTES_THRESHOLD`**: Minutes threshold below which per-90 stats are heavily regressed.

* `YELLOW_CARD_PROB`, `RED_CARD_PROB`, `PENALTY_MISS_PROB`, **`OWN_GOAL_PROB`**: Heuristic probabilities for negative events.

* **`DEFAULT_SUB_MINUTES`**: Assumed average minutes (15.0) for players who get some minutes but rarely start.

* **`DEFAULT_UNKNOWN_PLAYER_MINUTES`**: Very low default minutes (1.0) for players with almost no historical data.

* **`XP_CONFIDENCE_FACTORS`**: Scale factors applied to xP based on historical minutes:
  - 0.25x for players with very low minutes (<450)
  - 0.50x for players with low minutes (<2500)
  - 1.00x for proven players (≥2500 minutes)

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
