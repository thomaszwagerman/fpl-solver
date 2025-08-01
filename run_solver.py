"""
Entry point script for running the FPL Solver.
This script should be run from the command line.
"""

import pandas as pd
from fpl_solver.solver import FPLOptimizer
from fpl_solver.xp_predictor import FPLPredictor
from fpl_solver.config import (
    OPTIMIZATION_GAMEWEEKS,
    BUDGET,
    MAX_PLAYERS_PER_TEAM,
    CHIP_ALLOWANCES,
)

def main():
    """Run the FPL Solver with configured settings."""
    print("Initializing FPL Predictor to fetch data and calculate xP...")
    predictor = FPLPredictor(gameweeks_to_predict=OPTIMIZATION_GAMEWEEKS)
    
    print("Getting player data for optimizer...")
    player_data_list = predictor.get_players_for_optimizer()
    
    print("Converting player data to DataFrame...")
    player_data_df = pd.DataFrame(player_data_list)
    
    print("Initializing and running optimizer...")
    optimizer = FPLOptimizer(player_data=player_data_df)
    
    # Solve the optimization problem
    if optimizer.solve(
        budget=BUDGET,
        max_players_per_team=MAX_PLAYERS_PER_TEAM,
        chip_allowances=CHIP_ALLOWANCES,
        num_gameweeks=OPTIMIZATION_GAMEWEEKS
    ):
        print("\nOptimal solution found! Printing summary...")
        optimizer.print_overall_summary()

        # Get the range of gameweeks optimized over from the history
        if optimizer.selected_squad_history:
            first_gw = min(
                int(k.replace("GW", ""))
                for k in optimizer.selected_squad_history.keys()
            )
            last_gw = max(
                int(k.replace("GW", ""))
                for k in optimizer.selected_squad_history.keys()
            )
            print("\n--- Detailed Squad Summary for Each Optimized Gameweek ---")
            for gw_num in range(first_gw, last_gw + 1):
                optimizer.print_squad_summary(gameweek=gw_num)
        else:
            print("\nNo detailed per-gameweek summary available as no optimal solution was found.")
    else:
        print("\nCould not find an optimal FPL squad with the given parameters.")
        print("Consider adjusting the settings in fpl_config.py:")
        print("- BUDGET")
        print("- MAX_PLAYERS_PER_TEAM")
        print("- CHIP_ALLOWANCES")
        print("- OPTIMIZATION_GAMEWEEKS")
        print("Also, check that enough eligible players are available in each position category.")

if __name__ == "__main__":
    main()
