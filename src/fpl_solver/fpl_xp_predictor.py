"""
fpl_xp_predictor.py

A Python module for predicting Expected Points (xP) in Fantasy Premier League (FPL).

This module fetches real player, team, and fixture data from the official
FPL API, calculates xP for all players, and provides the data in a format
suitable for the FPL squad optimizer.

Improvements in this version:
- Expected Saves for Goalkeepers
- More refined Bonus Points proxy using BPS data
- Basic inclusion of minor negative events (yellow/red cards, own goals, penalty misses)
- Consistent position mapping (GKP -> GK)
- Inclusion of Defensive Contribution Points for 2025/26 season (using heuristic probabilities)
- More aggressive regression for players with very low total minutes played.
- Calculates Expected Points over multiple upcoming gameweeks.
- FIX: Corrected KeyError for 'id' when calculating multi-gameweek xP.
- NEW: Integrates Fixture Difficulty Rating (FDR) into strength calculations.
- NEW: More granular Expected Minutes prediction based on historical average minutes per appearance.
- FIX: Corrected typo 'defense_defense_home' to 'defense_strength'.
- NEW: Further refined Expected Minutes logic to better handle very low/zero minute players.
- NEW: Configurations moved to fpl_config.py.
"""

import math
import requests
import time
from datetime import datetime

# Import configurations from the new config file
from fpl_config import (
    FPL_POINTS,
    MIN_MINUTES_THRESHOLD,  # Imported from config
    VERY_LOW_MINUTES_THRESHOLD,  # Imported from config
    YELLOW_CARD_PROB,  # Imported from config
    RED_CARD_PROB,  # Imported from config
    PENALTY_MISS_PROB,  # Imported from config
    OWN_GOAL_PROB,  # Imported from config
    DEFAULT_SUB_MINUTES,  # Imported from config
    DEFAULT_UNKNOWN_PLAYER_MINUTES,  # Imported from config
)


