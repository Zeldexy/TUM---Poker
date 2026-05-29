"""Five-card hand evaluator used to rank Texas Hold'em showdowns."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import IntEnum
from itertools import combinations

from cards import Card, Deck, Rank, Suit


class HandCategory(IntEnum):
    HIGH_CARD = 0
    ONE_PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8


@dataclass(frozen=True, order=True)
class HandRank:
    category: HandCategory
    tiebreakers: tuple[int, ...]

    def __str__(self) -> str:
        return self.category.name.replace("_", " ").title()


class HandEvaluator:
    def best_rank(self, cards: list[Card]) -> HandRank:
        if len(cards) < 5:
            raise ValueError("need at least 5 cards to evaluate a hand")

        return max(self._rank_five(combo) for combo in combinations(cards, 5))

    def _rank_five(self, cards) -> HandRank:

        high_card = 0

        ranks = [card.rank.value for card in cards]
        counts = Counter()
        for rank in ranks:
            counts[rank] += 1
        groups = sorted(counts.items(), key=lambda x: x[1], reverse=True)

        is_flush = len(set(card.suit for card in cards)) == 1
        straight_high = self._straight_high(ranks)

        if is_flush and straight_high:
            return HandRank(HandCategory.STRAIGHT_FLUSH, (straight_high,))
        if straight_high:
            return HandRank(HandCategory.STRAIGHT, (straight_high,))
        if is_flush:
            return HandRank(HandCategory.FLUSH, tuple(sorted(ranks, reverse=True)))
        if groups[0][1] == 4:
            return HandRank(HandCategory.FOUR_OF_A_KIND, (groups[0][0],))
        if groups[0][1] == 3 and groups[1][1] == 2:
            return HandRank(HandCategory.FULL_HOUSE, (groups[0][0], groups[1][0]))
        if groups[0][1] == 3:
            return HandRank(HandCategory.THREE_OF_A_KIND, (groups[0][0],))
        if groups[0][1] == 2 and groups[1][1] == 2:
            return HandRank(HandCategory.TWO_PAIR, (groups[0][0], groups[1][0]))
        if groups[0][1] == 2:
            return HandRank(HandCategory.ONE_PAIR, (groups[0][0],))
        return HandRank(HandCategory.HIGH_CARD, tuple(sorted(ranks, reverse=True)))

    def _straight_high(self, ranks: list[int]) -> int | None:
        s = sorted(ranks)
        if s == list(range(s[0], s[0] + 5)):
            return s[-1]
        if s == [2, 3, 4, 5, 14]:  # Ace-low straight
            return 5
        return None
