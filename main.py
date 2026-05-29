"""Run the CLI Texas Hold'em starter game."""

from game import TexasHoldemGame
from player import Player


def main() -> None:
    players = [
        Player("You", chips=100, is_human=True),
        Player("Bob Bot", chips=100),
        Player("Charlie Bot", chips=100),
    ]
    game = TexasHoldemGame(players)
    # Play hands until one player remains with chips
    while sum(1 for p in players if p.chips > 0) > 1:
        game.play_hand()
    winner = [p for p in players if p.chips > 0][0]
    print(f"{winner.name} wins!")


if __name__ == "__main__":
    main()
