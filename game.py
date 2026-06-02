"""Main Texas Hold'em game loop."""

from __future__ import annotations

from bot import BotBrain
from cards import Deck
from evaluator import HandEvaluator, HandRank
from hand_history import HandHistoryLogger
from player import Player
from table import Table
from ui import ConsoleUI


class TexasHoldemGame:
    def __init__(
        self, players: list[Player], small_blind: int = 5, big_blind: int = 10
    ) -> None:
        if len(players) < 2:
            raise ValueError("There must be at least 2 players to start the game.")
        self.players = players
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.table = Table()
        self.evaluator = HandEvaluator()
        self.ui = ConsoleUI()
        self.hand_number = 0
        self.history = HandHistoryLogger()
        self.bot_brain = BotBrain(simulations=1000)
        message = "Welcome to the Premium Poker Suite! We pride ourselves on providing a secure, professional, and exhilarating card-playing environment. We highly encourage you to play strategically, master your poker face, and execute daring bluffs! It really makes the mathematically unavoidable process of our algorithm politely absorbing your entire net worth so much more entertaining for everyone involved. Good luck, and may the odds be entirely in our favor!"
        self.ui.show_message(message)

    def play_hand(self) -> None:
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
        self._betting_round("Pre-Flop")
        self._deal_community(deck, 3, "Flop")
        self._betting_round("Flop")
        self._deal_community(deck, 1, "Turn")
        self._betting_round("Turn")
        self._deal_community(deck, 1, "River")
        self._betting_round("River")
        self._showdown()

    def _commit(self, player: Player, wager: int) -> None:
        # Single choke point for chips entering the pot: keeps table.pot and the
        # per-player contribution map (used for side pots) perfectly in sync.
        self.table.add_to_pot(wager)
        self.contributions[player.name] += wager

    def _post_blinds(self) -> None:
        if len(self.players) < 2:
            raise ValueError("There must be at least 2 players to post blinds.")
        actual_small = self.players[0].bet(self.small_blind)
        self._commit(self.players[0], actual_small)
        actual_big = self.players[1].bet(self.big_blind)
        self._commit(self.players[1], actual_big)

        self.history.log_action(self.players[0].name, "small_blind", actual_small, "Pre-Flop")
        self.history.log_action(self.players[1].name, "big_blind", actual_big, "Pre-Flop")

        print(
            f"{self.players[0].name} posts {actual_small}; {self.players[1].name} posts {actual_big}"
        )
        print()  # Add an extra line for better readability

    def _show_players_chips(self) -> None:
        for player in self.players:
            print(f"{player.name}: {player.chips} chips")
        print()

    def _show_human_cards(self) -> None:
        for player in self.players:
            if player.is_human:
                self.ui.show_player(player)
                print()

    def _deal_community(self, deck: Deck, count: int, street: str) -> None:
        if self._only_one_player_left():
            return
        new_cards = deck.draw(count)
        self.table.community_cards.extend(new_cards)

        self.history.log_community_cards(street, new_cards)

        print()
        print(f"-- {street} --")
        self.ui.show_table(self.table.community_cards, self.table.pot)
        print()

    def _betting_round(self, street: str) -> None:
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

            for player in self.players:
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

                if player.is_human:
                    self.ui.show_table(self.table.community_cards, self.table.pot)
                    self.ui.show_player(player)
                    action = self.ui.ask_action(player, call_amount, allow_raise)
                else:
                    action = self._bot_action(player, call_amount)
                    if action == "raise" and not allow_raise:
                        action = "call"

                acted.add(player.name)

                if action == "fold":
                    player.folded = True
                    self.history.log_action(player.name, "fold", 0, street)
                    self.ui.show_message(f"{player.name} folds.")
                    continue

                if action == "call":
                    wager = player.bet(call_amount)
                    self._commit(player, wager)
                    if call_amount == 0:
                        self.history.log_action(player.name, "check", 0, street)
                        self.ui.show_message(f"{player.name} checks.")
                    else:
                        self.history.log_action(player.name, "call", wager, street)
                        suffix = " (all in)" if player.chips == 0 else ""
                        self.ui.show_message(f"{player.name} calls {wager}{suffix}.")
                    continue

                if action == "all in":
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
                    continue

                # action == "raise"
                max_increment = player.chips - call_amount
                if max_increment <= 0:
                    # Can't afford a full call plus any raise on top — this is at
                    # best an all-in short call. Put in whatever is left.
                    wager = player.bet(call_amount)
                    self._commit(player, wager)
                    self.history.log_action(player.name, "call", wager, street)
                    suffix = " (all in)" if player.chips == 0 else ""
                    self.ui.show_message(f"{player.name} calls {wager}{suffix}.")
                    continue

                min_increment = last_raise_size
                if player.is_human:
                    if min_increment > max_increment:
                        # Not enough for a full legal raise; the only raise
                        # available is an all-in for less.
                        increment = max_increment
                    else:
                        increment = self.ui.ask_raise_amount(min_increment, max_increment)
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

        for player in self.players:
            player.current_bet = 0

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
        # winner in seating order (left of the dealer button).
        if remainder:
            first = min(winners, key=lambda p: self.players.index(p))
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

    def _only_one_player_left(self) -> bool:
        return sum(1 for p in self.players if not p.folded) == 1
