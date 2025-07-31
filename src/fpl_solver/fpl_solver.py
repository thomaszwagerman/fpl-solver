import pandas as pd
from ortools.sat.python import cp_model
import sys
import os

# Import the FPLPredictor module to get real-time data and xP
from fpl_xp_predictor import FPLPredictor

# Import configurations from the new config file
from fpl_config import (
    OPTIMIZATION_GAMEWEEKS,
    BUDGET,
    MAX_PLAYERS_PER_TEAM,
    CHIP_ALLOWANCES,
    INITIAL_FREE_TRANSFERS,
    MAX_FREE_TRANSFERS_SAVED,
    POINTS_PER_HIT,
)

# Scaling factor for expected points and budget to handle float values as integers in CP-SAT
# FPL costs are in 0.1M increments, xP can be floats. Multiplying by 100 or 1000 usually
# provides enough precision. Let's use 100 for points for now, budget will be handled carefully.
POINTS_SCALING_FACTOR = 100
COST_SCALING_FACTOR = (
    10  # FPL costs are already in 0.1M increments (e.g., 4.5m is 45 in data)
)
MAX_POINTS_PER_PLAYER_PER_GW = (
    40  # A reasonable upper bound for any player's xP in a GW
)


class FPLOptimizer:
    """
    A class to optimize Fantasy Premier League (FPL) squad selection
    using the CP-SAT solver.

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
                                        'cost', 'expected_points_by_gw' (a dict of xP per GW).
        """
        required_columns = ["name", "team", "position", "cost", "expected_points_by_gw"]
        if not all(col in player_data.columns for col in required_columns):
            missing_cols = [
                col for col in required_columns if col not in player_data.columns
            ]
            raise ValueError(
                f"player_data DataFrame must contain {required_columns} columns. Missing: {missing_cols}"
            )

        self.player_data = player_data
        self.model = None  # CP-SAT model
        self.solver = None  # CP-SAT solver instance
        self.solution_printer = (
            None  # To potentially capture results without direct processing
        )
        self.selected_squad_history = {}
        self.total_cost = 0
        self.total_expected_points = 0
        self.total_transfer_hits = 0

        # Pre-calculate player indices by position and team for faster access
        self.gks_idx = self.player_data[
            self.player_data["position"] == "GK"
        ].index.tolist()
        self.defs_idx = self.player_data[
            self.player_data["position"] == "DEF"
        ].index.tolist()
        self.mids_idx = self.player_data[
            self.player_data["position"] == "MID"
        ].index.tolist()
        self.fwds_idx = self.player_data[
            self.player_data["position"] == "FWD"
        ].index.tolist()
        self.all_players_idx = self.player_data.index.tolist()
        self.unique_teams = self.player_data["team"].unique().tolist()

    def solve(
        self,
        budget: float,
        max_players_per_team: int,
        chip_allowances: dict,
        num_gameweeks: int,
    ) -> bool:
        """
        Solves the FPL optimization problem using CP-SAT.
        """
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        self.solver.parameters.log_search_progress = False  # Suppress verbose output
        self.solver.parameters.num_workers = (
            os.cpu_count()
        )  # Use all available CPU threads
        self.solver.parameters.max_time_in_seconds = (
            300  # Optional: set a time limit (5 minutes)
        )

        # Scale budget to match scaled player costs
        scaled_budget = int(budget * COST_SCALING_FACTOR)

        # Decision variables
        # Using a dictionary to map (player_idx, gameweek) to CP-SAT Boolean variables
        player_vars = {}
        starting_xi_vars = {}
        captain_var = {}
        for i in self.all_players_idx:
            for w in range(num_gameweeks):
                player_vars[(i, w)] = self.model.NewBoolVar(f"Player_{i}_GW{w}")
                starting_xi_vars[(i, w)] = self.model.NewBoolVar(
                    f"StartingXI_{i}_GW{w}"
                )
                captain_var[(i, w)] = self.model.NewBoolVar(f"Captain_{i}_GW{w}")

        use_bench_boost = [
            self.model.NewBoolVar(f"Use_Bench_Boost_GW{w}")
            for w in range(num_gameweeks)
        ]
        use_triple_captain = [
            self.model.NewBoolVar(f"Use_Triple_Captain_GW{w}")
            for w in range(num_gameweeks)
        ]

        # Transfer variables (only for GW 1 to num_gameweeks-1)
        transfer_in_vars = {}
        transfer_out_vars = {}
        for i in self.all_players_idx:
            for w in range(1, num_gameweeks):
                transfer_in_vars[(i, w)] = self.model.NewBoolVar(
                    f"Transfer_In_{i}_GW{w}"
                )
                transfer_out_vars[(i, w)] = self.model.NewBoolVar(
                    f"Transfer_Out_{i}_GW{w}"
                )

        # Integer variables for counts
        transfers_made = [
            self.model.NewIntVar(0, len(self.all_players_idx), f"Transfers_Made_GW{w}")
            for w in range(1, num_gameweeks)
        ]
        # Max free transfers can be saved is 1, plus initial 1, total 2. Add 1 for slack.
        free_transfers_available = [
            self.model.NewIntVar(
                0, MAX_FREE_TRANSFERS_SAVED + 1, f"Free_Transfers_Available_GW{w}"
            )
            for w in range(num_gameweeks)
        ]

        # Corrected: Ensure upper bound is an integer.
        # Max transfer hits could be roughly half the squad size (15 players) per gameweek.
        # So, num_gameweeks * 15 is a safe upper bound.
        max_transfer_hits_possible = num_gameweeks * 15
        transfer_hits = [
            self.model.NewIntVar(0, max_transfer_hits_possible, f"Transfer_Hits_GW{w}")
            for w in range(1, num_gameweeks)
        ]

        # Auxiliary variables for chip linearization (scaled points)
        # These are scaled integers, e.g., 20.5 xP becomes 2050
        max_possible_scaled_points = int(
            MAX_POINTS_PER_PLAYER_PER_GW * POINTS_SCALING_FACTOR
        )
        is_bench_player = {}
        actual_bench_boost_points = {}  # Integer values, scaled
        actual_triple_captain_bonus = {}  # Integer values, scaled
        for i in self.all_players_idx:
            for w in range(num_gameweeks):
                is_bench_player[(i, w)] = self.model.NewBoolVar(
                    f"Is_Bench_Player_{i}_GW{w}"
                )
                actual_bench_boost_points[(i, w)] = self.model.NewIntVar(
                    0,
                    max_possible_scaled_points,
                    f"Actual_Bench_Boost_Points_{i}_GW{w}",
                )
                actual_triple_captain_bonus[(i, w)] = self.model.NewIntVar(
                    0,
                    max_possible_scaled_points,
                    f"Actual_Triple_Captain_Bonus_{i}_GW{w}",
                )

        # Get the first gameweek number from player data
        first_gw_key = next(
            iter(
                self.player_data.loc[
                    self.all_players_idx[0], "expected_points_by_gw"
                ].keys()
            )
        )
        current_gameweek_number_start = int(first_gw_key)

        # --- Objective Function ---
        total_objective_terms = []
        for w in range(num_gameweeks):
            gw_actual = current_gameweek_number_start + w
            player_xp_gw_scaled = {
                i: int(
                    self.player_data.loc[i, "expected_points_by_gw"][gw_actual]
                    * POINTS_SCALING_FACTOR
                )
                for i in self.all_players_idx
            }

            # Base expected points from starting XI
            total_objective_terms.append(
                sum(
                    player_xp_gw_scaled[i] * starting_xi_vars[(i, w)]
                    for i in self.all_players_idx
                )
            )

            # Regular Captaincy points (additional 1x)
            total_objective_terms.append(
                sum(
                    player_xp_gw_scaled[i] * captain_var[(i, w)]
                    for i in self.all_players_idx
                )
            )

            # Chip calculations (consolidated for conciseness)
            for i in self.all_players_idx:
                xp_scaled = player_xp_gw_scaled[i]

                # Bench Boost linearization: is_bench_player[i][w] is true if player[i][w] is in squad AND NOT starting_xi[i][w]
                # is_bench_player[(i,w)] = 1  <=>  player_vars[(i,w)] = 1 AND starting_xi_vars[(i,w)] = 0
                self.model.Add(is_bench_player[(i, w)] == 1).OnlyEnforceIf(
                    player_vars[(i, w)]
                ).OnlyEnforceIf(starting_xi_vars[(i, w)].Not())
                self.model.Add(is_bench_player[(i, w)] == 0).OnlyEnforceIf(
                    player_vars[(i, w)].Not()
                )
                self.model.Add(is_bench_player[(i, w)] == 0).OnlyEnforceIf(
                    starting_xi_vars[(i, w)]
                )

                # Actual bench boost points are xp_scaled if bench_player AND bench_boost_used
                self.model.AddMultiplicationEquality(
                    actual_bench_boost_points[(i, w)],
                    [xp_scaled, is_bench_player[(i, w)], use_bench_boost[w]],
                )

                # Triple Captain linearization: actual_triple_captain_bonus[i][w] is xp_scaled if captain AND triple_captain_used
                self.model.AddMultiplicationEquality(
                    actual_triple_captain_bonus[(i, w)],
                    [xp_scaled, captain_var[(i, w)], use_triple_captain[w]],
                )

            total_objective_terms.append(
                sum(actual_bench_boost_points[(i, w)] for i in self.all_players_idx)
            )
            total_objective_terms.append(
                sum(actual_triple_captain_bonus[(i, w)] for i in self.all_players_idx)
            )

        # Transfer hits
        scaled_points_per_hit = int(POINTS_PER_HIT * POINTS_SCALING_FACTOR)
        total_objective_terms.append(
            sum(
                -scaled_points_per_hit * transfer_hits[w - 1]
                for w in range(1, num_gameweeks)
            )
        )
        self.model.Maximize(sum(total_objective_terms))

        # --- Constraints ---
        for w in range(num_gameweeks):
            # 1. Squad size and position constraints
            self.model.Add(sum(player_vars[(i, w)] for i in self.all_players_idx) == 15)
            self.model.Add(sum(player_vars[(i, w)] for i in self.gks_idx) == 2)
            self.model.Add(sum(player_vars[(i, w)] for i in self.defs_idx) == 5)
            self.model.Add(sum(player_vars[(i, w)] for i in self.mids_idx) == 5)
            self.model.Add(sum(player_vars[(i, w)] for i in self.fwds_idx) == 3)

            # 2. Budget constraint (scaled costs)
            player_costs_scaled = {
                i: int(self.player_data.loc[i, "cost"] * COST_SCALING_FACTOR)
                for i in self.all_players_idx
            }
            self.model.Add(
                sum(
                    player_costs_scaled[i] * player_vars[(i, w)]
                    for i in self.all_players_idx
                )
                <= scaled_budget
            )

            # 3. Maximum players per team constraint
            for team in self.unique_teams:
                team_players_idx = self.player_data[
                    self.player_data["team"] == team
                ].index.tolist()
                self.model.Add(
                    sum(player_vars[(i, w)] for i in team_players_idx)
                    <= max_players_per_team
                )

            # 4. Starting XI constraints
            self.model.Add(
                sum(starting_xi_vars[(i, w)] for i in self.all_players_idx) == 11
            )
            for i in self.all_players_idx:
                self.model.Add(
                    starting_xi_vars[(i, w)] <= player_vars[(i, w)]
                )  # Starter must be in squad
            self.model.Add(sum(starting_xi_vars[(i, w)] for i in self.gks_idx) == 1)
            self.model.Add(sum(starting_xi_vars[(i, w)] for i in self.defs_idx) >= 3)
            self.model.Add(sum(starting_xi_vars[(i, w)] for i in self.mids_idx) >= 2)
            self.model.Add(sum(starting_xi_vars[(i, w)] for i in self.fwds_idx) >= 1)

            # 5. Captain Constraints
            self.model.Add(sum(captain_var[(i, w)] for i in self.all_players_idx) == 1)
            for i in self.all_players_idx:
                self.model.Add(
                    captain_var[(i, w)] <= starting_xi_vars[(i, w)]
                )  # Captain must be in starting XI

        # --- Chip Usage Constraints (TOTAL usage over all gameweeks) ---
        self.model.Add(sum(use_bench_boost) <= chip_allowances.get("bench_boost", 0))
        self.model.Add(
            sum(use_triple_captain) <= chip_allowances.get("triple_captain", 0)
        )

        # --- Inter-Gameweek Constraints (Transfers and Transfer Rules) ---
        self.model.Add(free_transfers_available[0] == INITIAL_FREE_TRANSFERS)
        for w in range(1, num_gameweeks):
            # Transfers made count
            self.model.Add(
                transfers_made[w - 1]
                == sum(transfer_in_vars[(i, w)] for i in self.all_players_idx)
            )
            # Transfers in equals transfers out
            self.model.Add(
                sum(transfer_in_vars[(i, w)] for i in self.all_players_idx)
                == sum(transfer_out_vars[(i, w)] for i in self.all_players_idx)
            )

            # Free transfers calculation
            self.model.Add(
                free_transfers_available[w]
                <= free_transfers_available[w - 1] - transfers_made[w - 1] + 1
            )
            self.model.Add(free_transfers_available[w] <= MAX_FREE_TRANSFERS_SAVED + 1)
            self.model.Add(
                free_transfers_available[w] >= 0
            )  # Implicit by variable bounds, but good to be explicit

            # Transfer hits calculation (max(0, X))
            self.model.Add(
                transfer_hits[w - 1]
                >= transfers_made[w - 1] - free_transfers_available[w - 1]
            )
            self.model.Add(transfer_hits[w - 1] >= 0)  # Implicit by variable bounds

            # Squad continuity
            for i in self.all_players_idx:
                # player_vars[(i, w)] == player_vars[(i, w-1)] - transfer_out_vars[(i, w)] + transfer_in_vars[(i, w)]
                self.model.Add(
                    player_vars[(i, w)]
                    == player_vars[(i, w - 1)]
                    - transfer_out_vars[(i, w)]
                    + transfer_in_vars[(i, w)]
                )
                # Cannot transfer in and out the same player in the same GW
                self.model.Add(
                    transfer_in_vars[(i, w)] + transfer_out_vars[(i, w)] <= 1
                )

        # Solve the model
        status = self.solver.Solve(self.model)

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            print("Optimization successful! Optimal or feasible solution found.")
            self._process_solution(
                num_gameweeks,
                current_gameweek_number_start,
                player_vars,
                starting_xi_vars,
                captain_var,
                use_bench_boost,
                use_triple_captain,
                transfer_in_vars,
                transfer_out_vars,
                transfers_made,
                transfer_hits,
                free_transfers_available,
                actual_bench_boost_points,
                actual_triple_captain_bonus,
            )
            return True
        else:
            print(
                f"No optimal solution found. Status: {self.solver.StatusName(status)}"
            )
            self.selected_squad_history = {}
            self.total_cost = 0
            self.total_expected_points = 0
            self.used_chips = {}
            self.total_transfer_hits = 0
            return False

    def _process_solution(
        self,
        num_gameweeks,
        current_gameweek_number_start,
        player_vars,
        starting_xi_vars,
        captain_var,
        use_bench_boost,
        use_triple_captain,
        transfer_in_vars,
        transfer_out_vars,
        transfers_made,
        transfer_hits,
        free_transfers_available,
        actual_bench_boost_points,
        actual_triple_captain_bonus,
    ):
        """Helper to process the solved problem and populate results."""
        self.selected_squad_history = {}
        self.total_transfer_hits = 0
        self.used_chips = {}

        for w in range(num_gameweeks):
            gw_actual = current_gameweek_number_start + w

            # Efficiently get selected players and their statuses
            selected_player_indices = [
                i
                for i in self.all_players_idx
                if self.solver.Value(player_vars[(i, w)]) == 1
            ]
            selected_squad_gw = self.player_data.loc[selected_player_indices].copy()

            selected_squad_gw["is_starter"] = [
                self.solver.Value(starting_xi_vars[(i, w)]) == 1
                for i in selected_player_indices
            ]
            selected_squad_gw["is_captain"] = [
                self.solver.Value(captain_var[(i, w)]) == 1
                for i in selected_player_indices
            ]

            transfers_in_gw = 0
            transfers_out_gw = 0
            hits_gw = 0
            free_transfers_available_next_gw_val = 0

            if w > 0:
                transferred_in_indices = [
                    i
                    for i in self.all_players_idx
                    if self.solver.Value(transfer_in_vars[(i, w)]) == 1
                ]
                transferred_out_indices = [
                    i
                    for i in self.all_players_idx
                    if self.solver.Value(transfer_out_vars[(i, w)]) == 1
                ]

                # Mark transfers directly on the selected squad DataFrame
                selected_squad_gw["transfer_in"] = selected_squad_gw.index.isin(
                    transferred_in_indices
                )
                selected_squad_gw["transfer_out"] = selected_squad_gw.index.isin(
                    transferred_out_indices
                )

                transfers_in_gw = self.solver.Value(
                    transfers_made[w - 1]
                )  # transfers_made is 0-indexed for GW 1 to N-1
                transfers_out_gw = transfers_in_gw  # In equals Out constraint
                hits_gw = self.solver.Value(
                    transfer_hits[w - 1]
                )  # transfer_hits is 0-indexed for GW 1 to N-1
                self.total_transfer_hits += hits_gw
            else:
                selected_squad_gw["transfer_in"] = False
                selected_squad_gw["transfer_out"] = False

            if w < num_gameweeks:  # For current GW's free transfers
                free_transfers_available_next_gw_val = self.solver.Value(
                    free_transfers_available[w]
                )

            bench_boost_active = bool(self.solver.Value(use_bench_boost[w]))
            triple_captain_active = bool(self.solver.Value(use_triple_captain[w]))

            # Calculate actual points for the summary (un-scale them)
            gw_expected_points_xi = sum(
                self.player_data.loc[i, "expected_points_by_gw"][gw_actual]
                * (self.solver.Value(starting_xi_vars[(i, w)]))
                for i in self.all_players_idx
            )
            gw_total_bench_boost_points = (
                sum(
                    self.solver.Value(actual_bench_boost_points[(i, w)])
                    for i in self.all_players_idx
                )
                / POINTS_SCALING_FACTOR
            )
            gw_total_triple_captain_bonus = (
                sum(
                    self.solver.Value(actual_triple_captain_bonus[(i, w)])
                    for i in self.all_players_idx
                )
                / POINTS_SCALING_FACTOR
            )

            self.selected_squad_history[f"GW{gw_actual}"] = {
                "squad": selected_squad_gw,
                "total_cost": selected_squad_gw["cost"].sum(),
                "expected_points_from_xi": gw_expected_points_xi,
                "bench_boost_used": bench_boost_active,
                "triple_captain_used": triple_captain_active,
                "total_bench_boost_points": gw_total_bench_boost_points,
                "total_triple_captain_bonus": gw_total_triple_captain_bonus,
                "transfers_in_count": transfers_in_gw,
                "transfers_out_count": transfers_out_gw,
                "transfer_hits": hits_gw,
                "free_transfers_available_next_gw": free_transfers_available_next_gw_val,
            }
            self.used_chips[f"GW{gw_actual}"] = {
                "bench_boost": bench_boost_active,
                "triple_captain": triple_captain_active,
            }

        self.total_cost = self.selected_squad_history[
            f"GW{current_gameweek_number_start + num_gameweeks - 1}"
        ]["total_cost"]
        self.total_expected_points = (
            self.solver.ObjectiveValue() / POINTS_SCALING_FACTOR
        )

    def get_selected_squad(self, gameweek: int = None) -> pd.DataFrame | None:
        """Returns the selected squad for a specific gameweek (1-indexed)."""
        if not self.selected_squad_history:
            return None
        first_gw, last_gw = self._get_gw_range()
        target_gw = gameweek if gameweek is not None else last_gw
        if not (first_gw <= target_gw <= last_gw):
            print(
                f"Gameweek {target_gw} is outside the optimized range (GW{first_gw}-GW{last_gw})."
            )
            return None
        return self.selected_squad_history.get(f"GW{target_gw}", {}).get("squad")

    def get_total_cost(self, gameweek: int = None) -> float:
        """Returns the total cost for a specific gameweek (1-indexed)."""
        if not self.selected_squad_history:
            return 0
        first_gw, last_gw = self._get_gw_range()
        target_gw = gameweek if gameweek is not None else last_gw
        if not (first_gw <= target_gw <= last_gw):
            print(
                f"Gameweek {target_gw} is outside the optimized range (GW{first_gw}-GW{last_gw})."
            )
            return 0
        return self.selected_squad_history.get(f"GW{target_gw}", {}).get(
            "total_cost", 0
        )

    def get_total_expected_points(self) -> float:
        """Returns the overall total expected points across all optimized gameweeks."""
        return self.total_expected_points

    def get_gameweek_summary(self, gameweek: int):
        """Returns a dictionary summary for a specific gameweek."""
        if not self.selected_squad_history:
            return None
        first_gw, last_gw = self._get_gw_range()
        if not (first_gw <= gameweek <= last_gw):
            print(
                f"Gameweek {gameweek} is outside the optimized range (GW{first_gw}-GW{last_gw})."
            )
            return None
        return self.selected_squad_history.get(f"GW{gameweek}")

    def _get_gw_range(self):
        """Helper to get the min and max gameweeks from history."""
        if not self.selected_squad_history:
            return 0, 0
        gw_nums = [int(k.replace("GW", "")) for k in self.selected_squad_history.keys()]
        return min(gw_nums), max(gw_nums)

    def print_squad_summary(self, gameweek: int):
        """Prints a formatted summary of the selected squad for a specific gameweek."""
        if not self.selected_squad_history:
            print("No squad has been selected yet. Run the 'solve' method first.")
            return

        gw_data = self.get_gameweek_summary(gameweek)
        if not gw_data:
            return

        selected_squad = gw_data["squad"]
        # Extract variables more concisely
        total_cost = gw_data["total_cost"]
        expected_points_from_xi = gw_data["expected_points_from_xi"]
        bench_boost_used = gw_data["bench_boost_used"]
        triple_captain_used = gw_data["triple_captain_used"]
        total_bench_boost_points = gw_data["total_bench_boost_points"]
        total_triple_captain_bonus = gw_data["total_triple_captain_bonus"]
        transfers_in_count = gw_data["transfers_in_count"]
        transfers_out_count = gw_data["transfers_out_count"]
        transfer_hits_taken = gw_data["transfer_hits"]
        free_transfers_available_next_gw = gw_data["free_transfers_available_next_gw"]

        print(f"\n--- FPL Optimized Squad for Gameweek {gameweek} ---")
        print(f"Squad Cost: £{total_cost:.1f}m")
        print(f"Expected Points (Starting XI): {expected_points_from_xi:.2f}")
        total_gw_points = (
            expected_points_from_xi
            + total_bench_boost_points
            + total_triple_captain_bonus
        )
        print(
            f"Total Expected Points for GW{gameweek} (including chips): {total_gw_points:.2f}"
        )

        print("\n--- Chips Used This Gameweek ---")
        chip_summary_list = []
        if bench_boost_used:
            chip_summary_list.append(
                f"Bench Boost (Added {total_bench_boost_points:.2f} points)"
            )
        if triple_captain_used:
            chip_summary_list.append(
                f"Triple Captain (Added {total_triple_captain_bonus:.2f} bonus points)"
            )
        print(
            "- " + "\n- ".join(chip_summary_list)
            if chip_summary_list
            else "No chips used this gameweek."
        )

        # Helper for printing player details
        def print_players_by_position(position_filter, title):
            print(f"\n--- {title} (Starting XI marked with *) ---")
            for _, row in selected_squad[
                selected_squad["position"] == position_filter
            ].iterrows():
                starter_str = "*" if row["is_starter"] else ""
                captain_str = "(C)" if row["is_captain"] else ""
                transfer_status = (
                    "(IN)"
                    if row["transfer_in"]
                    else ("(OUT)" if row["transfer_out"] else "")
                )
                player_gw_xp = row["expected_points_by_gw"].get(gameweek, 0.0)
                print(
                    f"{starter_str} {row['name']} {captain_str} {transfer_status} ({row['team']}): £{row['cost']:.1f}m, {player_gw_xp} xP"
                )

        print_players_by_position("GK", "Goalkeepers")
        print_players_by_position("DEF", "Defenders")
        print_players_by_position("MID", "Midfielders")
        print_players_by_position("FWD", "Forwards")

        print(f"\n--- Team Breakdown for GW{gameweek} ---")
        print(
            selected_squad["team"].value_counts().to_string()
        )  # Use to_string for better formatting

        first_gw_in_history, last_gw_in_history = self._get_gw_range()
        if gameweek >= first_gw_in_history:
            print(
                f"\n  Transfers In: {transfers_in_count}, Transfers Out: {transfers_out_count}"
            )
            print(
                f"  Transfer Hits: {transfer_hits_taken} (-{transfer_hits_taken * POINTS_PER_HIT} points)"
            )
            if gameweek < last_gw_in_history:
                print(
                    f"  Free Transfers Available for Next GW: {free_transfers_available_next_gw}"
                )
        print("---------------------------\n")

    def print_overall_summary(self):
        """Prints an overall summary of the multi-week optimization results."""
        if not self.selected_squad_history:
            print("No optimization results to summarize.")
            return

        print("\n=== Overall Multi-Week FPL Optimization Summary ===")
        print(
            f"Total Expected Points Across All Gameweeks: {self.total_expected_points:.2f}"
        )

        last_gw_key = max(
            self.selected_squad_history.keys(), key=lambda k: int(k.replace("GW", ""))
        )
        print(
            f"Squad Cost ({last_gw_key}): £{self.selected_squad_history[last_gw_key]['total_cost']:.1f}m"
        )
        print(
            f"Total Transfer Hits Taken: {self.total_transfer_hits} (-{self.total_transfer_hits * POINTS_PER_HIT} points)"
        )

        print("\n--- Chip Usage Across Gameweeks ---")
        sorted_gw_keys = sorted(
            self.used_chips.keys(), key=lambda k: int(k.replace("GW", ""))
        )
        for gw_str in sorted_gw_keys:
            chips = self.used_chips[gw_str]
            chip_summary = []
            if chips["bench_boost"]:
                chip_summary.append("Bench Boost")
            if chips["triple_captain"]:
                chip_summary.append("Triple Captain")
            print(
                f"{gw_str}: {', '.join(chip_summary) if chip_summary else 'No chips used'}"
            )

        print("\n--- Gameweek-by-Gameweek Summary ---")
        for gw_str in sorted_gw_keys:
            gw_data = self.selected_squad_history[gw_str]
            print(f"\n--- {gw_str} ---")
            print(f"  Squad Cost: £{gw_data['total_cost']:.1f}m")
            print(
                f"  Expected Points (Starting XI): {gw_data['expected_points_from_xi']:.2f}"
            )
            print(
                f"  Total GW Points (incl. chips): {gw_data['expected_points_from_xi'] + gw_data['total_bench_boost_points'] + gw_data['total_triple_captain_bonus']:.2f}"
            )

            transfers_in_count = gw_data["transfers_in_count"]
            transfers_out_count = gw_data["transfers_out_count"]
            transfer_hits_taken = gw_data["transfer_hits"]
            free_transfers_available_next_gw = gw_data[
                "free_transfers_available_next_gw"
            ]

            print(
                f"  Transfers In: {transfers_in_count}, Transfers Out: {transfers_out_count}"
            )
            print(
                f"  Transfer Hits: {transfer_hits_taken} (-{transfer_hits_taken * POINTS_PER_HIT} points)"
            )
            if int(gw_str.replace("GW", "")) < max(
                int(k.replace("GW", "")) for k in self.selected_squad_history.keys()
            ):
                print(
                    f"  Free Transfers Available for Next GW: {free_transfers_available_next_gw}"
                )
            print("-----------------------------------")


