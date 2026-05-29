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
        best = max(combinations(cards, 5), key=self._rank_five)
        return self._rank_five(best)


    def _rank_five(self, cards: list[Card]) -> HandRank:

        high_card = 0

        ranks = [card.rank.value for card in cards]
        counts = Counter()
        for rank in ranks:
            counts[rank] += 1
        groups = sorted(counts.items(), key=lambda x: x[1], reverse=True)

        is_flush = False
        straight_flush = False
        is_flush = True if len(set(card.suit for card in cards)) == 1 else False

        straight_high = self._straight_high(ranks)


        if is_flush: #Still need to check for straight flush and ace low straight flush
            straight_flush = True
            ranks.sort()
            high_card = ranks[-1]
            low = ranks[0]
            for i in range(1, 5):
                if ranks[i] != low + i:
                    straight_flush = False

        Royal_flush = False
        if straight_flush and ranks[0] == 10:
            Royal_flush = True


        # TODO: Task 6 - implement the ranking logic 
        # NOTE: this is a hard task - ranking logic implemented in problem #6
        if Royal_flush:
            return HandRank(HandCategory.STRAIGHT_FLUSH, (14,))
        if straight_flush:
            return HandRank(HandCategory.STRAIGHT_FLUSH, (ranks[-1],))
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
