"""Main Texas Hold'em game loop."""

from __future__ import annotations

from bot import BotBrain
from cards import Deck
from evaluator import HandEvaluator
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
        self.bot_brain = BotBrain(simulations=1000)
        message = "Welcome to the Premium Poker Suite! We pride ourselves on providing a secure, professional, and exhilarating card-playing environment. We highly encourage you to play strategically, master your poker face, and execute daring bluffs! It really makes the mathematically unavoidable process of our algorithm politely absorbing your entire net worth so much more entertaining for everyone involved. Good luck, and may the odds be entirely in our favor!"
        self.ui.show_message(message)

    def play_hand(self) -> None:
        deck = Deck()
        self.table.reset()

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

    def _post_blinds(self) -> None:
        if len(self.players) < 2:
            raise ValueError("There must be at least 2 players to post blinds.")
        actual_small = self.players[0].bet(self.small_blind)
        actual_big = self.players[1].bet(self.big_blind)
        self.table.add_to_pot(actual_small + actual_big)
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
                print()  # Add an extra line for better readability

    def _deal_community(self, deck: Deck, count: int, street: str) -> None:
        if self._only_one_player_left():
            return
        new_cards = deck.draw(count)
        self.table.community_cards.extend(new_cards)
        print()  # Add an extra line for better readability
        print(f"-- {street} --")
        self.ui.show_table(self.table.community_cards, self.table.pot)
        print()  # Add an extra line for better readability

    def _betting_round(self, street: str) -> None:
        if self._only_one_player_left():
            return

        highest_bet = max(p.current_bet for p in self.players)
        acted = set()

        while True:
            # A player is settled if they folded, are all-in, or have acted and matched the highest bet
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

                # Skip if this player already acted and matches the highest bet
                if player.name in acted and call_amount == 0:
                    continue

                # Check if the player is a human or a bot
                if player.is_human:
                    self.ui.show_table(self.table.community_cards, self.table.pot)
                    self.ui.show_player(player)
                    action = self.ui.ask_action(player, call_amount)
                else:
                    action = self._bot_action(player, call_amount)

                acted.add(player.name)

                # Check the action chosen
                if action == "fold":
                    player.folded = True
                    self.ui.show_message(f"{player.name} folds.")

                elif action == "call":
                    wager = player.bet(call_amount)
                    self.table.add_to_pot(wager)
                    if call_amount == 0:
                        self.ui.show_message(f"{player.name} checks.")
                    else:
                        self.ui.show_message(f"{player.name} calls {wager}.")

                elif action == "raise":
                    minimum = call_amount + self.big_blind
                    maximum = player.chips
                    if player.is_human:
                        raise_amount = self.ui.ask_raise_amount(minimum, maximum)
                    else:
                        # Bots must size their own raise. Never prompt the
                        # console here or the human gets asked to type in a
                        # bot's raise amount.
                        raise_amount = self._bot_raise_amount(minimum, maximum)
                    wager = player.bet(call_amount + raise_amount)
                    self.table.add_to_pot(wager)
                    highest_bet = player.current_bet
                    self.ui.show_message(f"{player.name} raises by {raise_amount}.")

                elif action == "all in":
                    wager = player.all_in()
                    self.table.add_to_pot(wager)
                    if player.current_bet > highest_bet:
                        highest_bet = player.current_bet
                    self.ui.show_message(f"{player.name} goes all in for {wager}!")

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

    def _bot_raise_amount(self, minimum: int, maximum: int) -> int:
        # Bots raise a fixed, modest size: the minimum legal raise. When they
        # cannot afford even that, they shove whatever chips remain (all-in).
        if maximum < minimum:
            return maximum
        return minimum

    def _showdown(self) -> None:
        # Scenario 1: everyone else folded, last player wins
        if self._only_one_player_left():
            winner = [p for p in self.players if not p.folded][0]
            winner.chips += self.table.pot
            self.ui.show_message(
                f"{winner.name} wins {self.table.pot} chips (everyone else folded)."
            )
            return

        # Scenario 2: evaluate hands of all remaining players
        remaining = [p for p in self.players if not p.folded]
        player_ranks = []
        for player in remaining:
            cards = player.hole_cards + self.table.community_cards
            rank = self.evaluator.best_rank(cards)
            player_ranks.append((player, rank))
            self.ui.show_message(
                f"{player.name}: {self.ui.format_cards(player.hole_cards)} - {rank}"
            )

        # Find the best hand
        best_rank = max(rank for _, rank in player_ranks)

        # Collect all players who tied for the best hand
        winners = [p for p, rank in player_ranks if rank == best_rank]

        # Split the pot among winners
        share = self.table.pot // len(winners)
        for winner in winners:
            winner.chips += share

        if len(winners) == 1:
            self.ui.show_message(
                f"{winners[0].name} wins {self.table.pot} chips with {best_rank}!"
            )
        else:
            names = ", ".join(w.name for w in winners)
            self.ui.show_message(
                f"Tie! {names} split the pot ({share} chips each) with {best_rank}."
            )

    def _only_one_player_left(self) -> bool:
        return sum(1 for p in self.players if not p.folded) == 1
