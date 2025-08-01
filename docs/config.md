# Configuration

The `config.py` file centralizes all configurable parameters for the FPL Expected Points Predictor and Solver. This allows for easy adjustment of FPL scoring rules, thresholds, and optimization settings without modifying the core logic of the predictor or optimizer.

## FPL Point System (`FPL_POINTS`)

A dictionary defining the points awarded for various events in Fantasy Premier League. These values are based on the 2025/26 season rules as specified.

| Key | Description | Default Value |
| :----- | :----- | :----- |
| `appearance_points_lt_60` | Points for playing up to 60 minutes. | `1` |
| `appearance_points_gte_60` | Points for playing 60 minutes or more (excluding stoppage time). | `2` |
| `goal_gk` | Points for each goal scored by a goalkeeper. | `10` |
| `goal_def` | Points for each goal scored by a defender. | `6` |
| `goal_mid` | Points for each goal scored by a midfielder. | `5` |
| `goal_fwd` | Points for each goal scored by a forward. | `4` |
| `assist_points` | Points for each goal assist. | `3` |
| `clean_sheet_gk_def` | Points for a clean sheet by a goalkeeper or defender. | `4` |
| `clean_sheet_mid` | Points for a clean sheet by a midfielder (New for 2025/26 rules). | `1` |
| `saves_3_points` | Points for every 3 shot saves by a goalkeeper. | `1` |
| `cbit_def_points` | For accumulating 10 or more Clearances, Blocks, Interceptions (CBI) & Tackles (defenders). | `2` |
| `cbirt_mid_fwd_prob` | For accumulating 12 or more Clearances, Blocks, Interceptions (CBI), Tackles & Recoveries (midfielders & forwards). | `2` |
| `penalty_save_points` | For each penalty save. | `5` |
| `conceded_2_goals_deduction` | Per 2 goals conceded by a goalkeeper or defender. | `-1` |
| `yellow_card_deduction` | For each yellow card. | `-1` |
| `red_card_deduction` | For each red card. | `-3` |
| `penalty_miss_deduction` | For each penalty miss. | `-2` |
| `own_goal_deduction` | For each own goal. | `-2` |
| `bonus_points_scaling_factor` | A small factor to convert BPS score to expected bonus points (Model specific heuristic). | `0.005` |

## Thresholds for Minutes Played

These constants define thresholds used in predicting player minutes and assessing the reliability of per-90 statistics.

* `MIN_MINUTES_THRESHOLD`: Players must have played at least this many minutes for their per-90 stats to be considered reliable.

  * **Default:** `2500`

* `VERY_LOW_MINUTES_THRESHOLD`: Players below this minute threshold will have their per-90 stats effectively zeroed out, indicating they are unlikely to play significant minutes.

  * **Default:** `450`

## Probabilities for Minor Negative Events

These probabilities are used in the xP calculation for rare negative events.

* `YELLOW_CARD_PROB`: Probability of a player receiving a yellow card in a given match.

  * **Default:** `0.05`

* `RED_CARD_PROB`: Probability of a player receiving a red card in a given match.

  * **Default:** `0.005`

* `PENALTY_MISS_PROB`: Probability of a player missing a penalty.

  * **Default:** `0.01`

* `OWN_GOAL_PROB`: Probability of a player scoring an own goal.

  * **Default:** `0.002`

## Default Expected Minutes

* `DEFAULT_SUB_MINUTES`: Default average minutes assigned to players who typically come on as substitutes.

  * **Default:** `15.0`

* `DEFAULT_UNKNOWN_PLAYER_MINUTES`: Default expected minutes for new players or those with very sparse historical data.

  * **Default:** `1.0`

## xP Confidence Factors

These factors are applied to scale expected points based on a player's historical minutes, helping to discourage selection of unproven players.

* `very_low_minutes`: Applied to players with less than `VERY_LOW_MINUTES_THRESHOLD` minutes.
  * **Default:** `0.25` (reduces xP by 75%)

