"""Card and deck primitives for Texas Hold'em."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from random import shuffle


class Suit(IntEnum):
    CLUBS = 0
    # TODO: Task 1 - continue here 

    @property
    def symbol(self) -> str:
        return {
            Suit.CLUBS: "C",
            # TODO: Task 1 - map each Suit to its one-letter symbol
        }[self]


class Rank(IntEnum):
    TWO = 2
    # TODO: Task 2 - continue until ACE = 14 

    @property
    def label(self) -> str:
        return {
            Rank.TWO: "2",
            # TODO: Task 2 - continue the mapping 
        }[self]


@dataclass(frozen=True)
class Card:
    rank: Rank
    # TODO: Task 3 - continue here 

    def __str__(self) -> str:
        # TODO: Task 3 - return a string representation of the card, e.g. "AH" for Ace of Hearts
        return ""


class Deck:
    def __init__(self) -> None:
        # TODO: Task 4 - initialize the deck with all 52 cards 
        shuffle(self._cards)

    def draw(self, count: int = 1) -> list[Card]:
        if count < 1:
            raise ValueError("count must be at least 1")
        # TODO: Task 4 - check if there are enough cards left in the deck, 
        # and if so, return the drawn cards and remove them from the deck
        return []

