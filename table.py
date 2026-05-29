"""Shared table state for a Hold'em hand."""

from __future__ import annotations

from dataclasses import dataclass, field

from cards import Card

@dataclass
class Table:
    pot: int = 0
    community_cards: list[Card] = field(default_factory=list)

    def reset(self) -> None:
        self.community_cards.clear()
        self.pot = 0

    def add_to_pot(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("amount to add to pot cannot be negative")
        self.pot += amount