* `low_minutes`: Applied to players with less than `MIN_MINUTES_THRESHOLD` minutes.
  * **Default:** `0.5` (reduces xP by 50%)

* `proven`: Applied to players with more than `MIN_MINUTES_THRESHOLD` minutes.
  * **Default:** `1.0` (no reduction)

## Solver Configuration

These parameters control the behavior of the `FPLOptimizer`.

* `OPTIMIZATION_GAMEWEEKS`: The number of upcoming gameweeks the solver will consider for xP calculation (e.g., `1` for the next gameweek, `3` for the next three).

  * **Default:** `3`

* `BUDGET`: Your total FPL budget in millions of pounds (e.g., `100.0`).

  * **Default:** `100.0`

* `MAX_PLAYERS_PER_TEAM`: The maximum number of players you want from any single Premier League team (FPL limit is usually `3`).

  * **Default:** `3`

## Chip Configuration (`CHIP_ALLOWANCES`)

A dictionary specifying the maximum number of times each FPL chip can be used within the `OPTIMIZATION_GAMEWEEKS` horizon.

| Chip Name | Description | Default Allowance |
| :----- | :----- | :----- |
| `free_hit` | Free Hit chip allowance. | `0` |
| `wildcard` | Wildcard chip allowance. | `0` |
| `bench_boost` | Bench Boost chip allowance. | `1` |
| `triple_captain` | Triple Captain chip allowance. | `0` |

## Transfer Rules

These constants define the rules governing transfers between gameweeks.

* `INITIAL_FREE_TRANSFERS`: The number of free transfers available at the start of the optimization horizon (typically Gameweek 1).

  * **Default:** `1`

* `MAX_FREE_TRANSFERS_SAVED`: The maximum number of free transfers that can be saved for future gameweeks.

  * **Default:** `5`

* `POINTS_PER_HIT`: The points deduction incurred for each transfer made beyond the available free transfers.

  * **Default:** `4`

## Player Exclusion Configuration

These lists allow you to explicitly exclude certain players from being considered by the predictor and optimizer.

| Variable | Description | Default Value | Example |
| :----- | :----- | :----- | :----- |
| `EXCLUDED_PLAYERS_BY_ID` | A list of FPL player IDs to exclude. | `[]` (empty list) | `[123, 456]` |
| `EXCLUDED_PLAYERS_BY_NAME` | A list of player full names (case-sensitive) to exclude. Ensure names match exactly as they appear in the FPL data. | `["Kepa Arrizabalaga Revuelta", "Christian Nørgaard"]` | `["Erling Haaland", "Mohamed Salah"]` |
| `EXCLUDED_PLAYERS_BY_TEAM_AND_POSITION` | A list of dictionaries, each specifying a team and position from which all players should be excluded. | `[]` (empty list) | `[{"team": "Man City", "position": "GK"}, {"team": "Arsenal", "position": "FWD"}]` |

## Enforced Player Configuration

These lists allow you to explicitly enforce certain players or player types to be included in the optimized squad.

| Variable | Description | Default Value | Example |
| :----- | :----- | :----- | :----- |
| `ENFORCED_PLAYERS_BY_ID` | A list of FPL player IDs to enforce in the squad for the entire optimization horizon. | `[]` (empty list) | `[101, 202]` |
| `ENFORCED_PLAYERS_BY_NAME` | A list of player full names (case-sensitive) to enforce in the squad. | `[]` (empty list) | `["Mohamed Salah", "Erling Haaland"]` |
| `ENFORCED_PLAYERS_BY_TEAM_AND_POSITION` | A list of dictionaries, each specifying a team and position from which at least one player must be enforced. You can also specify `min_players` to enforce more than one. | `[]` (empty list) | `[{"team": "Liverpool", "position": "DEF", "min_players": 1}, {"team": "Man City", "position": "MID", "min_players": 2}]` |