class FPLPredictor:
    """
    Predictive algorithm for Expected Points (xP) in Fantasy Premier League,
    using real data from the FPL API.
    """

    def __init__(self, gameweeks_to_predict: int = 1):
        """
        Initializes the FPLPredictor with default FPL point rules and
        data structures, then fetches real data and calculates xP for all players.

        Args:
            gameweeks_to_predict (int): The number of upcoming gameweeks to calculate
                                        expected points for. Default is 1 (next gameweek).
        """
        if not isinstance(gameweeks_to_predict, int) or gameweeks_to_predict < 1:
            raise ValueError("gameweeks_to_predict must be a positive integer.")
        self.gameweeks_to_predict = gameweeks_to_predict

        # FPL Point System is now loaded from fpl_config.py
        self.fpl_points = FPL_POINTS

        self.players_data = {}
        self.teams_data = {}
        self.fixtures_data = {}
        self.position_map = {}  # To map element_type ID to position string
        self.team_id_to_code_map = {}  # To map team ID to team code (for fixtures)
        self.all_players_xp_calculated_data = []  # Stores processed data for the solver

        self._fetch_fpl_data()
        self._calculate_all_players_xp()  # Calculate xP for all players after data is loaded

    def _fetch_api_data(self, url, max_retries=5, backoff_factor=1.0):
        """
        Fetches data from a given URL with exponential backoff for retries.

        Args:
            url (str): The URL to fetch data from.
            max_retries (int): Maximum number of retries.
            backoff_factor (float): Factor by which to increase delay between retries.

        Returns:
            dict or None: JSON response if successful, None otherwise.
        """
        for i in range(max_retries):
            try:
                response = requests.get(url)
                response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
                return response.json()
            except requests.exceptions.RequestException as e:
                print(f"Error fetching {url}: {e}")
                if i < max_retries - 1:
                    wait_time = backoff_factor * (2**i)
                    print(f"Retrying in {wait_time:.2f} seconds...")
                    time.sleep(wait_time)
                else:
                    print(f"Max retries reached for {url}. Giving up.")
                    return None

    def _fetch_fpl_data(self):
        """
        Fetches real player, team, and fixture data from the FPL API.
        """
        print("Fetching real FPL data from API...")
        bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
        fixtures_url = "https://fantasy.premierleague.com/api/fixtures/"

        bootstrap_data = self._fetch_api_data(bootstrap_url)
        all_fixtures_data = self._fetch_api_data(fixtures_url)

        if not bootstrap_data or not all_fixtures_data:
            print("Failed to fetch essential FPL data. Using empty data structures.")
            return

        # --- Process Team Data ---
        for team in bootstrap_data.get("teams", []):
            team_id = team["id"]
            team_code = team["code"]
            clean_sheets = team.get("clean_sheets", 0)
            played_matches = team.get("played", 0)

            self.teams_data[team_code] = {
                "name": team["name"],
                "attack_strength": team["strength_attack_home"],
                "defense_strength": team["strength_defence_home"],
                "clean_sheet_rate": clean_sheets / max(1, played_matches),
                "team_id_fpl": team_id,
            }
            self.team_id_to_code_map[team_id] = team_code

        # --- Process Position Data ---
        for element_type in bootstrap_data.get("element_types", []):
            pos_name = element_type["singular_name_short"]
            # Map 'GKP' to 'GK' for consistency with solver
            if pos_name == "GKP":
                self.position_map[element_type["id"]] = "GK"
            else:
                self.position_map[element_type["id"]] = pos_name

        # --- Process Player Data ---
        for player in bootstrap_data.get("elements", []):
            player_id = str(player["id"])
            team_code = self.team_id_to_code_map.get(player["team"])
            position_short = self.position_map.get(player["element_type"], "N/A")

            if not team_code:
                continue

            minutes_played = player.get("minutes", 0)
            starts = player.get("starts", 0)  # Number of starts

            # Initialize per-90 stats
            goals_per_90 = 0.0
            assists_per_90 = 0.0
            saves_per_90 = 0.0  # For Goalkeepers
            bps_per_90 = 0.0  # For Bonus Points System score

            if minutes_played >= MIN_MINUTES_THRESHOLD:
                # Use raw per-90 stats for players with sufficient minutes
                goals_per_90 = player.get("goals_scored", 0) / (minutes_played / 90.0)
                assists_per_90 = player.get("assists", 0) / (minutes_played / 90.0)
                saves_per_90 = player.get("saves", 0) / (minutes_played / 90.0)
                bps_per_90 = player.get("bps", 0) / (minutes_played / 90.0)
            elif minutes_played > VERY_LOW_MINUTES_THRESHOLD:
                # For players with some minutes but below MIN_MINUTES_THRESHOLD,
                # apply a significant regression to their per-90 stats.
                raw_goals_per_90 = player.get("goals_scored", 0) / (
                    minutes_played / 90.0
                )
                raw_assists_per_90 = player.get("assists", 0) / (minutes_played / 90.0)
                raw_saves_per_90 = player.get("saves", 0) / (minutes_played / 90.0)
                raw_bps_per_90 = player.get("bps", 0) / (minutes_played / 90.0)

                goals_per_90 = min(0.1, raw_goals_per_90 * 0.1)
                assists_per_90 = min(0.1, raw_assists_per_90 * 0.1)
                saves_per_90 = min(0.5, raw_saves_per_90 * 0.1)
                bps_per_90 = min(5.0, raw_bps_per_90 * 0.1)
            else:  # minutes_played <= VERY_LOW_MINUTES_THRESHOLD (or 0)
                # For players with very few minutes, effectively zero out their per-90 contributions.
                # This prevents inflated xP from extremely limited appearances.
                goals_per_90 = 0.0
                assists_per_90 = 0.0
                saves_per_90 = 0.0
                bps_per_90 = 0.0

            # --- More Granular Expected Minutes Prediction ---
            expected_minutes = 0.0  # Default to 0 for all players initially

            # If a player has played 0 minutes, their expected minutes should stay 0.
            # This handles the case of backup players who are fit but don't play.
            if minutes_played == 0:
                expected_minutes = 0.0
            else:
                # Calculate average minutes per start if they have started games
                if starts > 0:
                    avg_minutes_per_start = minutes_played / starts
                    # Cap average minutes per start at 90 to prevent absurd values from very few starts
                    avg_minutes_per_start = min(90.0, avg_minutes_per_start)
                else:
                    # If player has minutes but no starts, they are likely a sub.
                    # Assign a lower default average minutes for subs.
                    avg_minutes_per_start = DEFAULT_SUB_MINUTES  # Now uses config value

                chance_playing = player.get("chance_of_playing_next_round")

                if chance_playing is not None:
                    if chance_playing == 0:
                        expected_minutes = 0.0
                    elif chance_playing < 100:
                        # Scale their average minutes by their chance of playing
                        expected_minutes = avg_minutes_per_start * (
                            chance_playing / 100.0
                        )
                    else:  # chance_playing == 100
                        # If 100% chance and they have historical minutes/starts, use that average.
                        # Fallback to DEFAULT_UNKNOWN_PLAYER_MINUTES if avg_minutes_per_start is 0
                        expected_minutes = (
                            avg_minutes_per_start
                            if avg_minutes_per_start > 0
                            else DEFAULT_UNKNOWN_PLAYER_MINUTES  # Now uses config value
                        )
                else:  # If chance_of_playing_next_round is None, assume 90 minutes (regular starter default)
                    # Fallback to DEFAULT_UNKNOWN_PLAYER_MINUTES if avg_minutes_per_start is 0
                    expected_minutes = (
                        avg_minutes_per_start
                        if avg_minutes_per_start > 0
                        else DEFAULT_UNKNOWN_PLAYER_MINUTES  # Now uses config value
                    )

            # Ensure expected_minutes doesn't exceed 90 or go negative
            expected_minutes = max(0.0, min(90.0, expected_minutes))

            self.players_data[player_id] = {
                "name": f"{player['first_name']} {player['second_name']}",
                "web_name": player["web_name"],
                "team_id": team_code,
                "position": position_short,
                "goals_per_90": goals_per_90,
                "assists_per_90": assists_per_90,
                "saves_per_90": saves_per_90,  # Added for GKs
                "bps_per_90": bps_per_90,  # Added for bonus points proxy
                "expected_minutes": expected_minutes,  # Updated with granular logic
                "form": float(player.get("form", 0.0)),
                "status": player.get("status", "a"),
                "cost_pence": player.get("now_cost", 0),
            }

        # --- Process Fixture Data ---
        for fixture in all_fixtures_data:
            fixture_id = str(fixture["id"])
            home_team_fpl_id = fixture["team_h"]
            away_team_fpl_id = fixture["team_a"]

            home_team_code = self.team_id_to_code_map.get(home_team_fpl_id)
            away_team_code = self.team_id_to_code_map.get(away_team_fpl_id)

            if not home_team_code or not away_team_code:
                continue

            self.fixtures_data[fixture_id] = {
                "home_team_id": home_team_code,
                "away_team_id": away_team_code,
                "home_advantage_factor": 1.1,
                "kickoff_time": fixture["kickoff_time"],
                "event": fixture["event"],  # Gameweek ID
                "finished": fixture["finished"],  # Keep finished status
                "home_team_difficulty": fixture[
                    "team_h_difficulty"
                ],
                "away_team_difficulty": fixture[
                    "team_a_difficulty"
                ],
            }
        print("Real FPL data loaded successfully.")

    def _get_team_strength_factors(
        self, team_id_code, opponent_id_code, is_home, fixture_data
    ):
        """
        Calculates adjusted attack and defense strength factors for a team
        considering the opponent, home/away advantage, and Fixture Difficulty Rating (FDR).

        Args:
            team_id_code (str): The code of the team (e.g., "LIV").
            opponent_id_code (str): The code of the opponent team.
            is_home (bool): True if the team is playing at home, False otherwise.
            fixture_data (dict): The specific fixture's data, including difficulty ratings.

        Returns:
            tuple: (adjusted_attack_strength, adjusted_defense_strength,
                    opponent_attack_strength, opponent_defense_strength)
        """
        team = self.teams_data.get(team_id_code)
        opponent = self.teams_data.get(opponent_id_code)

        if not team or not opponent:
            return 1.0, 1.0, 1.0, 1.0

        player_team_attack_strength = team["attack_strength"]
        player_team_defense_strength = team["defense_strength"]

        opponent_attack_strength = opponent["attack_strength"]
        opponent_defense_strength = opponent["defense_strength"]

        # Get FDR for the teams in this specific fixture
        player_team_fdr = (
            fixture_data["home_team_difficulty"]
            if is_home
            else fixture_data["away_team_difficulty"]
        )
        opponent_fdr = (
            fixture_data["away_team_difficulty"]
            if is_home
            else fixture_data["home_team_difficulty"]
        )

        # Example scaling factor based on FDR:
        # A base of 1.0, adjusted by (FDR - 3) * 0.1 (3 is average difficulty)
        # So, FDR 1 -> 1.0 - 0.2 = 0.8 (easier)
        # FDR 3 -> 1.0 (average)
        # FDR 5 -> 1.0 + 0.2 = 1.2 (harder)

        # Adjust player team's attack strength based on opponent's FDR
        # Higher opponent FDR means harder to score, so decrease attack strength
        attack_fdr_adjustment = 1.0 - ((opponent_fdr - 3) * 0.1)
        adjusted_player_team_attack = (
            player_team_attack_strength * attack_fdr_adjustment
        )

        # Adjust player team's defense strength based on opponent's FDR
        # Higher opponent FDR means harder for opponent to score, so increase player team defense strength
        defense_fdr_adjustment = 1.0 + ((opponent_fdr - 3) * 0.1)
        adjusted_player_team_defense = (
            player_team_defense_strength * defense_fdr_adjustment
        )

        # Adjust opponent's attack strength based on player team's FDR
        # Higher player team FDR means easier for opponent to score, so increase opponent attack strength
        opponent_attack_fdr_adjustment = 1.0 + ((player_team_fdr - 3) * 0.1)
        adjusted_opponent_attack = (
            opponent_attack_strength * opponent_attack_fdr_adjustment
        )

        # Adjust opponent's defense strength based on player team's FDR
        # Higher player team FDR means harder for opponent to concede, so decrease opponent defense strength
        opponent_defense_fdr_adjustment = 1.0 - ((player_team_fdr - 3) * 0.1)
        adjusted_opponent_defense = (
            opponent_defense_strength * opponent_defense_fdr_adjustment
        )

        # Apply home advantage factor (if applicable to this fixture)
        fixture_factor = (
            fixture_data["home_advantage_factor"]
            if is_home
            else (1 / fixture_data["home_advantage_factor"])
        )

        # Combine FPL's internal strength, FDR adjustment, and home advantage
        adjusted_player_team_attack *= fixture_factor
        adjusted_player_team_defense *= fixture_factor
        adjusted_opponent_attack *= (
            1 / fixture_factor
        )  # Opponent's attack is harder if they are home
        adjusted_opponent_defense *= (
            1 / fixture_factor
        )  # Opponent's defense is harder if they are home

        return (
            adjusted_player_team_attack,
            adjusted_player_team_defense,
            adjusted_opponent_attack,
            adjusted_opponent_defense,
        )

    def calculate_xp_for_player(self, player_id, fixture_id):
        """
        Calculates the Expected Points (xP) for a single player in a given fixture.
        """
        player = self.players_data.get(player_id)
        fixture = self.fixtures_data.get(fixture_id)

        if not player or not fixture:
            return None

        player_name = player["name"]
        player_position = player["position"]
        player_team_code = player["team_id"]
        expected_minutes = player.get("expected_minutes", 0)
        player_status = player.get("status", "a")

        if expected_minutes < 1 or player_status in ["i", "s", "n"]:
            return {
                "name": player_name,
                "position": player_position,
                "xp": 0.0,
                "status": player_status,
            }

        is_home_team = player_team_code == fixture["home_team_id"]
        opponent_team_code = (
            fixture["away_team_id"] if is_home_team else fixture["home_team_id"]
        )

        player_team = self.teams_data.get(player_team_code)
        opponent_team = self.teams_data.get(opponent_team_code)

        if not player_team or not opponent_team:
            return None

        # Pass the full fixture_data to get_team_strength_factors for FDR
        (
            player_team_attack_strength,
            player_team_defense_strength,
            opponent_attack_strength,
            opponent_defense_strength,
        ) = self._get_team_strength_factors(
            player_team_code, opponent_team_code, is_home_team, fixture
        )

        xp = 0.0

        # 1. Appearance Points (2 points for playing, 1 extra for 60+ mins)
        xp += self.fpl_points["appearance_points"]  # For playing any minutes

        # Simple proxy for 60+ minutes: if expected_minutes is high, assume 60+
        # This is a heuristic; a more advanced model would use probability of playing 60+
        if expected_minutes >= 60:
            xp += 1  # Additional point for playing 60+ minutes

        # 2. Goal Probability and Points
        goal_probability_factor = (
            player_team_attack_strength / opponent_defense_strength
        )
        goal_probability = (
            player["goals_per_90"] * (expected_minutes / 90.0) * goal_probability_factor
        )
        goal_probability = min(1.0, goal_probability)

        goal_points = 0
        if player_position == "GK":
            goal_points = self.fpl_points["goal_gk"]
        elif player_position == "DEF":
            goal_points = self.fpl_points["goal_def"]
        elif player_position == "MID":
            goal_points = self.fpl_points["goal_mid"]
        elif player_position == "FWD":
            goal_points = self.fpl_points["goal_fwd"]
        xp += goal_probability * goal_points

        # 3. Assist Probability and Points
        assist_probability_factor = (
            player_team_attack_strength / opponent_defense_strength
        ) * 0.8
        assist_probability = (
            player["assists_per_90"]
            * (expected_minutes / 90.0)
            * assist_probability_factor
        )
        assist_probability = min(1.0, assist_probability)
        xp += assist_probability * self.fpl_points["assist_points"]

        # 4. Clean Sheet Points & Goals Conceded (for GK and DEF only)
        if player_position in ["GK", "DEF"]:
            clean_sheet_probability_factor = (
                player_team_defense_strength / opponent_attack_strength
            )
            clean_sheet_probability = (
                player_team["clean_sheet_rate"] * clean_sheet_probability_factor
            )
            clean_sheet_probability = min(1.0, clean_sheet_probability)

            xp += clean_sheet_probability * self.fpl_points["clean_sheet_gk_def"]

            expected_goals_conceded = (
                (opponent_attack_strength / player_team_defense_strength)
                * (expected_minutes / 90.0)
                * 0.5
            )

            deduction_increments = math.floor(expected_goals_conceded / 2)
            xp += deduction_increments * self.fpl_points["conceded_2_goals_deduction"]

        # 5. Goalkeeper Saves Points (for GK only)
        if player_position == "GK":
            # Expected saves: influenced by GK's saves_per_90, expected minutes,
            # and opponent's attack strength relative to player team's defense strength.
            expected_saves_factor = (
                opponent_attack_strength / player_team_defense_strength
            )
            expected_saves = (
                player.get("saves_per_90", 0.0)
                * (expected_minutes / 90.0)
                * expected_saves_factor
            )

            # FPL: 1 point for every 3 saves
            xp += math.floor(expected_saves / 3) * 1

        # 6. Bonus Points (using BPS as a proxy)
        # BPS score is a more granular measure of a player's all-round performance.
        # We'll use bps_per_90 scaled by expected minutes, then apply a factor.
        expected_bps_score = player.get("bps_per_90", 0.0) * (expected_minutes / 90.0)

        # A simple linear scaling of expected BPS score to expected bonus points.
        # This is still a proxy, as actual bonus points are awarded to top 3 BPS scorers in a match.
        bonus_xp = min(
            3.0, expected_bps_score * self.fpl_points["bonus_points_scaling_factor"]
        )  # Cap at 3 bonus points
        xp += bonus_xp

        # 7. Minor Negative Events (simple probabilities)
        # These are very rough estimates and would ideally be data-driven or more complex.
        # Probabilities are now loaded from fpl_config.py

        # Yellow Card
        xp += YELLOW_CARD_PROB * self.fpl_points["yellow_card_deduction"]

        # Red Card (very rare, significant deduction)
        xp += RED_CARD_PROB * self.fpl_points["red_card_deduction"]

        # Penalty Miss (for attacking players: MID, FWD)
        if player_position in ["MID", "FWD"]:
            # This assumes they get a penalty and then miss it. Very simplified.
            xp += (
                PENALTY_MISS_PROB * self.fpl_points["goal_fwd"] * -1
            )  # Deduct points equal to a goal (negative)

        # Own Goal (for GK/DEF)
        if player_position in ["GK", "DEF"]:
            # This assumes they score an own goal. Very simplified.
            xp += (
                OWN_GOAL_PROB * self.fpl_points["goal_def"] * -1
            )  # Deduct points equal to a goal (negative)

        # 8. Defensive Contribution Points (NEW for 2025/26 season)
        # This is a simplified model due to lack of granular CBIT/CBIRT data from FPL API.
        # We use a heuristic probability based on position and expected minutes.
        defensive_contribution_xp = 0.0
        if player_position in ["GK", "DEF"]:
            # Defenders/GKs need 10 CBITs for 2 points
            dc_prob = self.fpl_points["defensive_contribution_prob_def"] * (
                expected_minutes / 90.0
            )
            defensive_contribution_xp = (
                min(1.0, dc_prob) * self.fpl_points["defensive_contribution_points"]
            )
        elif player_position in ["MID", "FWD"]:
            # Midfielders/Forwards need 12 CBIRTs for 2 points
            dc_prob = self.fpl_points["defensive_contribution_prob_mid_fwd"] * (
                expected_minutes / 90.0
            )
            defensive_contribution_xp = (
                min(1.0, dc_prob) * self.fpl_points["defensive_contribution_points"]
            )
        xp += defensive_contribution_xp

        xp = round(xp, 2)

        return {
            "name": player_name,
            "position": player_position,
            "xp": xp,
            "status": player_status,
        }

    def _calculate_all_players_xp(self):
        """
        Calculates the Expected Points (xP) for all players for their next upcoming fixture
        and populates self.all_players_xp_calculated_data.
        """
        print(
            f"Calculating xP for all players over {self.gameweeks_to_predict} gameweek(s)..."
        )

        # Get all upcoming fixtures and sort them by gameweek
        all_upcoming_fixtures_items = sorted(
            [
                (fid, fdict)
                for fid, fdict in self.fixtures_data.items()
                if not fdict["finished"]
            ],
            key=lambda item: item[1]["event"],
        )

        if not all_upcoming_fixtures_items:
            print("No upcoming fixtures found. Cannot calculate xP.")
            return

        # Determine the current gameweek (the gameweek of the earliest upcoming fixture)
        current_gameweek = all_upcoming_fixtures_items[0][1]["event"]
        target_gameweeks = range(
            current_gameweek, current_gameweek + self.gameweeks_to_predict
        )

        # Create a mapping of team_id_code to a list of their fixtures within the target gameweeks
        team_fixtures_in_range = {team_code: [] for team_code in self.teams_data.keys()}
        for fixture_id, fixture_data in all_upcoming_fixtures_items:
            if fixture_data["event"] in target_gameweeks:
                home_team_code = fixture_data["home_team_id"]
                away_team_code = fixture_data["away_team_id"]

                team_fixtures_in_range[home_team_code].append(fixture_id)
                team_fixtures_in_range[away_team_code].append(fixture_id)

        # Calculate total xP for each player across the specified gameweeks
        for player_id, player_data in self.players_data.items():
            player_team_code = player_data["team_id"]

            total_xp_for_player = 0.0

            # Get fixtures for the player's team in the target gameweeks
            relevant_fixture_ids = team_fixtures_in_range.get(player_team_code, [])

            # Calculate xP for each relevant fixture and sum them up
            for fixture_id in relevant_fixture_ids:
                xp_result_single_gw = self.calculate_xp_for_player(
                    player_id, fixture_id
                )
                if xp_result_single_gw:
                    total_xp_for_player += xp_result_single_gw["xp"]

            # If no relevant fixtures (e.g., team has no games in the next X GWs), xP remains 0.0

            # Prepare data for the optimizer
            player_cost_m = player_data["cost_pence"] / 10.0
            team_name_full = self.teams_data.get(player_team_code, {}).get(
                "name", "Unknown Team"
            )

            self.all_players_xp_calculated_data.append(
                {
                    "name": player_data["name"],
                    "web_name": player_data["web_name"],
                    "team": team_name_full,
                    "position": player_data["position"],
                    "cost": player_cost_m,
                    "expected_points": round(total_xp_for_player, 2),
                }
            )
        print("xP calculation for all players complete.")

    def get_upcoming_fixtures(self, limit=None):
        """
        Returns a list of upcoming fixtures.
        """
        upcoming = []
        # Filter for truly upcoming fixtures (not finished) and sort by gameweek and kickoff time
        sorted_fixtures = sorted(
            [f for f in self.fixtures_data.values() if not f["finished"]],
            key=lambda item: (item.get("event", 999), item.get("kickoff_time", "")),
        )

        for fixture_data in sorted_fixtures:
            fixture_id = str(fixture_data["id"])
            home_team_name = self.teams_data.get(fixture_data["home_team_id"], {}).get(
                "name", "Unknown"
            )
            away_team_name = self.teams_data.get(fixture_data["away_team_id"], {}).get(
                "name", "Unknown"
            )
            upcoming.append(
                {
                    "fixture_id": fixture_id,
                    "gameweek": fixture_data.get("event"),
                    "home_team_id": fixture_data["home_team_id"],
                    "away_team_id": fixture_data["away_team_id"],
                    "match": f"{home_team_name} vs {away_team_name}",
                    "kickoff_time": fixture_data.get("kickoff_time"),
                }
            )
            if limit is not None and len(upcoming) >= limit:
                break
        return upcoming

    def get_players_for_optimizer(self):
        """
        Returns the list of player data with calculated xP, formatted for the FPLOptimizer.
        """
        return self.all_players_xp_calculated_data


