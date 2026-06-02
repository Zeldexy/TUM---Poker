"""Lobby + in-memory table sessions and the async driver for the engine.

A ``Table`` has two phases:

- **lobby**: the host configures starting chips, adds bots, invites humans (who
  join by code/link), and can kick anyone. Only the host starts the game, and
  only when there are at least two members.
- **running**: the host deals each hand. Bots auto-play; the backend only waits
  on a human when it is that human's turn. Someone who joins by code while a game
  is running is marked *pending* and is seated (with the table's starting chips)
  at the start of the next hand the host deals. Kicking is lobby-only; once
  running, seats are fixed (busted 0-chip players still auto-drop between hands).

Concurrency is asyncio-only (turn-based game): a per-table ``asyncio.Lock``
serializes start/deal/action, and the CPU-bound engine step (bot Monte-Carlo) is
offloaded with ``asyncio.to_thread`` so it never blocks the event loop.
"""

from __future__ import annotations

import asyncio
import os
import secrets
from dataclasses import dataclass

from engine_events import ActionResponse, DecisionRequest
from game import TexasHoldemGame
from player import Player
from state import serialize_decision, serialize_state
from ui import HeadlessUI


@dataclass
class Member:
    member_id: str
    name: str
    kind: str            # "human" | "bot"
    token: str | None    # auth/identity for humans; None for bots
    is_host: bool = False
    pending: bool = False  # joined while running; seated at the next dealt hand


