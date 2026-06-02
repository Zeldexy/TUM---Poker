"""Run the CLI Texas Hold'em starter game."""

from game import TexasHoldemGame
from player import Player
from stats import StatsDashboard


def main() -> None:
    players = [
        Player("You", chips=100, is_human=True),
        Player("Bob Bot", chips=100),
        Player("Charlie Bot", chips=100),
    ]

    game = TexasHoldemGame(players)

    # Play hands until a single player has chips remaining.
    while sum(1 for p in players if p.chips > 0) > 1:
        game.play_hand()

    winner = [p for p in players if p.chips > 0][0]
    print(f"{winner.name} wins!")

    # Game over: offer the post-game menu.
    while True:
        print()
        print("=== Texas Hold'em ===")
        print("1. Play hand")
        print("2. Show stats")
        print("3. Quit")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            game.play_hand()
        elif choice == "2":
            dashboard = StatsDashboard()
            dashboard.print_dashboard()
        elif choice == "3":
            print("Goodbye.")
            break
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()
