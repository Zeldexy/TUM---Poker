"""Main Texas Hold'em game loop."""

from __future__ import annotations

from cards import Deck
from evaluator import HandEvaluator
from player import Player
from table import Table
from ui import ConsoleUI


class TexasHoldemGame:
    def __init__(self, players: list[Player], small_blind: int = 5, big_blind: int = 10) -> None:
        # TODO: Task 1 - check that there are at least 2 players, and if so, 
        # initialize the game state with the players, blinds, table, hand evaluator, and UI
        pass

    def play_hand(self) -> None:
        # TODO: Task 2 - implement the main game loop for a single hand of Texas Hold'em, following the 
        # standard sequence of actions (create new Deck, reset table, reset all players, deal two cards to each player, 
        # post blinds, deal (flop, turn, river), run betting rounds, and showdown)
        # NOTE: many of these actions are custom methods
        pass

    def _post_blinds(self) -> None:
        # TODO: Task 3 - have the first two players post the small and big blinds, 
        # respectively, add those amounts to the pot, 
        # and display the message as "[name] posts [small]; [name] posts [big]"
        pass

    def _show_human_cards(self) -> None:
        # TODO: Task 4 - display the hole cards of all human players, e.g. "Alice: AH KH"
        pass

    def _deal_community(self, deck: Deck, count: int, street: str) -> None:
        # TODO: Task 5 - stop if one player remains, deal the specified number of community 
        # cards from the deck, add them to the table, and display the message as "\n-- [Street] --"
        # HINT: use the extend method of the list to add the new cards to the existing community cards
        pass

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
        # TODO: Task 9 - return True if only one player is still active and False otherwise
        pass
