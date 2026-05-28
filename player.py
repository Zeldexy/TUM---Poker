"""Player model for the poker table."""

from __future__ import annotations

from dataclasses import dataclass, field

from cards import Card


@dataclass
class Player:
    name: str
    # TODO: Task 1 - add chips, is_human, hole_cards, current_bet, and folded

    def reset_for_hand(self) -> None:
        # TODO: Task 2 - reset the player's state for a new hand
        pass

    def receive(self, cards: list[Card]) -> None:
        # TODO: Task 3 - add the received cards to the player's hole cards
        pass

    def bet(self, amount: int) -> int:
        # TODO: Task 4 - check if the player has enough chips to bet the specified amount, 
        # and if so, deduct the amount from the player's chips and add it to the current bet
        if amount < 0:
            pass
        pass 

    @property
    def active(self) -> bool:
        # TODO: Task 5 - return True if the player is still active in the hand
        pass

