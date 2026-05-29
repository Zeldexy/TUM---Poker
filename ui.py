"""Console input/output helpers."""

from __future__ import annotations

from cards import Card, Deck
from player import Player

message = "Welcome to the Premium Poker Suite! We pride ourselves on providing a secure, professional, and exhilarating card-playing environment. We highly encourage you to play strategically, master your poker face, and execute daring bluffs! It really makes the mathematically unavoidable process of our algorithm politely absorbing your entire net worth so much more entertaining for everyone involved. Good luck, and may the odds be entirely in our favor!"


class ConsoleUI: 

    def format_cards(self, cards: list[Card]) -> str:
        return " ".join(str(card) for card in cards)

    def show_table(self, community_cards: list[Card], pot: int) -> None:
        string_cards = self.format_cards(community_cards)
        if string_cards == "":
            string_cards = "empty"
        print(f"Community Cards: {string_cards}")
        print(f"Pot: {pot}")


    def show_player(self, player: Player) -> None:
        # TODO: Task 2 - display the player's name, hole cards, and chip count in a clear format.
        print(f"Player: {player.name}")
        if player.hole_cards != []:
            print(f"Hole Cards: {self.format_cards(player.hole_cards)}")
        else:
            print("Hole Cards: None")
        print(f"Chips: {player.chips}")

    
    def ask_action(self, player: Player, call_amount: int) -> str:
        action = input(f"{player.name}, you need to call {call_amount} chips. Do you want to call/check, raise, or fold? ").strip().lower()
        if action in ["c", "call", "check"]:
            return 'call'
        
        elif action in ["r", "raise"]:
            return 'raise'
        
        elif action in ["f", "fold"]:
            return 'fold'
        
        else:
            print("Invalid action. Please enter 'call', 'raise', or 'fold'.")
            return self.ask_action(player, call_amount)
        


    def ask_raise_amount(self, minimum: int, maximum: int) -> int:
        while True:
            try:
                raise_amount = int(input(f"Enter raise amount (between {minimum} and {maximum}): "))
                if minimum <= raise_amount <= maximum:
                    return raise_amount
                else:
                    print(f"Invalid amount. Please enter a number between {minimum} and {maximum}.")
                    continue
            except ValueError:
                print("Invalid input. Please enter a valid integer.")
                continue

    def show_message(self, message: str) -> None:
        print(message)
        print()  # Add an extra line for better readability
    
