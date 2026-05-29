"""Standalone tests for BotBrain.

Plain Python assertions, no test framework. Run with:  python test_bot.py
Imports only from cards.py, evaluator.py, and bot.py - never from game.py,
table.py, or ui.py, so BotBrain is exercised in complete isolation.
"""

from cards import Card, Rank, Suit
from evaluator import HandEvaluator
from bot import BotBrain


def c(rank: Rank, suit: Suit) -> Card:
    return Card(rank, suit)


# Higher simulation count than production for tighter probability estimates.
bot = BotBrain(simulations=2000)


def test_1() -> None:
    hole = [c(Rank.ACE, Suit.SPADES), c(Rank.ACE, Suit.HEARTS)]
    community = []
    prob = bot._estimate_win_probability(hole, community, num_opponents=1)
    assert prob > 0.65, f"Pocket Aces pre-flop should win >65%, got {prob:.2%}"
    print(f"PASS  Test 1 - Pocket Aces pre-flop win prob: {prob:.2%}")


def test_2() -> None:
    hole = [c(Rank.SEVEN, Suit.CLUBS), c(Rank.TWO, Suit.DIAMONDS)]
    community = []
    prob = bot._estimate_win_probability(hole, community, num_opponents=1)
    assert prob < 0.40, f"7-2 offsuit pre-flop should win <40%, got {prob:.2%}"
    print(f"PASS  Test 2 - 7-2 offsuit pre-flop win prob: {prob:.2%}")


def test_3() -> None:
    hole = [c(Rank.NINE, Suit.SPADES), c(Rank.TEN, Suit.SPADES)]
    community = [
        c(Rank.JACK, Suit.SPADES),
        c(Rank.QUEEN, Suit.SPADES),
        c(Rank.KING, Suit.SPADES),
        c(Rank.TWO, Suit.CLUBS),
        c(Rank.THREE, Suit.DIAMONDS),
    ]
    prob = bot._estimate_win_probability(hole, community, num_opponents=1)
    assert prob > 0.95, f"Straight flush on river should win >95%, got {prob:.2%}"
    print(f"PASS  Test 3 - Straight flush on river win prob: {prob:.2%}")


def test_4() -> None:
    hole = [c(Rank.ACE, Suit.SPADES), c(Rank.ACE, Suit.HEARTS)]
    community = [
        c(Rank.TWO, Suit.CLUBS),
        c(Rank.SEVEN, Suit.DIAMONDS),
        c(Rank.JACK, Suit.HEARTS),
    ]
    action = bot.decide(
        hole_cards=hole,
        community_cards=community,
        pot=200,
        call_amount=20,
        player_chips=500,
        position_index=1,
        total_active_players=2,
    )
    assert action in ("call", "raise"), (
        f"Strong hand with good pot odds should not fold, got {action}"
    )
    print(f"PASS  Test 4 - Strong hand good pot odds: action={action}")


def test_5() -> None:
    hole = [c(Rank.SEVEN, Suit.CLUBS), c(Rank.TWO, Suit.DIAMONDS)]
    community = [
        c(Rank.ACE, Suit.SPADES),
        c(Rank.KING, Suit.HEARTS),
        c(Rank.QUEEN, Suit.CLUBS),
    ]
    action = bot.decide(
        hole_cards=hole,
        community_cards=community,
        pot=30,
        call_amount=100,
        player_chips=500,
        position_index=0,
        total_active_players=2,
    )
    assert action == "fold", (
        f"Weak hand with terrible pot odds should fold, got {action}"
    )
    print(f"PASS  Test 5 - Weak hand terrible pot odds: action={action}")


def test_6() -> None:
    hole = [c(Rank.ACE, Suit.HEARTS), c(Rank.KING, Suit.HEARTS)]
    community = [
        c(Rank.TWO, Suit.HEARTS),
        c(Rank.SEVEN, Suit.HEARTS),
        c(Rank.JACK, Suit.HEARTS),
    ]
    action = bot.decide(
        hole_cards=hole,
        community_cards=community,
        pot=100,
        call_amount=0,
        player_chips=500,
        position_index=1,
        total_active_players=2,
    )
    assert action == "raise", f"Made flush with free action should raise, got {action}"
    print(f"PASS  Test 6 - Made flush free action: action={action}")


def test_7() -> None:
    hole = [c(Rank.KING, Suit.SPADES), c(Rank.KING, Suit.HEARTS)]
    community = []
    prob = bot._estimate_win_probability(hole, community, num_opponents=3)
    assert prob > 0.45, f"Pocket Kings vs 3 opponents should win >45%, got {prob:.2%}"
    print(f"PASS  Test 7 - Pocket Kings vs 3 opponents win prob: {prob:.2%}")


def test_8() -> None:
    hole = [c(Rank.EIGHT, Suit.SPADES), c(Rank.NINE, Suit.HEARTS)]
    community = [
        c(Rank.TEN, Suit.CLUBS),
        c(Rank.JACK, Suit.DIAMONDS),
        c(Rank.TWO, Suit.SPADES),
    ]

    early = bot.decide(
        hole_cards=hole,
        community_cards=community,
        pot=80,
        call_amount=30,
        player_chips=300,
        position_index=0,
        total_active_players=4,
    )

    late = bot.decide(
        hole_cards=hole,
        community_cards=community,
        pot=80,
        call_amount=30,
        player_chips=300,
        position_index=3,
        total_active_players=4,
    )

    print(f"INFO  Test 8 - Position effect: early={early}, late={late}")
    print("PASS  Test 8 - Position test ran without error")


if __name__ == "__main__":
    print("Running BotBrain tests...\n")

    tests = [test_1, test_2, test_3, test_4, test_5, test_6, test_7, test_8]
    failures = 0

    for test in tests:
        try:
            test()
        except AssertionError as error:
            failures += 1
            print(f"FAIL  {test.__name__} - {error}")

    if failures:
        print(f"\n{failures} test(s) failed.")
        raise SystemExit(1)

    print("\nAll tests passed.")
