# FPL Squad Optimizer

This project provides a Python-based solution to optimize Fantasy Premier League (FPL) squad selection using Integer Linear Programming (ILP). It fetches player, team, and fixture data from the official FPL API, calculates Expected Points (xP) for all players, and then uses an optimization algorithm to build the highest-scoring 15-player squad within a specified budget and team limits.

This project aims to provide a **free and open-source** xP prediction algorithm, that is directly
integrated with a solver. It only uses freely available data from the FPL API.

This has obvious limitations compared to algorithms and solvers which can use pay-walled data
(such as Opta, FBREF, FFH), but we give the user flexibility to adjust the algorithm using a
configuration file.

The introduction of **defensive contribution points** in 25/26, in particular, causes an issues
because the FPL API currently return '0' defensive contribution points, and does not provide any historic data. Once the season starts, these points will be taken into account by the algorithm

## ✨ Features

* **FPL Data Integration:** Fetches up-to-date player, team, and fixture information directly from the official FPL API
* **Expected Points (xP) Prediction:** Calculates a player's expected points based on historical performance, team strengths, opponent difficulty (Fixture Difficulty Rating - FDR), and expected minutes played
* **Granular Expected Minutes:** Refined logic to predict player minutes, especially for those with low historical play, ensuring more realistic xP values
* **Multi-Gameweek Optimization:** Optimize your squad over multiple upcoming gameweeks to plan for future fixtures
* **Configurable Parameters:** Easily adjust probabilities, low-minute penalties, chip usage, player exclusion, xP thresholds, budget, and team limits via a dedicated configuration file

## 🚀 How It Works

The project is structured into three main components:

**`config.py`**

Contains all configuration variables needed by the solver and predictor:

   * FPL scoring rules
   * Player statistics
   * Squad constraints

**`xp_predictor.py`**

Calculates expected points (xP) for each player over multiple gameweeks

Accounts for:

   * Minutes played probability (with confidence adjustments)
   * Clean sheet probability
   * Goal-scoring probability
   * Assist probability
   * Bonus points probability
   * Defensive contributions (new for 2025/26)
   * Historical reliability (reduces xP for unproven players)

**`solver.py`**

Core optimization engine using xP-calculated player data

Features:

   * Sets up Integer Linear Programming (ILP) using PuLP
   * Defines squad constraints (size, positions, budget, team limits)
   * Maximizes total expected points
   * Prints detailed squad summary and breakdown position, and a team-by-team player count.

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

```bash
python run_solver.py
```

The script will:

1. Initialize the FPL Predictor to fetch the latest data
2. Calculate expected points for all players over the number of gameweeks specified in `config.py`
3. Run the optimization solver
4. Print the optimal 15-player squad, its total cost, and total expected points

## ⚙️ Configuration

All key parameters are located in `config.py`. You can modify these values to experiment with different scenarios:

### Core Settings
* **`OPTIMIZATION_GAMEWEEKS`**: Number of gameweeks to optimize for (e.g., `1` or `3`)
* **`BUDGET`**: Total FPL budget in millions (default: `100.0`)
* **`MAX_PLAYERS_PER_TEAM`**: Maximum players from one team (default: `3`)
* **`FPL_POINTS`**: Dictionary of points for all FPL events

### Minutes Thresholds
* **`MIN_MINUTES_THRESHOLD`**: Minutes for reliable per-90 stats
* **`VERY_LOW_MINUTES_THRESHOLD`**: Minutes before heavy regression
* **`DEFAULT_SUB_MINUTES`**: Expected minutes for rotation players (15.0)
* **`DEFAULT_UNKNOWN_PLAYER_MINUTES`**: Minutes for unproven players (1.0)

### Performance Adjustments
* **Negative Event Probabilities**:
  * `YELLOW_CARD_PROB`: Yellow card probability
  * `RED_CARD_PROB`: Red card probability
  * `PENALTY_MISS_PROB`: Penalty miss probability
  * `OWN_GOAL_PROB`: Own goal probability

* **`XP_CONFIDENCE_FACTORS`**:
  * Very low minutes (<450): 0.25x
  * Low minutes (<2500): 0.50x
  * Proven (≥2500): 1.00x

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

* **Improved Data Source:** The FPL API is limited in the type of data it provides, we cannot really calculate defensive contributions
* **Captaincy and Vice-Captaincy Selection:** Integrate logic to select the best captain and vice-captain for double points
* **Transfer Optimization:** Add functionality to suggest optimal transfers week-to-week, considering free transfers and hits
* **Chip Uses:** Chip usage is currently not a feature
