"""
fpl_config.py

Configuration settings for the FPL Expected Points Predictor and Solver.
This file centralizes all constants related to FPL scoring, thresholds, and optimization parameters.
"""

# FPL Point System (simplified for core events)
FPL_POINTS = {
    "appearance_points": 2,
    "goal_gk": 6,
    "goal_def": 5,
    "goal_mid": 4,
    "goal_fwd": 4,
    "assist_points": 3,
    "clean_sheet_gk_def": 4,
    "conceded_2_goals_deduction": -1,  # Per 2 goals conceded for GK/DEF
    "yellow_card_deduction": -1,
    "red_card_deduction": -3,
    "penalty_save_points": 5,
    "own_goal_deduction": -2,
    "penalty_miss_deduction": -2,
    # Bonus points factor is now more of a scaling for expected BPS score
    "bonus_points_scaling_factor": 0.005,  # A small factor to convert BPS score to expected bonus points
    # Defensive Contribution Points for 2025/26 season
    "defensive_contribution_points": 2,  # Points awarded for hitting threshold
    "defensive_contribution_prob_def": 0.3,  # Heuristic probability for defenders/GKs to hit 10 CBIT
    "defensive_contribution_prob_mid_fwd": 0.15,  # Heuristic probability for mids/fwds to hit 12 CBIRT
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

# Default average minutes for players with some minutes but no starts (e.g., regular subs)
DEFAULT_SUB_MINUTES = 30.0

# Default expected minutes for new players or those with very sparse data
DEFAULT_UNKNOWN_PLAYER_MINUTES = 10.0

# --- Solver Configuration ---
OPTIMIZATION_GAMEWEEKS = 3  # Number of upcoming gameweeks to optimize for
BUDGET = 100.0  # Total budget for the squad in millions of pounds
MAX_PLAYERS_PER_TEAM = (
    4  # Maximum number of players allowed from any single Premier League team
)

# --- Chip Configuration ---
# Maximum number of times each chip can be used within the OPTIMIZATION_GAMEWEEKS horizon
CHIP_ALLOWANCES = {
    "free_hit": 0,
    "wildcard": 1,
    "bench_boost": 1,
    "triple_captain": 0,
}

# --- Transfer Rules ---
INITIAL_FREE_TRANSFERS = 1
MAX_FREE_TRANSFERS_SAVED = (
    5
)
POINTS_PER_HIT = 4  # Points deduction per extra transfer
