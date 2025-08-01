"""
FPL Squad Optimizer using PuLP for Integer Linear Programming (ILP).

This module provides optimization functionality to select the best possible
FPL squad over multiple gameweeks, considering transfer constraints and chips.
"""

import pandas as pd
from pulp import (
    LpProblem,
    LpMaximize,
    LpVariable,
    LpBinary,
    LpInteger,
    LpContinuous,
    lpSum,
    PULP_CBC_CMD,
    value,
    LpStatus,
)

# Import configurations from config file
from .config import (
    CHIP_ALLOWANCES,
    BUDGET,
    ENFORCED_PLAYERS_BY_ID,
    ENFORCED_PLAYERS_BY_NAME,
    ENFORCED_PLAYERS_BY_TEAM_AND_POSITION,
    MAX_FREE_TRANSFERS_SAVED,
    INITIAL_FREE_TRANSFERS,
    POINTS_PER_HIT,
    MAX_PLAYERS_PER_TEAM,
)


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
        self.problem = None
        self.selected_squad_history = {}  # To store squad for each gameweek
        self.total_cost = 0
        self.total_expected_points = 0
        self.total_transfer_hits = 0

        # --- Process Enforced Players ---
        self.enforced_player_indices = set()
        self.enforced_team_pos_requirements = []

        print("\n--- Processing Enforced Players ---")

        # Enforce by Player ID
        for player_id in ENFORCED_PLAYERS_BY_ID:
            found_player = self.player_data[self.player_data["id"] == player_id]
            if not found_player.empty:
                player_idx = found_player.index[0]
                self.enforced_player_indices.add(player_idx)
                print(
                    f"Enforcing player by ID: {found_player.loc[player_idx, 'name']} (ID: {player_id})"
                )
            else:
                print(
                    f"Warning: Enforced player with ID {player_id} not found in data."
                )

        # Enforce by Player Name
        for player_name in ENFORCED_PLAYERS_BY_NAME:
            found_player = self.player_data[self.player_data["name"] == player_name]
            if not found_player.empty:
                player_idx = found_player.index[0]
                self.enforced_player_indices.add(player_idx)
                print(f"Enforcing player by name: {player_name}")
            else:
                print(f"Warning: Enforced player '{player_name}' not found in data.")

        # Enforce by Team and Position
        for requirement in ENFORCED_PLAYERS_BY_TEAM_AND_POSITION:
            team = requirement.get("team")
            position = requirement.get("position")
            if team and position:
                # Validate team and position exist in data
                if team not in self.player_data["team"].unique():
                    print(
                        f"Warning: Enforced team '{team}' for position '{position}' not found in data."
                    )
                    continue
                if position not in self.player_data["position"].unique():
                    print(
                        f"Warning: Enforced position '{position}' for team '{team}' not found in data."
                    )
                    continue

                self.enforced_team_pos_requirements.append((team, position))
                print(f"Enforcing at least one {position} from {team}.")
            else:
                print(
                    f"Warning: Invalid enforced team/position requirement: {requirement}"
                )

        if not (
            self.enforced_player_indices
            or self.enforced_team_pos_requirements
            or ENFORCED_PLAYERS_BY_ID
            or ENFORCED_PLAYERS_BY_NAME
            or ENFORCED_PLAYERS_BY_TEAM_AND_POSITION
        ):
            print("No players or team/position combinations are enforced.")
        print("-----------------------------------\n")

    def solve(
        self,
        budget: float,
        max_players_per_team: int,
        chip_allowances: dict,
        num_gameweeks: int,
    ) -> bool:
        """
        Solves the FPL optimization problem using PuLP.

        Args:
            budget (float): The maximum budget in millions of pounds.
            max_players_per_team (int): The maximum number of players allowed from
                                        any single Premier League team.
            chip_allowances (dict): A dictionary specifying the maximum usage for each chip.
            num_gameweeks (int): The number of gameweeks to optimize over.

        Returns:
            bool: True if a solution was found, False otherwise.
        """
        self.problem = LpProblem("FPL Squad Multi-Week Optimization", LpMaximize)

        # Decision variables for player selection, indexed by player and gameweek
        player_vars = LpVariable.dicts(
            "Player", (self.player_data.index, range(num_gameweeks)), 0, 1, LpBinary
        )
        starting_xi_vars = LpVariable.dicts(
            "StartingXI", (self.player_data.index, range(num_gameweeks)), 0, 1, LpBinary
        )
        captain_var = LpVariable.dicts(
            "Captain", (self.player_data.index, range(num_gameweeks)), 0, 1, LpBinary
        )

        # Binary variables for chip usage, indexed by gameweek
        use_bench_boost = LpVariable.dicts(
            "Use_Bench_Boost", range(num_gameweeks), 0, 1, LpBinary
        )
        use_triple_captain = LpVariable.dicts(
            "Use_Triple_Captain", range(num_gameweeks), 0, 1, LpBinary
        )

        # Transfer variables
        transfer_in_vars = LpVariable.dicts(
            "Transfer_In",
            (self.player_data.index, range(1, num_gameweeks)),
            0,
            1,
            LpBinary,
        )
        transfer_out_vars = LpVariable.dicts(
            "Transfer_Out",
            (self.player_data.index, range(1, num_gameweeks)),
            0,
            1,
            LpBinary,
        )

        # Total transfers made in a gameweek (absolute count)
        transfers_made = LpVariable.dicts(
            "Transfers_Made", range(1, num_gameweeks), 0, None, LpInteger
        )
        # Free transfers available at the start of a gameweek
        free_transfers_available = LpVariable.dicts(
            "Free_Transfers_Available",
            range(num_gameweeks),
            0,
            MAX_FREE_TRANSFERS_SAVED + 1,
            LpInteger,
        )
        # Number of transfer hits taken in a gameweek
        transfer_hits = LpVariable.dicts(
            "Transfer_Hits", range(1, num_gameweeks), 0, None, LpInteger
        )

        # Auxiliary variables for linearizing chip effects
        is_bench_player = LpVariable.dicts(
            "Is_Bench_Player",
            (self.player_data.index, range(num_gameweeks)),
            0,
            1,
            LpBinary,
        )
        actual_bench_boost_points = LpVariable.dicts(
            "Actual_Bench_Boost_Points",
            (self.player_data.index, range(num_gameweeks)),
            0,
            None,
            LpContinuous,
        )
        actual_triple_captain_bonus = LpVariable.dicts(
            "Actual_Triple_Captain_Bonus",
            (self.player_data.index, range(num_gameweeks)),
            0,
            None,
            LpContinuous,
        )

        # --- Objective Function ---
        total_objective_points = []

        # Get the first gameweek number from the player data to correctly index expected_points_by_gw
        first_gw_key = next(
            iter(
                self.player_data.loc[
                    self.player_data.index[0], "expected_points_by_gw"
                ].keys()
            )
        )
        current_gameweek_number_start = int(first_gw_key)

        for w in range(num_gameweeks):
            # The actual gameweek number (1-indexed)
            gw_actual = current_gameweek_number_start + w

            # Base expected points from the selected starting 11 for this gameweek
            base_points_expression_gw = lpSum(
                self.player_data.loc[i, "expected_points_by_gw"][gw_actual]
                * starting_xi_vars[i][w]
                for i in self.player_data.index
            )
            total_objective_points.append(base_points_expression_gw)

            # Regular Captaincy points (additional 1x for captain)
            captain_points_bonus_gw = lpSum(
                self.player_data.loc[i, "expected_points_by_gw"][gw_actual]
                * captain_var[i][w]
                for i in self.player_data.index
            )
            total_objective_points.append(captain_points_bonus_gw)

            # Define auxiliary variables and constraints for chips for each gameweek
            for i in self.player_data.index:
                # Use gameweek-specific player xP for chip calculations
                player_xp = self.player_data.loc[i, "expected_points_by_gw"][gw_actual]

                # Bench Boost auxiliary variables and constraints
                self.problem += (
                    is_bench_player[i][w] <= player_vars[i][w],
                    f"IsBench_Squad_{i}_{w}",
                )
                self.problem += (
                    is_bench_player[i][w] <= 1 - starting_xi_vars[i][w],
                    f"IsBench_NotStarter_{i}_{w}",
                )
                self.problem += (
                    is_bench_player[i][w]
                    >= player_vars[i][w] + (1 - starting_xi_vars[i][w]) - 1,
                    f"IsBench_Logical_{i}_{w}",
                )

                self.problem += (
                    actual_bench_boost_points[i][w]
                    <= player_xp * is_bench_player[i][w],
                    f"BenchBoost_Contr_1_{i}_{w}",
                )
                self.problem += (
                    actual_bench_boost_points[i][w] <= player_xp * use_bench_boost[w],
                    f"BenchBoost_Contr_2_{i}_{w}",
                )
                self.problem += (
                    actual_bench_boost_points[i][w]
                    >= player_xp * (is_bench_player[i][w] + use_bench_boost[w] - 1),
                    f"BenchBoost_Contr_3_{i}_{w}",
                )
                self.problem += (
                    actual_bench_boost_points[i][w] >= 0,
                    f"BenchBoost_Contr_4_{i}_{w}",
                )

                # Triple Captain auxiliary variables and constraints
                # Changed player_xp * 2 to player_xp to reflect additional 1x bonus
                self.problem += (
                    actual_triple_captain_bonus[i][w] <= player_xp * captain_var[i][w],
                    f"TripleCaptain_Contr_1_{i}_{w}",
                )
                self.problem += (
                    actual_triple_captain_bonus[i][w]
                    <= player_xp * use_triple_captain[w],
                    f"TripleCaptain_Contr_2_{i}_{w}",
                )
                self.problem += (
                    actual_triple_captain_bonus[i][w]
                    >= player_xp * (captain_var[i][w] + use_triple_captain[w] - 1),
                    f"TripleCaptain_Contr_3_{i}_{w}",
                )
                self.problem += (
                    actual_triple_captain_bonus[i][w] >= 0,
                    f"TripleCaptain_Contr_4_{i}_{w}",
                )

            # Add points from bench boost and triple captain bonus for this gameweek
            total_bench_boost_points_gw = lpSum(
                actual_bench_boost_points[i][w] for i in self.player_data.index
            )
            total_triple_captain_bonus_points_gw = lpSum(
                actual_triple_captain_bonus[i][w] for i in self.player_data.index
            )

            total_objective_points.append(total_bench_boost_points_gw)
            total_objective_points.append(total_triple_captain_bonus_points_gw)

        # Subtract transfer hits from the total objective
        total_objective_points.append(
            -POINTS_PER_HIT * lpSum(transfer_hits[w] for w in range(1, num_gameweeks))
        )

        self.problem += (
            lpSum(total_objective_points),
            "Total Expected Points Over Gameweeks",
        )

        # --- Constraints ---

        # Apply constraints for each gameweek
        for w in range(num_gameweeks):
            # 1. Select exactly 15 players for the squad
            self.problem += (
                lpSum(player_vars[i][w] for i in self.player_data.index) == 15,
                f"Total_Players_GW{w}",
            )

            # 2. Squad position constraints (2 GKs, 5 DEFs, 5 MIDs, 3 FWDs)
            gks = self.player_data[self.player_data["position"] == "GK"].index
            defs = self.player_data[self.player_data["position"] == "DEF"].index
            mids = self.player_data[self.player_data["position"] == "MID"].index
            fwds = self.player_data[self.player_data["position"] == "FWD"].index

            self.problem += (
                lpSum(player_vars[i][w] for i in gks) == 2,
                f"Goalkeepers_Count_GW{w}",
            )
            self.problem += (
                lpSum(player_vars[i][w] for i in defs) == 5,
                f"Defenders_Count_GW{w}",
            )
            self.problem += (
                lpSum(player_vars[i][w] for i in mids) == 5,
                f"Midfielders_Count_GW{w}",
            )
            self.problem += (
                lpSum(player_vars[i][w] for i in fwds) == 3,
                f"Forwards_Count_GW{w}",
            )

            # 3. Budget constraint
            # This applies to the cost of the squad for the current gameweek.
            self.problem += (
                lpSum(
                    self.player_data.loc[i, "cost"] * player_vars[i][w]
                    for i in self.player_data.index
                )
                <= budget,
                f"Total_Budget_GW{w}",
            )

            # 4. Maximum players per team constraint
            for team in self.player_data["team"].unique():
                team_players = self.player_data[self.player_data["team"] == team].index
                self.problem += (
                    lpSum(player_vars[i][w] for i in team_players)
                    <= max_players_per_team,
                    f"Max_Players_from_{team}_GW{w}",
                )

            # 5. Starting XI constraints
            # 5.1 Select exactly 11 players for the starting XI
            self.problem += (
                lpSum(starting_xi_vars[i][w] for i in self.player_data.index) == 11,
                f"Total_Starting_XI_Players_GW{w}",
            )

            # 5.2 A player can only be in the starting XI if they are in the squad
            for i in self.player_data.index:
                self.problem += (
                    starting_xi_vars[i][w] <= player_vars[i][w],
                    f"StartingXI_in_Squad_{i}_{w}",
                )

            # 5.3 Starting XI position constraints (FPL allows flexible formations, so use minimums)
            self.problem += (
                lpSum(starting_xi_vars[i][w] for i in gks) == 1,
                f"Starting_Goalkeepers_Count_GW{w}",
            )
            self.problem += (
                lpSum(starting_xi_vars[i][w] for i in defs) >= 3,
                f"Min_Starting_Defenders_Count_GW{w}",
            )
            self.problem += (
                lpSum(starting_xi_vars[i][w] for i in mids) >= 2,
                f"Min_Starting_Midfielders_Count_GW{w}",
            )
            self.problem += (
                lpSum(starting_xi_vars[i][w] for i in fwds) >= 1,
                f"Min_Starting_Forwards_Count_GW{w}",
            )

            # 6. Captain Constraints
            # 6.1 Select exactly one captain from the starting XI
            self.problem += (
                lpSum(captain_var[i][w] for i in self.player_data.index) == 1,
                f"One_Captain_GW{w}",
            )

            # 6.2 A player can only be captain if they are in the starting XI
            for i in self.player_data.index:
                self.problem += (
                    captain_var[i][w] <= starting_xi_vars[i][w],
                    f"Captain_in_StartingXI_{i}_{w}",
                )

            # --- Enforced Player Constraints---
            for player_idx in self.enforced_player_indices:
                self.problem += (
                    player_vars[player_idx][w] == 1,
                    f"Enforce_Player_{self.player_data.loc[player_idx, 'name']}_GW{w}",
                )

            for team, position in self.enforced_team_pos_requirements:
                # Filter players for the current team and position
                team_pos_players = self.player_data[
                    (self.player_data["team"] == team)
                    & (self.player_data["position"] == position)
                ].index
                if not team_pos_players.empty:
                    self.problem += (
                        lpSum(player_vars[i][w] for i in team_pos_players) >= 1,
                        f"Enforce_One_{position}_from_{team}_GW{w}",
                    )
                else:
                    print(
                        f"Warning: No players found for enforced requirement: at least one {position} from {team} for GW{gw_actual}."
                    )
                    
        # --- Chip Usage Constraints (TOTAL usage over all gameweeks) ---
        # These constraints should be outside the per-gameweek loop to avoid duplicates.
        self.problem += (
            lpSum(use_bench_boost[j] for j in range(num_gameweeks))
            <= chip_allowances.get("bench_boost", 0),
            f"Max_Bench_Boost_Usage_Total",
        )
        self.problem += (
            lpSum(use_triple_captain[j] for j in range(num_gameweeks))
            <= chip_allowances.get("triple_captain", 0),
            f"Max_Triple_Captain_Usage_Total",
        )

        # --- Inter-Gameweek Constraints (Transfers and Transfer Rules) ---
        # Initialize free transfers for GW0 (first gameweek of optimization horizon)
        # This assumes the optimization starts at GW0, and it has INITIAL_FREE_TRANSFERS.
        # If the model starts at an arbitrary GW, this would need to be an input.
        self.problem += (
            free_transfers_available[0] == INITIAL_FREE_TRANSFERS,
            f"Initial_Free_Transfers_GW0",
        )

        for w in range(1, num_gameweeks):
            # Calculate total transfers made in this gameweek
            self.problem += (
                transfers_made[w]
                == lpSum(transfer_in_vars[i][w] for i in self.player_data.index),
                f"Transfers_Made_GW{w}",
            )
            # Total transfers in must equal total transfers out for each gameweek after the first
            self.problem += (
                lpSum(transfer_in_vars[i][w] for i in self.player_data.index)
                == lpSum(transfer_out_vars[i][w] for i in self.player_data.index),
                f"Transfers_In_Equals_Out_GW{w}",
            )

            # Calculate free transfers available for the current gameweek (w)
            # Free transfers for GW_w = min(free transfers from GW_w-1 - transfers made in GW_w + 1, MAX_FREE_TRANSFERS_SAVED + 1)
            # The + 1 in MAX_FREE_TRANSFERS_SAVED + 1 is because MAX_FREE_TRANSFERS_SAVED implies how many can be *saved*,
            # so if you save 1, you have 1 (current) + 1 (saved) = 2.
            self.problem += (
                free_transfers_available[w]
                <= free_transfers_available[w - 1] - transfers_made[w] + 1,
                f"Free_Transfers_Calc_1_GW{w}",
            )
            self.problem += (
                free_transfers_available[w] <= MAX_FREE_TRANSFERS_SAVED + 1,
                f"Free_Transfers_Calc_2_GW{w}",
            )
            self.problem += (
                free_transfers_available[w] >= 0,  # Cannot have negative free transfers
                f"Free_Transfers_Non_Negative_GW{w}",
            )

            # Calculate transfer hits
            # transfer_hits[w] = max(0, transfers_made[w] - free_transfers_available_at_start_of_gw_w)
            # This needs to be linearized. If transfers_made[w] > free_transfers_available[w-1], then hit.
            # free_transfers_available[w-1] represents transfers available *before* making transfers for GW_w
            self.problem += (
                transfer_hits[w] >= transfers_made[w] - free_transfers_available[w - 1],
                f"Transfer_Hits_Calc_1_GW{w}",
            )
            self.problem += (
                transfer_hits[w] >= 0,
                f"Transfer_Hits_Calc_2_GW{w}",
            )

            for i in self.player_data.index:
                # Squad continuity: player_vars[i][w] (in squad at start of GW w)
                #                 = player_vars[i][w-1] (in squad at start of GW w-1)
                #                 - transfer_out_vars[i][w] (transferred out for GW w)
                #                 + transfer_in_vars[i][w] (transferred in for GW w)
                self.problem += (
                    player_vars[i][w]
                    == player_vars[i][w - 1]
                    - transfer_out_vars[i][w]
                    + transfer_in_vars[i][w],
                    f"Squad_Continuity_{i}_GW{w}",
                )
                # A player cannot be transferred in and out in the same gameweek
                self.problem += (
                    transfer_in_vars[i][w] + transfer_out_vars[i][w] <= 1,
                    f"No_Simultaneous_Transfer_{i}_{w}",
                )

        try:
            # The solver is called with the GLPK_CMD solver
            self.problem.solve(PULP_CBC_CMD(msg=0))  # msg=0 suppresses verbose output
        except Exception as e:
            print(f"Error solving the problem: {e}")
            return False

        if LpStatus[self.problem.status] == "Optimal":
            print("Optimization successful! Optimal solution found.")

            self.selected_squad_history = {}
            self.total_transfer_hits = 0
            for w in range(num_gameweeks):
                # The actual gameweek number (1-indexed)
                gw_actual = current_gameweek_number_start + w

                # Get selected players for the current gameweek
                selected_squad_gw = self.player_data[
                    [player_vars[i][w].varValue == 1 for i in self.player_data.index]
                ].copy()

                # Get starter and captain info for this gameweek
                is_starter_series_gw = pd.Series(
                    [
                        starting_xi_vars[i][w].varValue == 1
                        for i in self.player_data.index
                    ],
                    index=self.player_data.index,
                )
                is_captain_series_gw = pd.Series(
                    [captain_var[i][w].varValue == 1 for i in self.player_data.index],
                    index=self.player_data.index,
                )

                selected_squad_gw["is_starter"] = is_starter_series_gw.loc[
                    selected_squad_gw.index
                ]
                selected_squad_gw["is_captain"] = is_captain_series_gw.loc[
                    selected_squad_gw.index
                ]

                transfers_in_gw = 0
                transfers_out_gw = 0
                hits_gw = 0

                # Store transfer details for gameweeks > 0
                if (
                    w > 0
                ):  # Check for transfers only from GW1 onwards (index 1 in 0-indexed loop)
                    transfer_in_flags = pd.Series(
                        [
                            transfer_in_vars[i][w].varValue == 1
                            for i in self.player_data.index
                        ],
                        index=self.player_data.index,
                    )
                    transfer_out_flags = pd.Series(
                        [
                            transfer_out_vars[i][w].varValue == 1
                            for i in self.player_data.index
                        ],
                        index=self.player_data.index,
                    )

                    selected_squad_gw["transfer_in"] = transfer_in_flags.loc[
                        selected_squad_gw.index
                    ]
                    selected_squad_gw["transfer_out"] = transfer_out_flags.loc[
                        selected_squad_gw.index
                    ]

                    transfers_in_gw = int(round(transfer_in_flags.sum()))
                    transfers_out_gw = int(round(transfer_out_flags.sum()))
                    hits_gw = int(round(transfer_hits[w].varValue))
                    self.total_transfer_hits += hits_gw
                else:
                    selected_squad_gw["transfer_in"] = False  # No transfers in for GW0
                    selected_squad_gw["transfer_out"] = (
                        False  # No transfers out for GW0
                    )

                self.selected_squad_history[f"GW{gw_actual}"] = {
                    "squad": selected_squad_gw,
                    "total_cost": selected_squad_gw["cost"].sum(),
                    "expected_points_from_xi": sum(
                        self.player_data.loc[i, "expected_points_by_gw"][gw_actual]
                        * starting_xi_vars[i][w].varValue
                        for i in self.player_data.index
                    ),
                    "bench_boost_used": bool(use_bench_boost[w].varValue),
                    "triple_captain_used": bool(use_triple_captain[w].varValue),
                    "total_bench_boost_points": value(
                        lpSum(
                            actual_bench_boost_points[i][w]
                            for i in self.player_data.index
                        )
                    ),
                    "total_triple_captain_bonus": value(
                        lpSum(
                            actual_triple_captain_bonus[i][w]
                            for i in self.player_data.index
                        )
                    ),
                    "transfers_in_count": transfers_in_gw,
                    "transfers_out_count": transfers_out_gw,
                    "transfer_hits": hits_gw,  # New
                    "free_transfers_available_next_gw": (
                        int(round(free_transfers_available[w].varValue))
                        if w < num_gameweeks - 1
                        else 0
                    ),  # Free transfers available *after* this GW's transfers are made
                }

            # Overall totals
            self.total_cost = self.selected_squad_history[
                f"GW{current_gameweek_number_start + num_gameweeks - 1}"
            ][
                "total_cost"
            ]  # Cost of final squad
            self.total_expected_points = value(
                self.problem.objective
            )  # Total objective value from solver
            self.used_chips = {
                f"GW{current_gameweek_number_start + w}": {
                    "bench_boost": bool(use_bench_boost[w].varValue),
                    "triple_captain": bool(use_triple_captain[w].varValue),
                }
                for w in range(num_gameweeks)
            }

            return True
        else:
            print(f"No optimal solution found. Status: {LpStatus[self.problem.status]}")
            self.selected_squad_history = {}
            self.total_cost = 0
            self.total_expected_points = 0
            self.used_chips = {}
            self.total_transfer_hits = 0
            return False

    def get_selected_squad(self, gameweek: int = None) -> pd.DataFrame | None:
        """
        Returns the selected squad for a specific gameweek (1-indexed).
        If no gameweek is specified, returns the squad for the last optimized gameweek.
        """
        if not self.selected_squad_history:
            return None

        # Get the first GW key to determine the range of available GWs
        first_gw_in_history = min(
            int(k.replace("GW", "")) for k in self.selected_squad_history.keys()
        )
        last_gw_in_history = max(
            int(k.replace("GW", "")) for k in self.selected_squad_history.keys()
        )

        if gameweek is None:
            return self.selected_squad_history[f"GW{last_gw_in_history}"]["squad"]

        if gameweek < first_gw_in_history or gameweek > last_gw_in_history:
            print(
                f"Gameweek {gameweek} is outside the optimized range (GW{first_gw_in_history}-GW{last_gw_in_history})."
            )
            return None

        return self.selected_squad_history.get(f"GW{gameweek}", {}).get("squad")

    def get_total_cost(self, gameweek: int = None) -> float:
        """
        Returns the total cost for a specific gameweek (1-indexed).
        If no gameweek is specified, returns the cost of the squad in the last optimized gameweek.
        """
        if not self.selected_squad_history:
            return 0
        first_gw_in_history = min(
            int(k.replace("GW", "")) for k in self.selected_squad_history.keys()
        )
        last_gw_in_history = max(
            int(k.replace("GW", "")) for k in self.selected_squad_history.keys()
        )

        if gameweek is None:
            return self.selected_squad_history[f"GW{last_gw_in_history}"]["total_cost"]

        if gameweek < first_gw_in_history or gameweek > last_gw_in_history:
            print(
                f"Gameweek {gameweek} is outside the optimized range (GW{first_gw_in_history}-GW{last_gw_in_history})."
            )
            return 0  # Or raise an error

        return self.selected_squad_history.get(f"GW{gameweek}", {}).get("total_cost", 0)

    def get_total_expected_points(self) -> float:
        """
        Returns the overall total expected points across all optimized gameweeks.
        """
        return self.total_expected_points

    def get_gameweek_summary(self, gameweek: int):
        """
        Returns a dictionary summary for a specific gameweek.
        """
        if not self.selected_squad_history:
            return None
        first_gw_in_history = min(
            int(k.replace("GW", "")) for k in self.selected_squad_history.keys()
        )
        last_gw_in_history = max(
            int(k.replace("GW", "")) for k in self.selected_squad_history.keys()
        )

        if gameweek < first_gw_in_history or gameweek > last_gw_in_history:
            print(
                f"Gameweek {gameweek} is outside the optimized range (GW{first_gw_in_history}-GW{last_gw_in_history})."
            )
            return None

        return self.selected_squad_history.get(f"GW{gameweek}")

    def print_squad_summary(self, gameweek: int):
        """
        Prints a formatted summary of the selected squad for a specific gameweek.
        """
        if not self.selected_squad_history:
            print("No squad has been selected yet. Run the 'solve' method first.")
            return

        gw_data = self.get_gameweek_summary(gameweek)
        if not gw_data:
            return  # get_gameweek_summary already prints error message

        selected_squad = gw_data["squad"]
        total_cost = gw_data["total_cost"]
        expected_points_from_xi = gw_data["expected_points_from_xi"]
        bench_boost_used = gw_data["bench_boost_used"]
        triple_captain_used = gw_data["triple_captain_used"]
        total_bench_boost_points = gw_data["total_bench_boost_points"]
        total_triple_captain_bonus = gw_data["total_triple_captain_bonus"]
        transfers_in_count = gw_data["transfers_in_count"]  # New
        transfers_out_count = gw_data["transfers_out_count"]  # New
        transfer_hits_taken = gw_data["transfer_hits"]  # New
        free_transfers_available_next_gw = gw_data[
            "free_transfers_available_next_gw"
        ]  # New

        print(f"\n--- FPL Optimized Squad for Gameweek {gameweek} ---")
        print(f"Squad Cost: £{total_cost:.1f}m")
        print(f"Expected Points (Starting XI): {expected_points_from_xi:.2f}")
        print(
            f"Total Expected Points for GW{gameweek} (including chips): {expected_points_from_xi + total_bench_boost_points + total_triple_captain_bonus:.2f}"
        )
        print("\n--- Chips Used This Gameweek ---")
        if bench_boost_used:
            print(f"- Bench Boost (Added {total_bench_boost_points:.2f} points)")
        if triple_captain_used:
            print(
                f"- Triple Captain (Added {total_triple_captain_bonus:.2f} bonus points)"
            )
        if not (bench_boost_used or triple_captain_used):
            print("No chips used this gameweek.")

        print("\n--- Goalkeepers (Starting XI marked with *) ---")
        for index, row in selected_squad[selected_squad["position"] == "GK"].iterrows():
            starter_str = "*" if row["is_starter"] else ""
            captain_str = "(C)" if row["is_captain"] else ""
            transfer_status = ""
            if row["transfer_in"]:
                transfer_status = "(IN)"
            elif row["transfer_out"]:
                transfer_status = "(OUT)"

            # Access gameweek-specific xP correctly
            player_gw_xp = row["expected_points_by_gw"].get(gameweek, 0.0)
            print(
                f"{starter_str} {row['name']} {captain_str} {transfer_status} ({row['team']}): £{row['cost']:.1f}m, {player_gw_xp} xP"
            )
        print("\n--- Defenders (Starting XI marked with *) ---")
        for index, row in selected_squad[
            selected_squad["position"] == "DEF"
        ].iterrows():
            starter_str = "*" if row["is_starter"] else ""
            captain_str = "(C)" if row["is_captain"] else ""
            transfer_status = ""
            if row["transfer_in"]:
                transfer_status = "(IN)"
            elif row["transfer_out"]:
                transfer_status = "(OUT)"

            player_gw_xp = row["expected_points_by_gw"].get(gameweek, 0.0)
            print(
                f"{starter_str} {row['name']} {captain_str} {transfer_status} ({row['team']}): £{row['cost']:.1f}m, {player_gw_xp} xP"
            )
        print("\n--- Midfielders (Starting XI marked with *) ---")
        for index, row in selected_squad[
            selected_squad["position"] == "MID"
        ].iterrows():
            starter_str = "*" if row["is_starter"] else ""
            captain_str = "(C)" if row["is_captain"] else ""
            transfer_status = ""
            if row["transfer_in"]:
                transfer_status = "(IN)"
            elif row["transfer_out"]:
                transfer_status = "(OUT)"

            player_gw_xp = row["expected_points_by_gw"].get(gameweek, 0.0)
            print(
                f"{starter_str} {row['name']} {captain_str} {transfer_status} ({row['team']}): £{row['cost']:.1f}m, {player_gw_xp} xP"
            )
        print("\n--- Forwards (Starting XI marked with *) ---")
        for index, row in selected_squad[
            selected_squad["position"] == "FWD"
        ].iterrows():
            starter_str = "*" if row["is_starter"] else ""
            captain_str = "(C)" if row["is_captain"] else ""
            transfer_status = ""
            if row["transfer_in"]:
                transfer_status = "(IN)"
            elif row["transfer_out"]:
                transfer_status = "(OUT)"

            player_gw_xp = row["expected_points_by_gw"].get(gameweek, 0.0)
            print(
                f"{starter_str} {row['name']} {captain_str} {transfer_status} ({row['team']}): £{row['cost']:.1f}m, {player_gw_xp} xP"
            )

        print(f"\n--- Team Breakdown for GW{gameweek} ---")
        print(selected_squad["team"].value_counts())

        # Transfers are relevant from Gameweek 2 (index 1) onwards in the optimization horizon
        # For display, if the current GW is the initial one (GW1 in the current context), no transfers are made
        # If it's a subsequent GW, check if transfers occurred.
        first_gw_in_history = min(
            int(k.replace("GW", "")) for k in self.selected_squad_history.keys()
        )
        if (
            gameweek >= first_gw_in_history
        ):  # Changed from > to >=, to show initial free transfers
            # Display transfer info for this gameweek
            print(
                f"  Transfers In: {transfers_in_count}, Transfers Out: {transfers_out_count}"
            )
            print(
                f"  Transfer Hits: {transfer_hits_taken} (-{transfer_hits_taken * POINTS_PER_HIT} points)"
            )
            # Only show free transfers for the *next* gameweek if it's not the last gameweek in the horizon
            if gameweek < max(
                int(k.replace("GW", "")) for k in self.selected_squad_history.keys()
            ):
                print(
                    f"  Free Transfers Available for Next GW: {free_transfers_available_next_gw}"
                )
        print("---------------------------\n")

    def print_overall_summary(self):
        """
        Prints an overall summary of the multi-week optimization results.
        """
        if not self.selected_squad_history:
            print("No optimization results to summarize.")
            return

        print("\n=== Overall Multi-Week FPL Optimization Summary ===")
        print(
            f"Total Expected Points Across All Gameweeks: {self.total_expected_points:.2f}"
        )

        # Get the latest gameweek's cost
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
        # Ensure consistent order by sorting gameweek keys
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

            if chip_summary:
                print(f"{gw_str}: {', '.join(chip_summary)}")
            else:
                print(f"{gw_str}: No chips used")

        print("\n--- Gameweek-by-Gameweek Summary ---")
        # Iterate and print basic summary for each gameweek
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

            # Display transfer info for this gameweek
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
            # Only show free transfers for the *next* gameweek if it's not the last gameweek in the horizon
            if int(gw_str.replace("GW", "")) < max(
                int(k.replace("GW", "")) for k in self.selected_squad_history.keys()
            ):
                print(
                    f"  Free Transfers Available for Next GW: {free_transfers_available_next_gw}"
                )
            print("-----------------------------------")


# End of FPLOptimizer class
