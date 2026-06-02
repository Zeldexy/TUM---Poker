"""UI-agnostic events the game engine exchanges with a driver.

TexasHoldemGame._run_hand() is a generator: it yields a DecisionRequest
whenever a human must act and is resumed with an ActionResponse via .send().
The console driver and the web backend both speak this protocol, so the
betting logic never depends on how I/O actually happens. Bots resolve
synchronously inside the engine and never produce a DecisionRequest.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionRequest:
    """Emitted when the human in `seat` must choose an action."""

    seat: int                  # index into game.players of the player to act
    name: str
    call_amount: int           # chips needed to call (0 means a check is allowed)
    can_check: bool            # call_amount == 0
    can_raise: bool            # False when re-opening is closed or no chips to raise
    min_raise_increment: int   # smallest legal raise on top of the call
    max_raise_increment: int   # largest raise on top of the call (an all-in raise)
    can_all_in: bool           # the player still has chips to shove


@dataclass(frozen=True)
class ActionResponse:
    """The chosen action sent back into the generator with .send()."""

    action: str                # "fold" | "call" | "check" | "raise" | "all in"
    amount: int = 0            # raise increment on top of the call; only for "raise"


@dataclass(frozen=True)
class Tick:
    """The engine advanced and the view should refresh.

    Yielded after the hand is dealt, after each community street, and after each
    player acts — so a driver can broadcast incrementally instead of batching a
    whole street into one update. ``pause`` is True after a bot acts so the web
    driver can insert artificial "thinking time" before revealing the move; it
    requires no response (resume with ``.send(None)``).
    """

    pause: bool = False
    actor: str | None = None   # name of the player who just acted, if any
