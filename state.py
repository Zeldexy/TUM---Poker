"""JSON-serializable snapshots of game state for the web backend.

The engine itself stays UI-agnostic; these helpers translate a
``TexasHoldemGame`` and the events it yields into plain dicts the React client
renders. Hole cards are redacted per viewer: you only ever see your own cards
unless ``reveal_all`` is set (showdown).
"""

from __future__ import annotations

from engine_events import DecisionRequest


def serialize_player(game, player, seat: int, viewer_seat, reveal_all: bool) -> dict:
    show = reveal_all or (viewer_seat is not None and seat == viewer_seat)
    in_hand = not player.folded and len(player.hole_cards) > 0
    return {
        "seat": seat,
        "name": player.name,
        "chips": player.chips,
        "current_bet": player.current_bet,
        "folded": player.folded,
        "is_human": player.is_human,
        "all_in": in_hand and player.chips == 0,
        "is_button": seat == game.button,
        "is_small_blind": seat == getattr(game, "_sb_index", None),
        "is_big_blind": seat == getattr(game, "_bb_index", None),
        "hole_cards": [str(card) for card in player.hole_cards] if show else None,
        "hole_card_count": len(player.hole_cards),
    }


def serialize_state(game, viewer_seat=None, reveal_all: bool = False) -> dict:
    """Full public table snapshot, redacted for one viewer."""
    return {
        "hand_number": game.hand_number,
        "button": game.button,
        "small_blind_seat": getattr(game, "_sb_index", None),
        "big_blind_seat": getattr(game, "_bb_index", None),
        "small_blind": game.small_blind,
        "big_blind": game.big_blind,
        "pot": game.table.pot,
        "board": [str(card) for card in game.table.community_cards],
        "players": [
            serialize_player(game, player, seat, viewer_seat, reveal_all)
            for seat, player in enumerate(game.players)
        ],
    }


def serialize_decision(request: DecisionRequest) -> dict:
    """The 'your_turn' payload sent to the seat that must act."""
    return {
        "seat": request.seat,
        "name": request.name,
        "call_amount": request.call_amount,
        "can_check": request.can_check,
        "can_raise": request.can_raise,
        "min_raise": request.min_raise_increment,
        "max_raise": request.max_raise_increment,
        "can_all_in": request.can_all_in,
    }
