import json
from collections import defaultdict
from pathlib import Path


class StatsDashboard:
    def __init__(self, filename: str = "hand_history.jsonl"):
        self.filepath = Path(filename)

    def load_hands(self) -> list:
        if not self.filepath.exists():
            return []

        hands = []

        with self.filepath.open("r", encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    hands.append(json.loads(line))

        return hands

    def calculate_stats(self) -> dict:
        hands = self.load_hands()

        stats = defaultdict(lambda: {
            "hands_played": 0,
            "hands_won": 0,
            "total_winnings": 0,
            "folds": 0,
            "calls": 0,
            "raises": 0,
            "checks": 0,
            "bets": 0,
            "small_blinds": 0,
            "big_blinds": 0,
        })

        action_map = {
            "fold": "folds",
            "call": "calls",
            "raise": "raises",
            "check": "checks",
            "bet": "bets",
            "small_blind": "small_blinds",
            "big_blind": "big_blinds",
        }

        for hand in hands:
            pot = hand.get("pot", 0)
            winners = hand.get("winners", [])

            for player in hand.get("players", []):
                name = player["name"]
                stats[name]["hands_played"] += 1

            if winners:
                winnings_per_player = pot / len(winners)

                for winner in winners:
                    stats[winner]["hands_won"] += 1
                    stats[winner]["total_winnings"] += winnings_per_player

            for action in hand.get("actions", []):
                player_name = action["player"]
                action_name = action["action"]

                if action_name in action_map:
                    stat_name = action_map[action_name]
                    stats[player_name][stat_name] += 1

        return stats

    def print_dashboard(self) -> None:
        stats = self.calculate_stats()

        if not stats:
            print("No hand history found yet.")
            return

        print()
        print("=== Poker Stats Dashboard ===")
        print()

        for player_name, data in stats.items():
            hands_played = data["hands_played"]
            hands_won = data["hands_won"]

            if hands_played > 0:
                win_rate = hands_won / hands_played * 100
            else:
                win_rate = 0

            print(f"Player: {player_name}")
            print(f"  Hands played:   {hands_played}")
            print(f"  Hands won:      {hands_won}")
            print(f"  Win rate:       {win_rate:.1f}%")
            print(f"  Total winnings: {data['total_winnings']}")
            print(f"  Folds:          {data['folds']}")
            print(f"  Calls:          {data['calls']}")
            print(f"  Raises:         {data['raises']}")
            print(f"  Checks:         {data['checks']}")
            print(f"  Bets:           {data['bets']}")
            print(f"  Small blinds:   {data['small_blinds']}")
            print(f"  Big blinds:     {data['big_blinds']}")
            print()