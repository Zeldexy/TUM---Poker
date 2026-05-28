"""Five-card hand evaluator used to rank Texas Hold'em showdowns."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import IntEnum
from itertools import combinations

from cards import Card


class HandCategory(IntEnum):
    # TODO: Task 1 - define the hand categories in order from lowest to highest
    pass


@dataclass(frozen=True, order=True)
class HandRank:
    # TODO: Task 2 - define the HandRank dataclass with the category and tiebreakers

    # TODO: Task 2 - return a version of the category
    pass


class HandEvaluator:
    # TODO: Task 3 - implement the best_rank method to evaluate the best possible hand from a list of cards
    def best_rank(self, cards: list[Card]) -> HandRank:
        if len(cards) < 5:
            pass 
        pass 

    def _rank_five(self, cards: list[Card]) -> HandRank:
        # TODO: Task 4 - implement the logic to rank a five-card hand according to poker rules
        ranks = "change"
        counts = "me"
        groups = "into"
        is_flush = "something"
        straight_high = "useful"

        # TODO: Task 6 - implement the ranking logic 
        # NOTE: this is a hard task - ranking logic implemented in problem #6
        if is_flush and straight_high:
            return HandRank(HandCategory.STRAIGHT_FLUSH, (straight_high,))
        if groups[0][1] == 4:
            pass
        pass

    def _straight_high(self, ranks: list[int]) -> int | None:
        # TODO: Task 5 - implement the logic to determine if the hand contains a straight, 
        # and if so, return the high card of the straight
        pass
