# fpl_xp_predictor.py

import math
import requests
import time
from datetime import datetime

# Import configurations from the new config file
from fpl_config import (
    FPL_POINTS,
    MIN_MINUTES_THRESHOLD,
    VERY_LOW_MINUTES_THRESHOLD,
    YELLOW_CARD_PROB,
    RED_CARD_PROB,
    PENALTY_MISS_PROB,
    OWN_GOAL_PROB,
    DEFAULT_SUB_MINUTES,
    DEFAULT_UNKNOWN_PLAYER_MINUTES,
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

        self.fpl_points = FPL_POINTS

        self.players_data = {}
        self.teams_data = {}
        self.fixtures_data = {}
        self.position_definitions = {
            1: "GK",
            2: "DEF",
            3: "MID",
            4: "FWD",
        }
        self.all_players_xp_calculated_data = (
            []
        )  # To store xP for all players for the optimizer

        self._fetch_fpl_data()
        self._calculate_all_players_xp()  # Calculate xP for all players after data is loaded

    def _fetch_fpl_data(self):
        """Fetches initial data from the FPL API."""
        print("Fetching FPL data...")
        try:
            # Fetch general data
            static_data = requests.get(
                "https://fantasy.premierleague.com/api/bootstrap-static/"
            ).json()
            # Fetch fixtures data
            fixtures_data = requests.get(
                "https://fantasy.premierleague.com/api/fixtures/"
            ).json()

            # Process players data
            for element in static_data["elements"]:
                player_id = element["id"]
                self.players_data[player_id] = {
                    "name": element["first_name"] + " " + element["second_name"],
                    "web_name": element["web_name"],
                    "team_id": element["team"],
                    "element_type": element["element_type"],  # Position ID
                    "position": self.position_definitions.get(
                        element["element_type"], "Unknown"
                    ),
                    "cost_pence": element["now_cost"],
                    "status": element[
                        "status"
                    ],  # E.g., 'a' for available, 'i' for injured
                    "news": element["news"],
                    "total_points": element["total_points"],
                    "minutes": element["minutes"],
                    "goals_scored": element["goals_scored"],
                    "assists": element["assists"],
                    "clean_sheets": element["clean_sheets"],
                    "goals_conceded": element["goals_conceded"],
                    "penalties_saved": element["penalties_saved"],
                    "penalties_missed": element["penalties_missed"],
                    "yellow_cards": element["yellow_cards"],
                    "red_cards": element["red_cards"],
                    "own_goals": element["own_goals"],
                    "saves": element["saves"],
                    "bonus": element["bonus"],
                    "bps": element["bps"],  # Bonus Points System score
                    "threat": element["threat"],
                    "creativity": element["creativity"],
                    "influence": element["influence"],
                    "form": float(element["form"]),  # Player's form
                    "points_per_game": float(element["points_per_game"]),
                    "value_season": float(element["value_season"]),
                    "value_form": float(element["value_form"]),
                    # Additional stats for defensive contribution
                    "ict_index": float(
                        element["ict_index"]
                    ),  # Influence, Creativity, Threat
                }

            # Process teams data
            for team in static_data["teams"]:
                self.teams_data[team["id"]] = {
                    "name": team["name"],
                    "short_name": team["short_name"],
                    "strength": team["strength"],
                    "strength_overall_home": team["strength_overall_home"],
                    "strength_overall_away": team["strength_overall_away"],
                    "strength_attack_home": team["strength_attack_home"],
                    "strength_attack_away": team["strength_attack_away"],
                    "strength_defence_home": team["strength_defence_home"],
                    "strength_defence_away": team["strength_defence_away"],
                }

            # Process fixtures data
            for fixture in fixtures_data:
                self.fixtures_data[fixture["id"]] = fixture

            print("FPL data fetched successfully.")

        except requests.exceptions.RequestException as e:
            print(f"Error fetching FPL data: {e}")
            self.players_data = {}
            self.teams_data = {}
            self.fixtures_data = {}
            print("Initialization failed due to data fetching error. Exiting.")
            sys.exit(1)
        except Exception as e:
            print(f"An unexpected error occurred during data fetching: {e}")
            self.players_data = {}
            self.teams_data = {}
            self.fixtures_data = {}
            print("Initialization failed due to unexpected error. Exiting.")
            sys.exit(1)

    def _get_team_strength(self, team_id, is_home):
        """Get team strength based on home/away status."""
        team = self.teams_data.get(team_id, {})
        if is_home:
            return team.get("strength_overall_home", 1000)  # Default if not found
        return team.get("strength_overall_away", 1000)  # Default if not found

    def _predict_minutes(self, player_id):
        """
        Predicts expected minutes for a player based on historical data.
        More sophisticated logic for handling very low minute players.
        """
        player = self.players_data.get(player_id)
        if not player:
            return 0.0

        status = player["status"]
        news = player["news"].lower()
        minutes_played = player["minutes"]

        # 1. Unavailable players (injured, suspended, doubtful)
        if status != "a" or any(
            x in news
            for x in [
                "injured",
                "doubtful",
                "suspension",
                "red card",
                "expected back",
            ]
        ):
            return 0.0

        # 2. Players with significant minutes (starters/key rotation)
        if minutes_played >= MIN_MINUTES_THRESHOLD:
            # Average minutes per game started (assuming most minutes come from starts)
            # This is a heuristic; real FPL API doesn't give starts directly.
            # We assume a player with > MIN_MINUTES_THRESHOLD plays ~80-90 minutes when on pitch.
            # So, (minutes_played / number_of_appearances) is a rough proxy.
            # For simplicity, let's use a cap of 90 minutes.
            if player["total_points"] > 0:  # Player has played at least one game
                avg_minutes_per_appearance = minutes_played / (
                    player["total_points"] / player["points_per_game"]
                )
                return min(avg_minutes_per_appearance, 90.0)
            return 70.0  # Reasonable default for established player with points but no clear avg

        # 3. Players with very low minutes (rarely play, new, youth)
        if minutes_played < VERY_LOW_MINUTES_THRESHOLD:
            # If news suggests they might get a chance, assign default sub minutes.
            # Otherwise, very low expected minutes or zero.
            if any(x in news for x in ["return imminent", "close to return"]):
                return DEFAULT_SUB_MINUTES  # Might get some minutes
            return DEFAULT_UNKNOWN_PLAYER_MINUTES  # Very unlikely to play significant minutes

        # 4. Players with some minutes but below significant threshold (regular subs)
        return DEFAULT_SUB_MINUTES

    def _calculate_expected_goals(self, team_attack_strength, opp_defence_strength):
        """
        Calculates expected goals for a team based on its attack strength and
        opponent's defensive strength. This is a simplified heuristic.
        """
        # A simple ratio model: Higher attack strength and lower opponent defense means more goals
        # Normalization factor can be adjusted based on average league goals
        expected_goals = (
            team_attack_strength / opp_defence_strength
        ) * 1.5  # 1.5 is an arbitrary scaling factor
        return max(0.0, expected_goals)

    def _calculate_expected_conceded_goals(
        self, team_defence_strength, opp_attack_strength
    ):
        """
        Calculates expected goals conceded by a team based on its defense strength
        and opponent's attacking strength.
        """
        # A simple ratio model: Higher opponent attack and lower team defense means more conceded goals
        expected_conceded_goals = (
            opp_attack_strength / team_defence_strength
        ) * 1.5  # 1.5 is an arbitrary scaling factor
        return max(0.0, expected_conceded_goals)

    def calculate_xp_for_player(self, player_id, fixture_id):
        """
        Calculates Expected Points (xP) for a single player in a given fixture.
        Considers various factors: minutes, goals, assists, clean sheets, saves,
        bonus points, and negative events, adjusted for fixture difficulty.
        """
        player = self.players_data.get(player_id)
        fixture = self.fixtures_data.get(fixture_id)

        if not player or not fixture:
            return {"xp": 0.0, "reason": "Player or fixture data missing."}

        # Handle unavailable players
        if (
            player["status"] != "a"
        ):  # 'd' for doubtful, 'i' for injured, 's' for suspended
            return {"xp": 0.0, "reason": f"Player status: {player['status']}"}
        if any(
            x in player["news"].lower()
            for x in ["injured", "doubtful", "suspension", "red card"]
        ):
            return {"xp": 0.0, "reason": f"Player news: {player['news']}"}

        # Predict minutes
        expected_minutes = self._predict_minutes(player_id)
        if expected_minutes < 1.0:  # If expected to play very little or none
            return {"xp": 0.0, "reason": "Expected minutes too low."}

        xp = 0.0
        position = player["position"]
        # Use 'team_h' for home team ID
        is_home_fixture = player["team_id"] == fixture["team_h"]

        # Determine attacking and defensive strengths for the fixture
        player_team_strength_attack = (
            self.teams_data.get(fixture["team_h"], {}).get(
                "strength_attack_home"
            )  # Use 'team_h'
            if is_home_fixture
            else self.teams_data.get(fixture["team_a"], {}).get(
                "strength_attack_away"
            )  # Use 'team_a'
        )
        player_team_strength_defence = (
            self.teams_data.get(fixture["team_h"], {}).get(
                "strength_defence_home"
            )  # Use 'team_h'
            if is_home_fixture
            else self.teams_data.get(fixture["team_a"], {}).get(
                "strength_defence_away"
            )  # Use 'team_a'
        )
        opponent_team_strength_attack = (
            self.teams_data.get(fixture["team_a"], {}).get(
                "strength_attack_away"
            )  # Use 'team_a'
            if is_home_fixture
            else self.teams_data.get(fixture["team_h"], {}).get(
                "strength_attack_home"
            )  # Use 'team_h'
        )
        opponent_team_strength_defence = (
            self.teams_data.get(fixture["team_a"], {}).get(
                "strength_defence_away"
            )  # Use 'team_a'
            if is_home_fixture
            else self.teams_data.get(fixture["team_h"], {}).get(
                "strength_defence_home"
            )  # Use 'team_h'
        )

        if None in [
            player_team_strength_attack,
            player_team_strength_defence,
            opponent_team_strength_attack,
            opponent_team_strength_defence,
        ]:
            # Fallback if strength data is missing (shouldn't happen with robust data fetch)
            return {"xp": 0.0, "reason": "Team strength data missing for fixture."}

        # 1. Appearance points (scaled by expected minutes)
        xp += (expected_minutes / 90.0) * self.fpl_points["appearance_points"]

        # 2. Expected Goals (scaled by historical goals per 90 and opponent difficulty)
        # Use player's form and total goals as a basis
        goals_per_90_hist = (
            (player["goals_scored"] / player["minutes"] * 90)
            if player["minutes"] > 0
            else 0.0
        )
        expected_team_goals = self._calculate_expected_goals(
            player_team_strength_attack, opponent_team_strength_defence
        )

        expected_goals_player_contribution = (
            (goals_per_90_hist / 90.0) * expected_minutes * (expected_team_goals / 1.5)
        )  # Scale player's goal contribution by team's expected goals

        if position == "GK":
            xp += expected_goals_player_contribution * self.fpl_points["goal_gk"]
        elif position == "DEF":
            xp += expected_goals_player_contribution * self.fpl_points["goal_def"]
        elif position == "MID":
            xp += expected_goals_player_contribution * self.fpl_points["goal_mid"]
        elif position == "FWD":
            xp += expected_goals_player_contribution * self.fpl_points["goal_fwd"]

        # 3. Expected Assists (scaled by historical assists per 90 and opponent difficulty)
        assists_per_90_hist = (
            (player["assists"] / player["minutes"] * 90)
            if player["minutes"] > 0
            else 0.0
        )
        # Assuming team's attacking strength correlates with assist opportunities
        expected_assists_player_contribution = (
            (assists_per_90_hist / 90.0)
            * expected_minutes
            * (expected_team_goals / 1.5)
        )  # Similarly scale by team's expected goals
        xp += expected_assists_player_contribution * self.fpl_points["assist_points"]

        # 4. Expected Clean Sheets (for GKs/DEFs) and Conceded Goals deduction
        expected_conceded = self._calculate_expected_conceded_goals(
            player_team_strength_defence, opponent_team_strength_attack
        )

        if position in ["GK", "DEF"]:
            # Probability of clean sheet
            # Simplified: higher team defense / lower opponent attack -> higher CS prob
            # Use logistic or sigmoid for probability
            cs_prob = 1.0 / (
                1.0 + math.exp(expected_conceded - 1.0)
            )  # Sigmoid centered at 1 goal
            xp += cs_prob * self.fpl_points["clean_sheet_gk_def"]

            # Conceded goals deduction: Apply penalty for every 2 goals conceded *probability*
            # For simplicity, calculate expected deduction: (expected_conceded / 2) * deduction
            xp += (expected_conceded / 2.0) * self.fpl_points[
                "conceded_2_goals_deduction"
            ]

        # 5. Expected Saves (for GKs)
        if position == "GK":
            saves_per_90_hist = (
                (player["saves"] / player["minutes"] * 90)
                if player["minutes"] > 0
                else 0.0
            )
            # Expected saves scaled by opponent's attacking strength (more attacking -> more shots -> more saves)
            expected_saves_player_contribution = (
                (saves_per_90_hist / 90.0)
                * expected_minutes
                * (opponent_team_strength_attack / player_team_strength_defence)
            )
            xp += (
                expected_saves_player_contribution / 3.0
            ) * 1  # 1 point per 3 saves. Assuming 1 point per 3 saves.

            # Penalty saves (low probability, use historical rate)
            penalty_saves_hist_per_game = (
                player["penalties_saved"] / (player["minutes"] / 90.0)
                if player["minutes"] > 0
                else 0.0
            )
            xp += (
                penalty_saves_hist_per_game
                * (expected_minutes / 90.0)
                * self.fpl_points["penalty_save_points"]
            )

        # 6. Expected Bonus Points
        # Use BPS (Bonus Points System) as a proxy. Scale player's average BPS by form and expected minutes.
        bps_per_90_hist = (
            (player["bps"] / player["minutes"] * 90) if player["minutes"] > 0 else 0.0
        )
        expected_bps = (bps_per_90_hist / 90.0) * expected_minutes * player["form"]
        xp += expected_bps * self.fpl_points["bonus_points_scaling_factor"]

        # 7. Minor Negative Events (Probabilistic)
        # These are rare, so a simple probability based on expected minutes.
        xp += (expected_minutes / 90.0) * (
            self.fpl_points["yellow_card_deduction"] * YELLOW_CARD_PROB
            + self.fpl_points["red_card_deduction"] * RED_CARD_PROB
            + self.fpl_points["own_goal_deduction"]
            * OWN_GOAL_PROB  # Ensure own_goal_deduction is in FPL_POINTS
            + self.fpl_points["penalty_miss_deduction"]
            * PENALTY_MISS_PROB  # Ensure penalty_miss_deduction is in FPL_POINTS
        )

        # 8. Defensive Contribution Points (for 2025/26 season heuristic)
        # Assuming CBIT/CBIRT tracking
        if position in ["GK", "DEF"]:
            xp += (
                self.fpl_points["defensive_contribution_prob_def"]
                * self.fpl_points["defensive_contribution_points"]
            )
        elif position in ["MID", "FWD"]:
            xp += (
                self.fpl_points["defensive_contribution_prob_mid_fwd"]
                * self.fpl_points["defensive_contribution_points"]
            )

        return {"xp": round(xp, 2), "reason": "Success"}

    def _calculate_all_players_xp(self):
        """
        Calculates the Expected Points (xP) for all players over multiple upcoming gameweeks
        and populates self.all_players_xp_calculated_data with xP per gameweek.
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
                home_team_code = fixture_data["team_h"]
                away_team_code = fixture_data["team_a"]

                team_fixtures_in_range[home_team_code].append(fixture_id)
                team_fixtures_in_range[away_team_code].append(fixture_id)

        # Calculate total xP for each player across the specified gameweeks
        for player_id, player_data in self.players_data.items():
            player_team_code = player_data["team_id"]
            player_position = player_data["position"]

            # Calculate xP for each relevant fixture and store by gameweek
            expected_points_by_gw = {}
            for fixture_id in team_fixtures_in_range.get(player_team_code, []):
                fixture_gameweek = self.fixtures_data[fixture_id]["event"]
                xp_result_single_gw = self.calculate_xp_for_player(
                    player_id, fixture_id
                )
                if xp_result_single_gw and xp_result_single_gw["xp"] is not None:
                    if fixture_gameweek not in expected_points_by_gw:
                        expected_points_by_gw[fixture_gameweek] = 0.0
                    expected_points_by_gw[fixture_gameweek] += xp_result_single_gw["xp"]

            # Ensure all target gameweeks are present, even if xP is 0 for a given GW
            for gw in target_gameweeks:
                if gw not in expected_points_by_gw:
                    expected_points_by_gw[gw] = 0.0

            # Sort the dictionary by gameweek for consistent output
            expected_points_by_gw = dict(sorted(expected_points_by_gw.items()))

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
                    "position": player_position,
                    "cost": player_cost_m,
                    "expected_points_by_gw": expected_points_by_gw,  # Changed key and format
                }
            )
        print("xP calculation for all players complete.")

    def get_upcoming_fixtures(self, limit=None):
        """
        Returns a list of upcoming fixtures, sorted by gameweek and kickoff time.
        Optionally limits the number of fixtures returned.
        """
        upcoming = []
        now = datetime.now()

        # Sort all fixtures by gameweek and then by kickoff time
        sorted_fixtures = sorted(
            self.fixtures_data.values(),
            key=lambda x: (
                x.get("event", 0),
                x.get("kickoff_time", "9999-12-31T00:00:00Z"),
            ),
        )

        current_gameweek = None
        for fixture_data in sorted_fixtures:
            # Determine current gameweek from the earliest upcoming fixture
            if not fixture_data["finished"] and current_gameweek is None:
                current_gameweek = fixture_data.get("event", 0)

            # Filter for upcoming fixtures within the prediction horizon
            if (
                fixture_data.get("event", 0) < current_gameweek  # Skip past gameweeks
                or fixture_data.get("event", 0)
                >= current_gameweek + self.gameweeks_to_predict
            ):
                continue  # Skip fixtures outside the prediction horizon

            home_team_name = self.teams_data.get(
                fixture_data["team_h"], {}
            ).get(  # Use 'team_h'
                "name", "Unknown"
            )
            away_team_name = self.teams_data.get(
                fixture_data["team_a"], {}
            ).get(  # Use 'team_a'
                "name", "Unknown"
            )

            # Only add fixtures that are not finished
            if not fixture_data["finished"]:
                upcoming.append(
                    {
                        "fixture_id": fixture_data["id"],
                        "gameweek": fixture_data.get("event"),
                        "home_team_id": fixture_data["team_h"],  # Use 'team_h'
                        "away_team_id": fixture_data["team_a"],  # Use 'team_a'
                        "match": f"{home_team_name} vs {away_team_name}",
                        "kickoff_time": fixture_data.get("kickoff_time"),
                        "home_team_difficulty": fixture_data["team_h_difficulty"],
                        "away_team_difficulty": fixture_data["team_a_difficulty"],
                    }
                )
            if limit is not None and len(upcoming) >= limit:
                break
        return upcoming

    def get_players_for_optimizer(self):
        """
        Returns the list of player data with calculated xP per gameweek,
        formatted for the FPLOptimizer.
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

    # Calculate total xP for sorting for display purposes
    for player in all_players_data:
        player["total_expected_points"] = sum(player["expected_points_by_gw"].values())

    all_players_data.sort(key=lambda x: x["total_expected_points"], reverse=True)

    if all_players_data:
        print(f"\nTotal players with calculated xP and cost: {len(all_players_data)}")
        print("Top 20 players by xP (ready for optimizer):")
        for i, player_info in enumerate(all_players_data[:20]):
            xp_by_gw_str = ", ".join(
                [
                    f"GW{gw}: {xp:.2f}"
                    for gw, xp in player_info["expected_points_by_gw"].items()
                ]
            )
            print(
                f"{i+1}. {player_info['name']} ({player_info['position']}, {player_info['team']}): £{player_info['cost']:.1f}m - Total xP: {player_info['total_expected_points']:.2f} (Breakdown: {xp_by_gw_str})"
            )
    else:
        print("No players found with calculated xP.")
