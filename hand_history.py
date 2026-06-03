import json
from datetime import datetime
from pathlib import Path


class HandHistoryLogger:
    def __init__(self, filename: str = "hand_history.jsonl"):
        self.filepath = Path(filename)
        self.current_hand = None

    def start_hand(self, hand_number: int, players: list):
        self.current_hand = {
            "hand_number": hand_number,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "players": [
                {
                    "name": player.name,
                    "starting_chips": player.chips,
                }
                for player in players
            ],
            "actions": [],
            "community_cards": [],
            "winners": [],
            "pot": 0,
        }

    def log_action(self, player_name: str, action: str, amount: int = 0, street: str = "preflop"):
        if self.current_hand is None:
            return

        self.current_hand["actions"].append({
            "street": street,
            "player": player_name,
            "action": action,
            "amount": amount,
            "time": datetime.now().isoformat(timespec="seconds"),
        })

    def log_community_cards(self, street: str, cards: list):
        if self.current_hand is None:
            return

        self.current_hand["community_cards"].append({
            "street": street,
            "cards": [str(card) for card in cards],
        })

    def finish_hand(self, winners: list, pot: int):
        if self.current_hand is None:
            return

        self.current_hand["winners"] = winners
        self.current_hand["pot"] = pot

        # Per-table logs live in a subdirectory (e.g. hand_histories/<id>.jsonl);
        # make sure it exists before the first append.
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        with self.filepath.open("a", encoding="utf-8") as file:
            file.write(json.dumps(self.current_hand) + "\n")

        self.current_hand = None