# Main execution block
if __name__ == "__main__":
    print("Initializing FPL Predictor to fetch data and calculate xP...")
    predictor = FPLPredictor(gameweeks_to_predict=OPTIMIZATION_GAMEWEEKS)
    all_players_for_solver = predictor.get_players_for_optimizer()

    if not all_players_for_solver:
        print("No player data with calculated xP available. Cannot run optimizer.")
        sys.exit(1)

    player_data_for_solver = pd.DataFrame(all_players_for_solver)

    # Combined and more efficient filtering
    player_data_for_solver["total_xp_sum"] = player_data_for_solver[
        "expected_points_by_gw"
    ].apply(lambda x: sum(x.values()))
    player_data_for_solver = player_data_for_solver[
        (player_data_for_solver["total_xp_sum"] > 0)
        | (player_data_for_solver["cost"] >= 3.8)
    ].drop(columns=["total_xp_sum"])

    if player_data_for_solver.empty:
        print("No eligible players found after filtering. Cannot run optimizer.")
        sys.exit(1)

    print(
        f"Prepared {len(player_data_for_solver)} players for optimization over {OPTIMIZATION_GAMEWEEKS} gameweek(s)."
    )

    optimizer = FPLOptimizer(player_data_for_solver)

    if optimizer.solve(
        budget=BUDGET,
        max_players_per_team=MAX_PLAYERS_PER_TEAM,
        chip_allowances=CHIP_ALLOWANCES,
        num_gameweeks=OPTIMIZATION_GAMEWEEKS,
    ):
        optimizer.print_overall_summary()

        if optimizer.selected_squad_history:
            first_gw, last_gw = optimizer._get_gw_range()
            print("\n--- Detailed Squad Summary for Each Optimized Gameweek ---")
            for gw_num in range(first_gw, last_gw + 1):
                optimizer.print_squad_summary(gameweek=gw_num)
        else:
            print(
                "\nNo detailed per-gameweek summary available as no optimal solution was found."
            )
    else:
        print(
            "Could not find an optimal FPL squad with the given parameters for multi-week optimization."
        )
        print(
            "Consider adjusting the 'BUDGET', 'MAX_PLAYERS_PER_TEAM', 'CHIP_ALLOWANCES', or 'OPTIMIZATION_GAMEWEEKS'."
        )
        print(
            "Also, review the player data to ensure enough eligible players are available in each category."
        )
