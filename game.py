"""Main Texas Hold'em game loop."""

from __future__ import annotations

from cards import Deck
from evaluator import HandEvaluator
from player import Player
from table import Table
from ui import ConsoleUI


class TexasHoldemGame:
    def __init__(self, players: list[Player], small_blind: int = 5, big_blind: int = 10) -> None:
        if len(players) < 2:
            raise ValueError("There must be at least 2 players to start the game.")
        self.players = players
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.table = Table()
        self.evaluator = HandEvaluator()
        self.ui = ConsoleUI()

    def play_hand(self) -> None:
        deck = Deck()
        self.table.reset()
        
        for player in self.players:
            player.reset_for_hand()
        for player in self.players:
            hole_cards = deck.draw(2)
            player.receive(hole_cards)
        self._post_blinds()
        self._show_human_cards()
        self._betting_round("Pre-Flop")
        self._deal_community(deck, 3, "Flop")
        self._betting_round("Flop")
        self._deal_community(deck, 1, "Turn")
        self._betting_round("Turn")
        self._deal_community(deck, 1, "River")
        self._betting_round("River")
        self._showdown()

    def _post_blinds(self) -> None:
        if len(self.players) < 2:
            raise ValueError("There must be at least 2 players to post blinds.")
        self.players[0].bet(self.small_blind)
        self.players[1].bet(self.big_blind)
        self.table.pot += self.small_blind + self.big_blind
        print(f"{self.players[0].name} posts {self.small_blind}; {self.players[1].name} posts {self.big_blind}")
        print()  # Add an extra line for better readability        

    def _show_human_cards(self) -> None:
        for player in self.players:
            if player.is_human:
                self.ui.show_player(player)
                print()  # Add an extra line for better readability

    def _deal_community(self, deck: Deck, count: int, street: str) -> None:
        if self._only_one_player_left():
            return
        new_cards = deck.draw(count)
        self.table.community_cards.extend(new_cards)
        print()  # Add an extra line for better readability
        print(f"-- {street} --")
        self.ui.show_table(self.table.community_cards, self.table.pot)
        print()  # Add an extra line for better readability

    def _betting_round(self, street: str) -> None:
        # TODO: Task 6 - implement the betting round for the specified street, where each 
        # active player can choose to fold, call, or raise -> ensure that each action works
        # NOTE: this is a big task
        pass

    def _bot_action(self, player: Player, call_amount: int) -> str:
        # TODO: Task 7 - implement a simple bot strategy based on the 
        # call amount relative to the player's chips
        pass

    def _showdown(self) -> None:
        # TODO: Task 8 - if only one player remains, they win the pot; 
        # otherwise, evaluate the hands of all active players
        # NOTE: this is a big task
        pass

    def _only_one_player_left(self) -> bool:
        active_players = [player for player in self.players if player.active]
        return len(active_players) == 1

players = [
    Player(name="Lukas", chips=1000, is_human=True),
    Player(name="Bob", chips=1000),
    Player(name="Charlie", chips=1000),
]

game = TexasHoldemGame(players)
game.play_hand()
