"""Decision engine for bot players.

BotBrain is pure logic: it never prints, never reads input, and never mutates
the table, players, or any shared state. It only inspects cards and numbers and
returns one of 'fold', 'call', or 'raise'.

Note: imports are absolute (``from cards import ...``) to match the rest of this
project, which is run as flat scripts (``python main.py``) rather than as a
package. Relative imports would break ``import bot`` in test_bot.py.
"""

from __future__ import annotations

import random

from cards import Card, Deck, Rank, Suit
from evaluator import HandEvaluator


class BotBrain:
    def __init__(self, simulations: int = 1000) -> None:
        self.simulations = simulations
        # One shared, stateless evaluator reused for every decision.
        # Never reassign this after construction.
        self.evaluator = HandEvaluator()

    def decide(
        self,
        hole_cards: list[Card],
        community_cards: list[Card],
        pot: int,
        call_amount: int,
        player_chips: int,
        position_index: int,
        total_active_players: int,
    ) -> str:
        # Layer 1 - Win probability via Monte Carlo simulation.
        num_opponents = total_active_players - 1
        win_prob = self._estimate_win_probability(
            hole_cards, community_cards, num_opponents
        )

        # Layer 2 - Pot odds, adjusted for table position.
        if call_amount == 0:
            pot_odds = 0.0
        else:
            pot_odds = call_amount / (pot + call_amount)

        # Acting later is a positional advantage, so we loosen the calling
        # threshold the closer this player is to the button.
        position_ratio = position_index / max(total_active_players - 1, 1)
        adjusted_threshold = pot_odds - (0.05 * position_ratio)
        if adjusted_threshold < 0.0:
            adjusted_threshold = 0.0

        # Layer 3 - Decision.
        if call_amount == 0:
            # Checking is free; only raise with a genuinely strong hand.
            if win_prob > 0.65:
                return "raise"
            return "call"

        if win_prob >= 0.65:
            return "raise"

        if win_prob >= adjusted_threshold:
            return "call"

        return "fold"

    def _estimate_win_probability(
        self,
        hole_cards: list[Card],
        community_cards: list[Card],
        num_opponents: int,
    ) -> float:
        # Build the pool of unseen cards: the full deck minus everything the
        # bot can currently observe.
        seen = set(hole_cards) | set(community_cards)
        unseen = [
            Card(rank, suit)
            for rank in Rank
            for suit in Suit
            if Card(rank, suit) not in seen
        ]

        cards_needed = 5 - len(community_cards)

        wins = 0
        valid_iterations = 0

        for _ in range(self.simulations):
            shuffled = unseen[:]
            random.shuffle(shuffled)

            # Make sure there are enough cards to deal opponents plus the board.
            if num_opponents * 2 + cards_needed > len(shuffled):
                continue

            opponent_hands = []
            for i in range(num_opponents):
                opponent_hands.append(shuffled[i * 2 : i * 2 + 2])

            simulated_community = (
                community_cards
                + shuffled[num_opponents * 2 : num_opponents * 2 + cards_needed]
            )

            bot_best = self.evaluator.best_rank(hole_cards + simulated_community)

            # The bot wins only if it strictly beats every opponent; ties do
            # not count as a win here (split pots are handled in game.py).
            bot_wins = True
            for opponent_hole in opponent_hands:
                opponent_best = self.evaluator.best_rank(
                    opponent_hole + simulated_community
                )
                if not (bot_best > opponent_best):
                    bot_wins = False
                    break

            valid_iterations += 1
            if bot_wins:
                wins += 1

        if valid_iterations == 0:
            return 0.5

        return wins / valid_iterations