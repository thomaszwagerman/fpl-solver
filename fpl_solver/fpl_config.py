"""
fpl_config.py

Configuration settings for the FPL Expected Points Predictor and Solver.
This file centralizes all constants related to FPL scoring, thresholds, and optimization parameters.
Updated for 2025/26 season rules based on user input for specific scoring changes.
"""

# FPL Point System
FPL_POINTS = {
    "appearance_points_lt_60": 1,  # For playing up to 60 minutes
    "appearance_points_gte_60": 2,  # For playing 60 minutes or more (excluding stoppage time)
    "goal_gk": 10,  # For each goal scored by a goalkeeper
    "goal_def": 6,  # For each goal scored by a defender
    "goal_mid": 5,  # For each goal scored by a midfielder
    "goal_fwd": 4,  # For each goal scored by a forward
    "assist_points": 3,  # For each goal assist
    "clean_sheet_gk_def": 4,  # For a clean sheet by a goalkeeper or defender
    "clean_sheet_mid": 1,  # For a clean sheet by a midfielder (New for 2025/26 rules)
    "saves_3_points": 1,  # For every 3 shot saves by a goalkeeper
    "cbit_def_points": 2,  # For accumulating 10 or more Clearances, Blocks, Interceptions (CBI) & Tackles (defenders)
    "cbirt_mid_fwd_points": 2,  # For accumulating 12 or more Clearances, Blocks, Interceptions (CBI), Tackles & Recoveries (midfielders & forwards)
    "penalty_save_points": 5,  # For each penalty save
    "conceded_2_goals_deduction": -1,  # Per 2 goals conceded by a goalkeeper or defender
    "yellow_card_deduction": -1,  # For each yellow card
    "red_card_deduction": -3,  # For each red card
    "penalty_miss_deduction": -2,  # For each penalty miss
    "own_goal_deduction": -2,  # For each own goal
    # Bonus points factor is now more of a scaling for expected BPS score
    "bonus_points_scaling_factor": 0.005,  # A small factor to convert BPS score to expected bonus points (Model specific)
}

# Define thresholds for minutes played for per-90 stats reliability
MIN_MINUTES_THRESHOLD = 2500  # Players must have played at least this many minutes for reliable per-90 stats
VERY_LOW_MINUTES_THRESHOLD = (
    450  # Players below this will have their per-90 stats effectively zeroed out
)

# Probabilities for minor negative events (used in xP calculation)
YELLOW_CARD_PROB = 0.05
RED_CARD_PROB = 0.005
PENALTY_MISS_PROB = 0.01
OWN_GOAL_PROB = 0.002

# Heuristic probabilities for the new defensive contribution points (if direct event data is not available)
# These are internal model parameters, not direct FPL rules.
CBIT_DEF_PROB = 0.3  # Heuristic probability for defenders/GKs to hit 10 CBIT
CBIRT_MID_FWD_PROB = 0.15  # Heuristic probability for mids/fwds to hit 12 CBIRT

# Default average minutes for players with some minutes but no starts (e.g., regular subs)
DEFAULT_SUB_MINUTES = 30.0

# Default expected minutes for new players or those with very sparse data
DEFAULT_UNKNOWN_PLAYER_MINUTES = 10.0

# --- Solver Configuration ---
OPTIMIZATION_GAMEWEEKS = 3  # Number of upcoming gameweeks to optimize for
BUDGET = 100.0  # Total budget for the squad in millions of pounds
MAX_PLAYERS_PER_TEAM = (
    3  # Maximum number of players allowed from any single Premier League team
)

# --- Chip Configuration ---
# Maximum number of times each chip can be used within the OPTIMIZATION_GAMEWEEKS horizon
CHIP_ALLOWANCES = {
    "free_hit": 0,
    "wildcard": 0,
    "bench_boost": 1,
    "triple_captain": 0,
}

# --- Transfer Rules ---
INITIAL_FREE_TRANSFERS = 1
MAX_FREE_TRANSFERS_SAVED = 5
POINTS_PER_HIT = 4  # Points deduction per extra transfer

# --- Player Exclusion Configuration ---
# List of player IDs to exclude from prediction and optimization.
EXCLUDED_PLAYERS_BY_ID = []  # Example: [123, 456, 789] for specific player IDs

# List of player full names (case-sensitive) to exclude.
# Ensure names match exactly as they appear in the FPL data (e.g., "Erling Haaland").
EXCLUDED_PLAYERS_BY_NAME = [
    "Kepa Arrizabalaga Revuelta",
    "Christian Nørgaard",
]  # Example: ["Erling Haaland", "Mohamed Salah"]

# List of dictionaries, each specifying a team and position to exclude all players from.
# The 'position' should match your defined positions (e.g., "GK", "DEF", "MID", "FWD").
EXCLUDED_PLAYERS_BY_TEAM_AND_POSITION = [
    # Example: Exclude all goalkeepers from Manchester City
    # {"team": "Man City", "position": "GK"},
    # Example: Exclude all forwards from Arsenal
    # {"team": "Arsenal", "position": "FWD"}
]

# --- Enforced Player Configuration ---
# List of player IDs to enforce in the squad for the entire optimization horizon.
ENFORCED_PLAYERS_BY_ID = []  # Example: [101, 202]

# List of player full names (case-sensitive) to enforce in the squad.
ENFORCED_PLAYERS_BY_NAME = [
#    "Erling Haaland"
]  # Example: ["Mohamed Salah", "Erling Haaland"]

# List of dictionaries, each specifying a team and position to enforce at least one player from.
# This ensures that if you, for example, want at least one Arsenal defender, you can specify it.
ENFORCED_PLAYERS_BY_TEAM_AND_POSITION = [
    # Example: Enforce at least one defender from Liverpool
    # {"team": "Liverpool", "position": "DEF", "min_players": 1},
    # Example: Enforce at least two midfielders from Man City
    # {"team": "Man City", "position": "MID", "min_players": 2}
]
