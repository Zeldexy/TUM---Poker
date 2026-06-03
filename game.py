"""Main Texas Hold'em game loop.

The hand is driven by a generator (``_run_hand``) that yields a
``DecisionRequest`` whenever a human must act and is resumed with an
``ActionResponse`` via ``.send()``. ``play_hand()`` is the console driver that
backs those requests with ``ConsoleUI``; the web backend drives the same
generator and backs them with client messages. Bots resolve synchronously
inside the engine and never yield. Output goes through ``self.ui`` so it can be
printed (console) or buffered (headless/web).
"""

from __future__ import annotations

from collections.abc import Generator

from bot import BotBrain
from cards import Deck
from engine_events import ActionResponse, DecisionRequest, Tick
from evaluator import HandEvaluator, HandRank
from hand_history import HandHistoryLogger
from player import Player
from table import Table
from ui import ConsoleUI


class TexasHoldemGame:
    def __init__(
        self,
        players: list[Player],
        small_blind: int = 5,
        big_blind: int = 10,
        ui=None,
        history=None,
    ) -> None:
        if len(players) < 2:
            raise ValueError("There must be at least 2 players to start the game.")
        self.players = players
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.table = Table()
        self.evaluator = HandEvaluator()
        # ConsoleUI by default; the web backend injects a HeadlessUI that buffers
        # output instead of printing. The engine only depends on show_message /
        # show_table / show_player / format_cards.
        self.ui = ui if ui is not None else ConsoleUI()
        self.hand_number = 0
        # Index into self.players of the dealer button. The small blind sits one
        # seat left of the button and the big blind two seats left, so starting
        # the button at the last seat makes the first hand's small blind
        # players[0] and big blind players[1]. Rotates one seat clockwise after
        # every hand so the blinds do not always fall on the same players.
        self.button = len(players) - 1
        # ConsoleUI writes to the shared default file; the web backend injects a
        # per-table HandHistoryLogger so each table's hands stay separate.
        self.history = history if history is not None else HandHistoryLogger()
        self.bot_brain = BotBrain(simulations=1000)

    # ------------------------------------------------------------------ #
    # Drivers
    # ------------------------------------------------------------------ #

    def play_hand(self) -> None:
        """Console driver: run one hand, answering human turns via ConsoleUI."""
        runner = self._run_hand()
        try:
            event = next(runner)  # prime the generator up to the first event
            while True:
                if isinstance(event, DecisionRequest):
                    event = runner.send(self._console_respond(event))
                else:  # Tick — refresh point; the console renders inline already
                    event = runner.send(None)
        except StopIteration:
            pass

        # Separate finished hands in the console log so games are easy to track.
        print()
        print()
        print("-" * 40)
        print()
        print()

    def _console_respond(self, request: DecisionRequest) -> ActionResponse:
        player = self.players[request.seat]
        action = self.ui.ask_action(player, request.call_amount, request.can_raise)
        if action != "raise":
            return ActionResponse(action)
        if request.min_raise_increment > request.max_raise_increment:
            # Not enough chips for a full legal raise; the only raise is all-in.
            return ActionResponse("raise", request.max_raise_increment)
        increment = self.ui.ask_raise_amount(
            request.min_raise_increment, request.max_raise_increment
        )
        return ActionResponse("raise", increment)

    # ------------------------------------------------------------------ #
    # Hand orchestration (generator)
    # ------------------------------------------------------------------ #

    def _run_hand(self) -> Generator[DecisionRequest | Tick, ActionResponse | None, None]:
        # Drop players who busted in a previous hand. A 0-chip player can't post
        # a blind, can't be dealt in, and must not ride to showdown for free.
        # Keeping them in is what let a broke player keep winning pots and
        # stopped folded-around hands from ending. Mutate in place (slice
        # assignment) so the caller's player list stays in sync.
        self.players[:] = [player for player in self.players if player.chips > 0]
        if len(self.players) < 2:
            self.ui.show_message("Not enough players with chips to play a hand.")
            return

        self.hand_number += 1
        self.history.start_hand(self.hand_number, self.players)

        # Keep the button in range after any eliminations, then derive the
        # blind seats: small blind one seat left of the button, big blind two.
        self.button %= len(self.players)
        self._sb_index = (self.button + 1) % len(self.players)
        self._bb_index = (self.button + 2) % len(self.players)

        deck = Deck()
        self.table.reset()
        # Total chips each player has put in this hand (across every street).
        # Drives side-pot construction at showdown. Folded players stay in the
        # map — their chips remain in the pot even though they can't win it.
        self.contributions = {player.name: 0 for player in self.players}

        for player in self.players:
            player.reset_for_hand()
        for player in self.players:
            hole_cards = deck.draw(2)
            player.receive(hole_cards)

        self._post_blinds()
        self._show_players_chips()
        self._show_human_cards()
        # Reveal the freshly dealt hand (blinds, hole cards) before betting.
        yield Tick()
        yield from self._betting_round("Pre-Flop")
        self._deal_community(deck, 3, "Flop")
        yield Tick()
        yield from self._betting_round("Flop")
        self._deal_community(deck, 1, "Turn")
        yield Tick()
        yield from self._betting_round("Turn")
        self._deal_community(deck, 1, "River")
        yield Tick()
        yield from self._betting_round("River")
        self._showdown()

        # Move the button one seat clockwise for the next hand.
        self.button = (self.button + 1) % len(self.players)

    def _commit(self, player: Player, wager: int) -> None:
        # Single choke point for chips entering the pot: keeps table.pot and the
        # per-player contribution map (used for side pots) perfectly in sync.
        self.table.add_to_pot(wager)
        self.contributions[player.name] += wager

    def _post_blinds(self) -> None:
        if len(self.players) < 2:
            raise ValueError("There must be at least 2 players to post blinds.")
        small_blind_player = self.players[self._sb_index]
        big_blind_player = self.players[self._bb_index]
        actual_small = small_blind_player.bet(self.small_blind)
        self._commit(small_blind_player, actual_small)
        actual_big = big_blind_player.bet(self.big_blind)
        self._commit(big_blind_player, actual_big)

        self.history.log_action(small_blind_player.name, "small_blind", actual_small, "Pre-Flop")
        self.history.log_action(big_blind_player.name, "big_blind", actual_big, "Pre-Flop")

        self.ui.show_message(
            f"{small_blind_player.name} posts {actual_small}; {big_blind_player.name} posts {actual_big}"
        )

    def _show_players_chips(self) -> None:
        for player in self.players:
            self.ui.show_message(f"{player.name}: {player.chips} chips")

    def _show_human_cards(self) -> None:
        for player in self.players:
            if player.is_human:
                self.ui.show_player(player)

    def _deal_community(self, deck: Deck, count: int, street: str) -> None:
        if self._only_one_player_left():
            return
        new_cards = deck.draw(count)
        self.table.community_cards.extend(new_cards)

        self.history.log_community_cards(street, new_cards)

        self.ui.show_message(f"-- {street} --")
        self.ui.show_table(self.table.community_cards, self.table.pot)

    def _betting_round(
        self, street: str
    ) -> Generator[DecisionRequest | Tick, ActionResponse | None, None]:
        if self._only_one_player_left():
            return

        # Once at most one player still has chips to wager (everyone else is
        # folded or all-in), there is nothing left to bet on — the remaining
        # streets are simply dealt out. Skipping avoids a lone player "betting"
        # into opponents who can no longer respond.
        if sum(1 for p in self.players if not p.folded and p.chips > 0) < 2:
            return

        highest_bet = max(p.current_bet for p in self.players)
        # Minimum legal raise increment for this round. The first bet or raise
        # must be at least the big blind; thereafter it is the size of the last
        # full raise. Reset at the start of every betting round.
        last_raise_size = self.big_blind
        # Players who have acted since the last action-reopening (full) raise.
        acted: set[str] = set()
        # Players act in clockwise order from the correct first seat for the
        # street (under the gun pre-flop, small blind afterwards).
        order = self._action_order(street == "Pre-Flop")

        while True:
            if self._only_one_player_left():
                break

            # Settled = folded, all-in, or has acted and matched the current bet.
            all_settled = all(
                p.folded
                or p.chips == 0
                or (p.name in acted and p.current_bet == highest_bet)
                for p in self.players
            )
            if all_settled:
                break

            for player in order:
                if player.folded or player.chips == 0:
                    continue
                if self._only_one_player_left():
                    break

                call_amount = highest_bet - player.current_bet

                already_acted = player.name in acted
                # Nothing owed and already acted -> settled, skip.
                if already_acted and call_amount == 0:
                    continue

                # A player may (re-)raise only when the action is open to them:
                # they have not yet acted since the last full raise. Someone
                # dragged back in solely to call a sub-minimum all-in may not
                # re-raise.
                allow_raise = not already_acted

                # Largest/smallest legal raise on top of the call this turn.
                max_increment = player.chips - call_amount
                min_increment = last_raise_size

                if player.is_human:
                    self.ui.show_table(self.table.community_cards, self.table.pot)
                    self.ui.show_player(player)
                    response = yield DecisionRequest(
                        seat=self.players.index(player),
                        name=player.name,
                        call_amount=call_amount,
                        can_check=call_amount == 0,
                        can_raise=allow_raise and max_increment > 0,
                        min_raise_increment=min_increment,
                        max_raise_increment=max_increment,
                        can_all_in=player.chips > 0,
                    )
                    # A driver always sends an ActionResponse for a
                    # DecisionRequest; guard against a stray None defensively.
                    if response is None:
                        action, requested_increment = "fold", None
                    else:
                        action = self._normalize_action(response.action)
                        requested_increment = response.amount
                else:
                    action = self._bot_action(player, call_amount)
                    if action == "raise" and not allow_raise:
                        action = "call"
                    requested_increment = None

                acted.add(player.name)

                # Apply the action. Branches use if/elif (no `continue`) so the
                # Tick at the end of the turn is always reached — that Tick lets
                # the driver reveal one action at a time (with bot "thinking").
                if action == "fold":
                    player.folded = True
                    self.history.log_action(player.name, "fold", 0, street)
                    self.ui.show_message(f"{player.name} folds.")

                elif action == "all in":
                    wager = player.all_in()
                    self._commit(player, wager)
                    increment = player.current_bet - highest_bet
                    if increment >= last_raise_size:
                        # A full legal raise reopens the action to everyone else.
                        last_raise_size = increment
                        acted = {player.name}
                    if player.current_bet > highest_bet:
                        highest_bet = player.current_bet
                    self.history.log_action(player.name, "all_in", wager, street)
                    self.ui.show_message(f"{player.name} goes all in for {wager}!")

                elif action == "raise" and max_increment > 0:
                    if player.is_human:
                        increment = self._clamp_raise(
                            requested_increment, min_increment, max_increment
                        )
                    else:
                        increment = self._bot_raise_increment(min_increment, max_increment)
                    wager = player.bet(call_amount + increment)
                    self._commit(player, wager)
                    actual_increment = player.current_bet - highest_bet
                    if actual_increment >= last_raise_size:
                        last_raise_size = actual_increment
                        acted = {player.name}
                    if player.current_bet > highest_bet:
                        highest_bet = player.current_bet
                    self.history.log_action(player.name, "raise", wager, street)
                    suffix = " (all in)" if player.chips == 0 else ""
                    self.ui.show_message(
                        f"{player.name} raises by {actual_increment}{suffix}."
                    )

                else:
                    # A call/check, or a "raise" the stack can't fund (an all-in
                    # short call): put in whatever the call takes, capped by bet().
                    wager = player.bet(call_amount)
                    self._commit(player, wager)
                    if call_amount == 0:
                        self.history.log_action(player.name, "check", 0, street)
                        self.ui.show_message(f"{player.name} checks.")
                    else:
                        self.history.log_action(player.name, "call", wager, street)
                        suffix = " (all in)" if player.chips == 0 else ""
                        self.ui.show_message(f"{player.name} calls {wager}{suffix}.")

                # Reveal this action on its own; bots get a "thinking" pause.
                yield Tick(pause=not player.is_human, actor=player.name)

        for player in self.players:
            player.current_bet = 0

    @staticmethod
    def _normalize_action(action: str) -> str:
        # Accept web aliases; the engine works in "call"/"all in" terms.
        action = action.strip().lower()
        if action == "check":
            return "call"
        if action in ("all_in", "allin"):
            return "all in"
        return action

    @staticmethod
    def _clamp_raise(requested: int | None, minimum: int, maximum: int) -> int:
        # Never trust the requested increment (web clients especially). If the
        # stack can't cover a full minimum raise, the only legal raise is a shove.
        if minimum > maximum:
            return maximum
        if requested is None:
            return minimum
        return max(minimum, min(requested, maximum))

    def _bot_action(self, player: Player, call_amount: int) -> str:
        active_players = [p for p in self.players if not p.folded]
        position_index = active_players.index(player)
        total_active = len(active_players)

        return self.bot_brain.decide(
            hole_cards=player.hole_cards,
            community_cards=self.table.community_cards,
            pot=self.table.pot,
            call_amount=call_amount,
            player_chips=player.chips,
            position_index=position_index,
            total_active_players=total_active,
        )

    def _bot_raise_increment(self, minimum: int, maximum: int) -> int:
        # Bots raise a fixed, modest size: the minimum legal raise. When they
        # cannot afford even that, they shove whatever chips remain (all-in).
        if maximum < minimum:
            return maximum
        return minimum

    def _showdown(self) -> None:
        # Any portion of a bet that no one could match is returned to the
        # bettor before pots are settled (e.g. an opponent called all-in for
        # less). Without this the over-bettor would be paid from their own chips.
        self._refund_uncalled_bet()

        # Everyone else folded: the last player standing takes the whole pot.
        if self._only_one_player_left():
            winner = [p for p in self.players if not p.folded][0]
            amount = self.table.pot
            winner.chips += amount
            self.ui.show_message(
                f"{winner.name} wins {amount} chips (everyone else folded)."
            )
            self.history.finish_hand([winner.name], amount)
            return

        # Reveal and rank every player still in the hand.
        ranks: dict[str, HandRank] = {}
        for player in self.players:
            if player.folded:
                continue
            rank = self.evaluator.best_rank(
                player.hole_cards + self.table.community_cards
            )
            ranks[player.name] = rank
            self.ui.show_message(
                f"{player.name}: {self.ui.format_cards(player.hole_cards)} - {rank}"
            )

        total_awarded = self.table.pot
        winner_names: list[str] = []
        pots = self._merge_contested_pots(self._build_side_pots())
        for index, (amount, contenders) in enumerate(pots):
            if amount == 0 or not contenders:
                continue
            best_rank = max(ranks[p.name] for p in contenders)
            winners = [p for p in contenders if ranks[p.name] == best_rank]
            label = "the pot" if len(pots) == 1 else (
                "the main pot" if index == 0 else f"side pot {index}"
            )
            self._award_pot(amount, winners, best_rank, label)
            for w in winners:
                if w.name not in winner_names:
                    winner_names.append(w.name)

        self.history.finish_hand(winner_names, total_awarded)

    def _merge_contested_pots(
        self, pots: list[tuple[int, list[Player]]]
    ) -> list[tuple[int, list[Player]]]:
        # Collapse the raw contribution layers down to the pots that actually
        # need separating: those contested by different sets of live players.
        # Dead money from a folded player (e.g. a surrendered blind) otherwise
        # shows up as a bogus "side pot" even though one set of players contests
        # the whole thing. Layers are produced smallest-first with a shrinking
        # participant set, so equal live-contender sets are always adjacent.
        merged: list[tuple[int, list[Player]]] = []
        for amount, eligible in pots:
            contenders = [p for p in eligible if not p.folded]
            names = frozenset(p.name for p in contenders)
            if merged and frozenset(p.name for p in merged[-1][1]) == names:
                previous_amount, previous_contenders = merged[-1]
                merged[-1] = (previous_amount + amount, previous_contenders)
            else:
                merged.append((amount, contenders))
        return merged

    def _refund_uncalled_bet(self) -> None:
        # If exactly one player contributed strictly more than everyone else,
        # the surplus above the next-highest contribution was never called and
        # belongs back in their stack.
        contributed = {name: amt for name, amt in self.contributions.items() if amt > 0}
        if len(contributed) < 2:
            return
        amounts = sorted(contributed.values())
        highest, second = amounts[-1], amounts[-2]
        if highest == second:
            return
        top_names = [name for name, amt in contributed.items() if amt == highest]
        if len(top_names) != 1:
            return
        name = top_names[0]
        refund = highest - second
        player = self._player_by_name(name)
        player.chips += refund
        self.contributions[name] -= refund
        self.table.pot -= refund
        self.ui.show_message(f"{refund} uncalled chips returned to {name}.")

    def _build_side_pots(self) -> list[tuple[int, list[Player]]]:
        # Peel the pot into layers, smallest contribution first. Each layer
        # holds (layer_size * number_of_contributors_at_that_level) chips, and
        # only players who reached that level are eligible to win it.
        contributed = {name: amt for name, amt in self.contributions.items() if amt > 0}
        pots: list[tuple[int, list[Player]]] = []
        while contributed:
            floor = min(contributed.values())
            participants = list(contributed.keys())
            amount = floor * len(participants)
            eligible = [self._player_by_name(name) for name in participants]
            pots.append((amount, eligible))
            contributed = {
                name: amt - floor
                for name, amt in contributed.items()
                if amt - floor > 0
            }
        return pots

    def _award_pot(self, amount: int, winners: list[Player], best_rank, label: str) -> None:
        share = amount // len(winners)
        remainder = amount - share * len(winners)
        for winner in winners:
            winner.chips += share
        # Odd chip(s) left by an indivisible split go to the first eligible
        # winner clockwise from the dealer button (the small blind seat first).
        if remainder:
            count = len(self.players)
            first = min(
                winners,
                key=lambda p: (self.players.index(p) - self._sb_index) % count,
            )
            first.chips += remainder
        if len(winners) == 1:
            self.ui.show_message(
                f"{winners[0].name} wins {amount} chips from {label} with {best_rank}!"
            )
        else:
            names = ", ".join(w.name for w in winners)
            self.ui.show_message(
                f"Tie! {names} split {label} ({amount} chips) with {best_rank}."
            )

    def _player_by_name(self, name: str) -> Player:
        for player in self.players:
            if player.name == name:
                return player
        raise ValueError(f"No player named {name}.")

    def _action_order(self, preflop: bool) -> list[Player]:
        # Clockwise seating starting from the player who acts first this street.
        # Pre-flop that is under the gun (left of the big blind); on later
        # streets it is the small blind. This also puts the big blind last
        # pre-flop, giving them the option to raise after everyone has called.
        count = len(self.players)
        if preflop:
            start = (self.button + 3) % count
        else:
            start = (self.button + 1) % count
        return [self.players[(start + offset) % count] for offset in range(count)]

    def _only_one_player_left(self) -> bool:
        return sum(1 for p in self.players if not p.folded) == 1