# Example Usage (for testing this module independently if needed)
if __name__ == "__main__":
    predictor = FPLPredictor(gameweeks_to_predict=3)

    print("\n--- Upcoming Fixtures ---")
    upcoming_fixtures = predictor.get_upcoming_fixtures(limit=5)
    if upcoming_fixtures:
        for i, fixture in enumerate(upcoming_fixtures):
            print(
                f"{i+1}. GW{fixture['gameweek']}: {fixture['match']} (ID: {fixture['fixture_id']})"
            )
    else:
        print("No upcoming fixtures found or failed to load fixtures.")

    print(
        f"\n--- Calculated xP for Players (Top 20 over {predictor.gameweeks_to_predict} GWs) ---"
    )
    all_players_data = predictor.get_players_for_optimizer()
    all_players_data.sort(key=lambda x: x["expected_points"], reverse=True)

    if all_players_data:
        print(f"\nTotal players with calculated xP and cost: {len(all_players_data)}")
        print("Top 20 players by xP (ready for optimizer):")
        for i, player_info in enumerate(all_players_data[:20]):
            print(
                f"{i+1}. {player_info['name']} ({player_info['position']}, {player_info['team']}): £{player_info['cost']:.1f}m, {player_info['expected_points']} xP"
            )
    else:
        print("No player data with xP could be prepared for the optimizer.")
