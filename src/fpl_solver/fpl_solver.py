import pandas as pd
from pulp import *
import sys
import os

# Import the FPLPredictor module to get real-time data and xP
from fpl_xp_predictor import FPLPredictor

# Import configurations from the new config file
from fpl_config import OPTIMIZATION_GAMEWEEKS, BUDGET, MAX_PLAYERS_PER_TEAM


class FPLOptimizer:
    """
    A class to optimize Fantasy Premier League (FPL) squad selection
    using Integer Linear Programming (ILP).

    The optimizer aims to select a 15-player squad (2 GKs, 5 DEFs, 5 MIDs, 3 FWDs)
    within a budget, with a maximum number of players from any single team,
    to maximize the total expected points.
    """

    def __init__(self, player_data: pd.DataFrame):
        """
        Initializes the FPLOptimizer with player data.

        Args:
            player_data (pd.DataFrame): A DataFrame containing player information
                                        with columns: 'name', 'team', 'position',
                                        'cost', 'expected_points'.
        """
        required_columns = ["name", "team", "position", "cost", "expected_points"]
        if not all(col in player_data.columns for col in required_columns):
            missing_cols = [
                col for col in required_columns if col not in player_data.columns
            ]
            raise ValueError(
                f"player_data DataFrame must contain {required_columns} columns. Missing: {missing_cols}"
            )

        self.player_data = player_data
        self.problem = None
        self.selected_squad = None
        self.total_cost = 0
        self.total_expected_points = 0

    def solve(self, budget: float, max_players_per_team: int) -> bool:
        """
        Solves the FPL optimization problem.

        Args:
            budget (float): The maximum budget in millions of pounds.
            max_players_per_team (int): The maximum number of players allowed from
                                        any single Premier League team.

        Returns:
            bool: True if a solution was found, False otherwise.
        """
        self.problem = LpProblem("FPL Squad Optimization", LpMaximize)

        player_vars = LpVariable.dicts("Player", self.player_data.index, 0, 1, LpBinary)

        self.problem += (
            lpSum(
                self.player_data.loc[i, "expected_points"] * player_vars[i]
                for i in self.player_data.index
            ),
            "Total Expected Points",
        )

        self.problem += (
            lpSum(player_vars[i] for i in self.player_data.index) == 15,
            "Total Players",
        )

        gks = self.player_data[self.player_data["position"] == "GK"].index
        defs = self.player_data[self.player_data["position"] == "DEF"].index
        mids = self.player_data[self.player_data["position"] == "MID"].index
        fwds = self.player_data[self.player_data["position"] == "FWD"].index

        self.problem += lpSum(player_vars[i] for i in gks) == 2, "Goalkeepers Count"
        self.problem += lpSum(player_vars[i] for i in defs) == 5, "Defenders Count"
        self.problem += lpSum(player_vars[i] for i in mids) == 5, "Midfielders Count"
        self.problem += lpSum(player_vars[i] for i in fwds) == 3, "Forwards Count"

        self.problem += (
            lpSum(
                self.player_data.loc[i, "cost"] * player_vars[i]
                for i in self.player_data.index
            )
            <= budget,
            "Total Budget",
        )

        for team in self.player_data["team"].unique():
            team_players = self.player_data[self.player_data["team"] == team].index
            self.problem += (
                lpSum(player_vars[i] for i in team_players) <= max_players_per_team,
                f"Max Players from {team}",
            )

        try:
            self.problem.solve()
        except Exception as e:
            print(f"Error solving the problem: {e}")
            return False

        if LpStatus[self.problem.status] == "Optimal":
            print("Optimization successful! Optimal solution found.")
            self.selected_squad = self.player_data[
                [player_vars[i].varValue == 1 for i in self.player_data.index]
            ].copy()
            self.total_cost = self.selected_squad["cost"].sum()
            self.total_expected_points = self.selected_squad["expected_points"].sum()
            return True
        else:
            print(f"No optimal solution found. Status: {LpStatus[self.problem.status]}")
            self.selected_squad = None
            self.total_cost = 0
            self.total_expected_points = 0
            return False

    def get_selected_squad(self) -> pd.DataFrame | None:
        return self.selected_squad

    def get_total_cost(self) -> float:
        return self.total_cost

    def get_total_expected_points(self) -> float:
        return self.total_expected_points

    def print_squad_summary(self):
        """
        Prints a formatted summary of the selected squad.
        """
        if self.selected_squad is None:
            print("No squad has been selected yet. Run the 'solve' method first.")
            return

        print("\n--- FPL Optimized Squad ---")
        print(f"Total Cost: £{self.total_cost:.1f}m")
        print(f"Total Expected Points: {self.total_expected_points:.2f}")
        print("\n--- Goalkeepers ---")
        print(
            self.selected_squad[self.selected_squad["position"] == "GK"][
                ["name", "team", "cost", "expected_points"]
            ]
        )
        print("\n--- Defenders ---")
        print(
            self.selected_squad[self.selected_squad["position"] == "DEF"][
                ["name", "team", "cost", "expected_points"]
            ]
        )
        print("\n--- Midfielders ---")
        print(
            self.selected_squad[self.selected_squad["position"] == "MID"][
                ["name", "team", "cost", "expected_points"]
            ]
        )
        print("\n--- Forwards ---")
        print(
            self.selected_squad[self.selected_squad["position"] == "FWD"][
                ["name", "team", "cost", "expected_points"]
            ]
        )
        print("\n--- Team Breakdown ---")
        print(self.selected_squad["team"].value_counts())
        print("---------------------------\n")


# Main execution block
if __name__ == "__main__":
    print("Initializing FPL Predictor to fetch data and calculate xP...")
    # Use OPTIMIZATION_GAMEWEEKS from fpl_config.py
    predictor = FPLPredictor(gameweeks_to_predict=OPTIMIZATION_GAMEWEEKS)

    # Get the prepared player data from the predictor
    all_players_for_solver = predictor.get_players_for_optimizer()

    if not all_players_for_solver:
        print("No player data with calculated xP available. Cannot run optimizer.")
        sys.exit(1)

    # Convert the list of dictionaries to a pandas DataFrame
    player_data_for_solver = pd.DataFrame(all_players_for_solver)

    # Filter out players with 0 expected points or very low cost (e.g., non-playing, injured)
    # The predictor already sets xP to 0 for unavailable players, but an explicit filter is good.
    player_data_for_solver = player_data_for_solver[
        player_data_for_solver["expected_points"] > 0
    ]
    player_data_for_solver = player_data_for_solver[
        player_data_for_solver["cost"] >= 3.8
    ]  # Min FPL cost for a playing player

    if player_data_for_solver.empty:
        print("No eligible players found after filtering. Cannot run optimizer.")
        sys.exit(1)

    print(
        f"Prepared {len(player_data_for_solver)} players for optimization over {OPTIMIZATION_GAMEWEEKS} gameweek(s)."
    )

    # Initialize the optimizer with the fetched and processed player data
    optimizer = FPLOptimizer(player_data_for_solver)

    # Solve the problem using BUDGET and MAX_PLAYERS_PER_TEAM from fpl_config.py
    if optimizer.solve(budget=BUDGET, max_players_per_team=MAX_PLAYERS_PER_TEAM):
        optimizer.print_squad_summary()
    else:
        print("Could not find an optimal FPL squad with the given parameters.")
        print(
            "Consider adjusting the 'BUDGET' or 'MAX_PLAYERS_PER_TEAM' in fpl_config.py."
        )
        print(
            "Also, review the player data to ensure enough eligible players are available in each category."
        )
