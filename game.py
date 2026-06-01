"""Main Texas Hold'em game loop."""

from __future__ import annotations
from hand_history import HandHistoryLogger

from cards import Deck
from evaluator import HandEvaluator
from player import Player
from table import Table
from ui import ConsoleUI


class TexasHoldemGame:
    def __init__(self, players: list[Player], small_blind: int = 5, big_blind: int = 10) -> None:
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

    def play_hand(self) -> None:
        self.hand_number += 1
        self.history.start_hand(self.hand_number, self.players)

        deck = Deck()
        self.table.reset()

        for player in self.players:
            player.reset_for_hand()
        for player in self.players:
            hole_cards = deck.draw(2)
            player.receive(hole_cards)
        self._post_blinds()
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
        self.players[0].bet(self.small_blind)
        self.players[1].bet(self.big_blind)
        self.table.pot += self.small_blind + self.big_blind

        self.history.log_action(self.players[0].name, "small_blind", self.small_blind, "Pre-Flop")
        self.history.log_action(self.players[1].name, "big_blind", self.big_blind, "Pre-Flop")

        print(f"{self.players[0].name} posts {self.small_blind}; {self.players[1].name} posts {self.big_blind}")
        print()  # Add an extra line for better readability

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

        self.history.log_community_cards(street, new_cards)

        print()  # Add an extra line for better readability
        print(f"-- {street} --")
        self.ui.show_table(self.table.community_cards, self.table.pot)
        print()  # Add an extra line for better readability

    def _betting_round(self, street: str) -> None:
        # TODO: Task 6 - implement the betting round for the specified street, where each
        # active player can choose to fold, call, or raise -> ensure that each action works
        # NOTE: this is a big task
        if self._only_one_player_left():
            return

        if street != "Pre-Flop":
            for player in self.players:
                player.current_bet = 0

        current_bet = 0

        if street == "Pre-Flop":
            current_bet = self.big_blind

        players_who_acted = set()

        while True:
            round_complete = True

            for player in self.players:
                if self._only_one_player_left():
                    return

                if not player.active:
                    continue

                call_amount = current_bet - player.current_bet

                if call_amount < 0:
                    call_amount = 0

                if player.current_bet < current_bet or player.name not in players_who_acted:
                    round_complete = False

                    print(f"-- {street} betting --")
                    print(f"Pot: {self.table.pot}")
                    print(f"{player.name}'s chips: {player.chips}")
                    print(f"Current bet to match: {current_bet}")
                    print(f"{player.name}'s current bet: {player.current_bet}")
                    print()

                    if player.is_human:
                        while True:
                            if call_amount == 0:
                                action = input(f"{player.name}, choose action (check / bet / fold): ").lower().strip()
                            else:
                                action = input(f"{player.name}, choose action (call / raise / fold): ").lower().strip()

                            if action in ["check", "bet", "call", "raise", "fold"]:
                                break

                            print("Invalid action.")

                    else:
                        action = self._bot_action(player, call_amount)
                        print(f"{player.name} chooses to {action}.")

                    if action == "fold":
                        player.folded = True
                        self.history.log_action(player.name, "fold", 0, street)
                        players_who_acted.add(player.name)
                        print(f"{player.name} folds.")
                        print()
                        continue

                    if action == "check":
                        if call_amount > 0:
                            print("You cannot check. You need to call, raise, or fold.")
                            continue

                        self.history.log_action(player.name, "check", 0, street)
                        players_who_acted.add(player.name)
                        print(f"{player.name} checks.")
                        print()
                        continue

                    if action == "call":
                        if call_amount == 0:
                            self.history.log_action(player.name, "check", 0, street)
                            players_who_acted.add(player.name)
                            print(f"{player.name} checks.")
                            print()
                            continue

                        if call_amount > player.chips:
                            print(f"{player.name} does not have enough chips to call.")
                            player.folded = True
                            self.history.log_action(player.name, "fold", 0, street)
                            players_who_acted.add(player.name)
                            print(f"{player.name} folds.")
                            print()
                            continue

                        player.bet(call_amount)
                        self.table.pot += call_amount

                        self.history.log_action(player.name, "call", call_amount, street)
                        players_who_acted.add(player.name)
                        print(f"{player.name} calls {call_amount}.")
                        print()
                        continue

                    if action == "bet":
                        if call_amount > 0:
                            print("You cannot bet because there is already a bet. Choose call, raise, or fold.")
                            continue

                        if player.is_human:
                            while True:
                                try:
                                    bet_amount = int(input("Enter bet amount: "))
                                    if bet_amount > 0 and bet_amount <= player.chips:
                                        break
                                    print("Invalid bet amount.")
                                except ValueError:
                                    print("Please enter a number.")
                        else:
                            bet_amount = min(self.big_blind, player.chips)

                        player.bet(bet_amount)
                        self.table.pot += bet_amount
                        current_bet = player.current_bet

                        self.history.log_action(player.name, "bet", bet_amount, street)
                        players_who_acted = {player.name}
                        print(f"{player.name} bets {bet_amount}.")
                        print()
                        continue

                    if action == "raise":
                        if player.is_human:
                            while True:
                                try:
                                    raise_amount = int(input("Enter total raise amount: "))
                                    if raise_amount > current_bet and raise_amount <= player.current_bet + player.chips:
                                        break
                                    print("Invalid raise amount.")
                                except ValueError:
                                    print("Please enter a number.")
                        else:
                            raise_amount = min(current_bet + self.big_blind, player.current_bet + player.chips)

                        amount_to_pay = raise_amount - player.current_bet

                        player.bet(amount_to_pay)
                        self.table.pot += amount_to_pay
                        current_bet = player.current_bet

                        self.history.log_action(player.name, "raise", amount_to_pay, street)
                        players_who_acted = {player.name}
                        print(f"{player.name} raises to {current_bet}.")
                        print()
                        continue

            if round_complete:
                break

    def _bot_action(self, player: Player, call_amount: int) -> str:
        # TODO: Task 7 - implement a simple bot strategy based on the
        # call amount relative to the player's chips
        if call_amount == 0:
            return "check"

        if call_amount <= self.big_blind:
            return "call"

        if call_amount <= player.chips // 10:
            return "call"

        return "fold"

    def _showdown(self) -> None:
        # TODO: Task 8 - if only one player remains, they win the pot;
        # otherwise, evaluate the hands of all active players
        # NOTE: this is a big task
        active_players = [player for player in self.players if player.active]

        if len(active_players) == 1:
            winner = active_players[0]
            winner.chips += self.table.pot

            print(f"{winner.name} wins {self.table.pot} chips.")

            self.history.finish_hand([winner.name], self.table.pot)
            return

        player_ranks = []

        for player in active_players:
            rank = self.evaluator.best_rank(player.hole_cards + self.table.community_cards)
            player_ranks.append((player, rank))

        best_rank = max(rank for player, rank in player_ranks)
        winners = [player for player, rank in player_ranks if rank == best_rank]

        split_amount = self.table.pot // len(winners)

        for winner in winners:
            winner.chips += split_amount

        if len(winners) == 1:
            print(f"{winners[0].name} wins {self.table.pot} chips with {best_rank}.")
        else:
            winner_names = ", ".join(player.name for player in winners)
            print(f"{winner_names} split the pot of {self.table.pot} chips with {best_rank}.")

        self.history.finish_hand(
            [player.name for player in winners],
            self.table.pot,
        )

    def _only_one_player_left(self) -> bool:
        active_players = [player for player in self.players if player.active]
        return len(active_players) == 1


if __name__ == "__main__":
    players = [
        Player(name="Lukas", chips=1000, is_human=True),
        Player(name="Bob", chips=1000),
        Player(name="Charlie", chips=1000),
    ]

    game = TexasHoldemGame(players)
    game.play_hand()
