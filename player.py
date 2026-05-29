"""Player model for the poker table."""

from __future__ import annotations

from dataclasses import dataclass, field

from cards import Card


@dataclass
class Player:
    name: str
    chips: int
    is_human: bool = False
    hole_cards: list = field(default_factory=list)
    current_bet: int = 0
    folded: bool = False


    def reset_for_hand(self) -> None:
        self.hole_cards.clear()
        self.current_bet = 0
        self.folded = False

    def receive(self, cards: list[Card]) -> None:
        self.hole_cards.extend(cards)
        pass

    def bet(self, amount: int) -> int:

        if amount < 0:
            raise ValueError("bet amount cannot be negative")
        if amount > self.chips:
            raise ValueError("not enough chips to bet that amount")
        
        self.chips -= amount
        self.current_bet += amount
        return self.current_bet

    @property
    def active(self) -> bool:

        if not self.folded and self.chips > 0:
            return True
        else:
            return False