class Table:
    def __init__(
        self,
        game_id: str,
        code: str,
        host_name: str,
        starting_chips: int,
        small_blind: int,
        big_blind: int,
    ) -> None:
        self.game_id = game_id
        self.code = code
        self.starting_chips = starting_chips
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.status = "lobby"  # "lobby" | "running" | "over"

        self.lock = asyncio.Lock()
        self.clients: dict[object, str | None] = {}  # ws -> token (None = spectator)
        self.members: list[Member] = []

        # Game-phase state (created on start).
        self.ui: HeadlessUI | None = None
        self.game: TexasHoldemGame | None = None
        self.runner = None
        self.pending_request: DecisionRequest | None = None
        # Names of humans who left; their turns are auto-folded so a running
        # game never stalls waiting on someone who closed their tab.
        self.left_names: set[str] = set()

        # Artificial "thinking time" (seconds) before revealing each bot move,
        # so the frontend shows bots acting one at a time. Tunable via env.
        self.bot_think_seconds = float(os.environ.get("POKER_BOT_THINK_SECONDS", "1.0"))

        self.host_token = secrets.token_urlsafe(9)
        self.add_member(host_name, "human", token=self.host_token, is_host=True)

    # ----- membership ----- #

    def add_member(self, name, kind, token=None, is_host=False, pending=False) -> Member:
        member = Member(secrets.token_urlsafe(6), name, kind, token, is_host, pending)
        self.members.append(member)
        return member

    def _name_taken(self, name: str) -> bool:
        return any(m.name == name for m in self.members)

    def _unique_bot_name(self) -> str:
        index = 1
        while self._name_taken(f"Bot {index}"):
            index += 1
        return f"Bot {index}"

    def is_host(self, token: str | None) -> bool:
        return token is not None and token == self.host_token

    def name_for(self, token: str | None) -> str | None:
        if token is None:
            return None
        for member in self.members:
            if member.token == token:
                return member.name
        return None

    def viewer_seat_for(self, token: str | None) -> int | None:
        name = self.name_for(token)
        if name is None or self.game is None:
            return None
        for seat, player in enumerate(self.game.players):
            if player.name == name:
                return seat
        return None

    # ----- lobby mutations (host) ----- #

    def join(self, name: str) -> Member:
        if self.status == "over":
            raise ValueError("This game has finished.")
        if not name or not name.strip():
            raise ValueError("A name is required.")
        name = name.strip()
        if self._name_taken(name):
            raise ValueError("That name is already taken at this table.")
        token = secrets.token_urlsafe(9)
        # Joining mid-game = wait for the next dealt hand to be seated.
        return self.add_member(
            name, "human", token=token, pending=(self.status == "running")
        )

    def add_bot(self, token: str | None, name: str | None) -> Member:
        self._require_host(token)
        if self.status != "lobby":
            raise ValueError("Bots can only be added in the lobby.")
        name = (name or "").strip() or self._unique_bot_name()
        if self._name_taken(name):
            raise ValueError("That name is already taken at this table.")
        return self.add_member(name, "bot", token=None)

    def kick(self, token: str | None, member_id: str) -> None:
        self._require_host(token)
        if self.status != "lobby":
            raise ValueError("Players can only be kicked in the lobby.")
        target = next((m for m in self.members if m.member_id == member_id), None)
        if target is None:
            raise ValueError("No such member.")
        if target.is_host:
            raise ValueError("The host cannot be kicked.")
        self.members.remove(target)

    async def leave(self, token: str | None) -> None:
        name = self.name_for(token)
        if name is None:
            return  # spectator or unknown token: nothing to remove
        # Mark as left so any future turn for this player is auto-folded.
        self.left_names.add(name)
        member = next((m for m in self.members if m.token == token), None)
        if self.status == "lobby" and member is not None:
            was_host = member.is_host
            self.members.remove(member)
            if was_host:
                # Hand the host role to the next human, if any remains.
                next_human = next((m for m in self.members if m.kind == "human"), None)
                if next_human is not None:
                    next_human.is_host = True
                    self.host_token = next_human.token
            await self._broadcast_lobby()
        elif self.status == "running":
            # Seat stays in the hand but its turns auto-fold; surface a notice.
            if self.ui is not None:
                self.ui.messages.append(f"{name} left the table.")
                await self._flush_log()

    def set_starting_chips(self, token: str | None, chips: int) -> None:
        self._require_host(token)
        if self.status != "lobby":
            raise ValueError("Starting chips can only be set in the lobby.")
        if chips <= 0:
            raise ValueError("Starting chips must be positive.")
        self.starting_chips = chips

    def _require_host(self, token: str | None) -> None:
        if not self.is_host(token):
            raise ValueError("Only the host may do that.")

    # ----- starting / dealing ----- #

    async def start_game(self, token: str | None) -> None:
        async with self.lock:
            self._require_host(token)
            if self.status != "lobby":
                raise ValueError("The game has already started.")
            if len(self.members) < 2:
                raise ValueError("Need at least 2 players to start.")
            players = [
                Player(m.name, self.starting_chips, is_human=(m.kind == "human"))
                for m in self.members
            ]
            self.ui = HeadlessUI()
            self.game = TexasHoldemGame(
                players, self.small_blind, self.big_blind, ui=self.ui
            )
            self.status = "running"
            await self._broadcast_lobby()
            await self._begin_hand()

    async def deal_hand(self, token: str | None) -> None:
        async with self.lock:
            self._require_host(token)
            if self.status != "running":
                raise ValueError("The game is not running.")
            if self.runner is not None:
                return  # a hand is already in progress
            self._seat_pending_members()
            await self._begin_hand()

    def _seat_pending_members(self) -> None:
        assert self.game is not None
        for member in self.members:
            if member.pending:
                self.game.players.append(
                    Player(member.name, self.starting_chips, is_human=True)
                )
                member.pending = False

    async def _begin_hand(self) -> None:
        assert self.game is not None
        if sum(1 for p in self.game.players if p.chips > 0) < 2:
            await self._end_game()
            return
        self.runner = self.game._run_hand()
        await self._advance(None)

    async def submit_action(self, token, action: str, amount: int) -> None:
        async with self.lock:
            request = self.pending_request
            if request is None:
                raise ValueError("No action is pending.")
            if self.name_for(token) != request.name:
                raise ValueError("It is not your turn.")
            self._validate(request, action)
            self.pending_request = None
            await self._advance(ActionResponse(action=action, amount=amount or 0))

    @staticmethod
    def _validate(request: DecisionRequest, action: str) -> None:
        if action == "fold" or action == "call":
            return
        if action == "check":
            if not request.can_check:
                raise ValueError("You cannot check; there is a bet to call.")
            return
        if action in ("all in", "all_in", "allin"):
            if not request.can_all_in:
                raise ValueError("You have no chips to go all in with.")
            return
        if action == "raise":
            if not request.can_raise:
                raise ValueError("Raising is not allowed here.")
            return
        raise ValueError(f"Unknown action: {action!r}")

    # ----- engine pump ----- #

    def _step(self, response: ActionResponse | None):
        try:
            if response is None:
                return next(self.runner)
            return self.runner.send(response)
        except StopIteration:
            return None

    async def _advance(self, response: ActionResponse | None) -> None:
        # Holds self.lock (callers acquire it). Pumps the engine generator one
        # event at a time: each Tick is broadcast separately so the frontend
        # sees moves one by one, and a bot Tick (pause=True) is preceded by
        # artificial thinking time. Stops at a human decision or the hand's end.
        result = await asyncio.to_thread(self._step, response)
        while True:
            if result is None:
                self.pending_request = None
                self.runner = None
                await self._broadcast_state()
                await self._flush_log()
                await self._broadcast_hand_result()
                if sum(1 for p in self.game.players if p.chips > 0) < 2:
                    await self._end_game()
                return
            if isinstance(result, DecisionRequest):
                if result.name in self.left_names:
                    # The player left; auto-fold their turn so the table never
                    # stalls waiting on someone who is gone.
                    await self._broadcast_state()
                    await self._flush_log()
                    result = await asyncio.to_thread(
                        self._step, ActionResponse(action="fold")
                    )
                    continue
                await self._broadcast_state()
                await self._flush_log()
                self.pending_request = result
                await self._send_your_turn(result)
                return
            # Tick: pause before revealing a bot's move so it reads as "thinking".
            if getattr(result, "pause", False):
                await asyncio.sleep(self.bot_think_seconds)
            await self._broadcast_state()
            await self._flush_log()
            result = await asyncio.to_thread(self._step, None)

    async def _end_game(self) -> None:
        self.status = "over"
        self.runner = None
        self.pending_request = None
        survivors = [p for p in self.game.players if p.chips > 0] if self.game else []
        winner = survivors[0].name if survivors else None
        await self._broadcast({"type": "game_over", "winner": winner})

    # ----- snapshots & messages ----- #

    def lobby_snapshot(self) -> dict:
        return {
            "type": "lobby",
            "game_id": self.game_id,
            "code": self.code,
            "status": self.status,
            "starting_chips": self.starting_chips,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "can_start": self.status == "lobby" and len(self.members) >= 2,
            "members": [
                {
                    "id": m.member_id,
                    "name": m.name,
                    "kind": m.kind,
                    "is_host": m.is_host,
                    "pending": m.pending,
                }
                for m in self.members
            ],
        }

    def _state_msg(self, token: str | None, reveal_all: bool = False) -> dict:
        return {
            "type": "state",
            "game_id": self.game_id,
            "status": self.status,
            "hand_in_progress": self.runner is not None,
            "your_seat": self.viewer_seat_for(token),
            "state": serialize_state(self.game, self.viewer_seat_for(token), reveal_all),
        }

    # ----- connections ----- #

    async def connect(self, websocket, token: str | None) -> None:
        self.clients[websocket] = token
        if self.status == "lobby":
            await self._safe_send(websocket, self.lobby_snapshot())
        else:
            await self._safe_send(websocket, self._state_msg(token))
            if (
                self.pending_request is not None
                and self.name_for(token) == self.pending_request.name
            ):
                await self._safe_send(
                    websocket, {"type": "your_turn", **serialize_decision(self.pending_request)}
                )

    def disconnect(self, websocket) -> None:
        self.clients.pop(websocket, None)

    # ----- broadcasting ----- #

    async def _broadcast(self, message: dict) -> None:
        for websocket in list(self.clients):
            await self._safe_send(websocket, message)

    async def _broadcast_lobby(self) -> None:
        await self._broadcast(self.lobby_snapshot())

    async def _broadcast_state(self, reveal_all: bool = False) -> None:
        for websocket, token in list(self.clients.items()):
            await self._safe_send(websocket, self._state_msg(token, reveal_all))

    async def _flush_log(self) -> None:
        if self.ui is None:
            return
        lines = self.ui.drain()
        if lines:
            await self._broadcast({"type": "log", "lines": lines})

    async def _send_your_turn(self, request: DecisionRequest) -> None:
        payload = {"type": "your_turn", **serialize_decision(request)}
        for websocket, token in list(self.clients.items()):
            if self.name_for(token) == request.name:
                await self._safe_send(websocket, payload)

    async def _broadcast_hand_result(self) -> None:
        for websocket, token in list(self.clients.items()):
            message = self._state_msg(token, reveal_all=True)
            message["type"] = "hand_result"
            await self._safe_send(websocket, message)

    async def _safe_send(self, websocket, message: dict) -> None:
        try:
            await websocket.send_json(message)
        except Exception:
            self.clients.pop(websocket, None)

    async def broadcast_after_lobby_change(self) -> None:
        await self._broadcast_lobby()


class TableRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, Table] = {}
        self._by_code: dict[str, str] = {}  # code -> game_id

    def create(
        self, host_name: str, starting_chips: int, small_blind: int, big_blind: int
    ) -> Table:
        game_id = secrets.token_urlsafe(6)
        code = self._unique_code()
        table = Table(game_id, code, host_name, starting_chips, small_blind, big_blind)
        self._by_id[game_id] = table
        self._by_code[code] = game_id
        return table

    def _unique_code(self) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous chars
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(6))
            if code not in self._by_code:
                return code

    def get(self, game_id: str) -> Table | None:
        return self._by_id.get(game_id)

    def get_by_code(self, code: str) -> Table | None:
        game_id = self._by_code.get(code.strip().upper())
        return self._by_id.get(game_id) if game_id else None

    def remove(self, game_id: str) -> None:
        table = self._by_id.pop(game_id, None)
        if table is not None:
            self._by_code.pop(table.code, None)


registry = TableRegistry()
