"""Run the CLI Texas Hold'em starter game."""

from game import TexasHoldemGame
from player import Player
from stats import StatsDashboard


def main() -> None:
    players = [
        Player("You", chips=1_000, is_human=True),
        Player("Ada Bot", chips=1_000),
        Player("Grace Bot", chips=1_000),
    ]

    game = TexasHoldemGame(players)

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

