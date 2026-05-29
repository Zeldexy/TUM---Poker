# CLAUDE.md — Texas Hold'em Poker (Python)

## How to Use This File
Read this file fully at the start of every session. It is the single source of truth for this codebase.
Do NOT scan the entire project on every task. Use the Module Map to navigate directly to the file relevant to the current task. Only open files that are directly touched by what you are doing.

---

## Project Status
ALL FILES ARE FULLY IMPLEMENTED AND WORKING.
The game runs end-to-end in the terminal via a console UI.
No file is a stub or placeholder. Do not rewrite, restructure, or second-guess existing implementations unless explicitly asked.

---

## Project Overview

A terminal-based Texas Hold'em poker game written in pure Python (standard library only).
Single package. No third-party dependencies. No GUI. No networking. No async.

- Entry point: game.py -> TexasHoldemGame
- Python version: 3.10+ (int | None union syntax)
- All internal imports: relative (from .cards import Card, etc.)
- UI: console only via ConsoleUI in ui.py using input() and print()

---

## Module Map

| File         | Single Responsibility                        | Imports From                   |
|--------------|----------------------------------------------|-------------------------------|
| cards.py     | Card primitives: Suit, Rank, Card, Deck      | nothing (stdlib only)         |
| player.py    | Player state, chip management, betting       | cards.py                      |
| table.py     | Community cards, pot tracking                | cards.py                      |
| evaluator.py | Hand ranking engine, 5-card evaluation       | cards.py                      |
| ui.py        | Console I/O, display, input validation       | cards.py, player.py           |
| game.py      | Game loop, hand orchestration, all game rules| all of the above              |

Ripple risk: cards.py is the root dependency. Any change there can affect all other files.
evaluator.py and table.py are the most isolated.
ui.py never makes game decisions.
game.py never formats strings directly.

---

## Implemented Classes and Interfaces

### cards.py

Suit(IntEnum)
Represents the four suits as integers for comparison and iteration.
  CLUBS=0, DIAMONDS=1, HEARTS=2, SPADES=3
  .symbol -> str    returns 'C', 'D', 'H', 'S'

Rank(IntEnum)
Represents card values 2-14 where 14 is Ace high. Integer value is used directly in hand evaluation.
  TWO=2, THREE=3, ..., TEN=10, JACK=11, QUEEN=12, KING=13, ACE=14
  .label -> str     returns '2'..'9', 'T', 'J', 'Q', 'K', 'A'
  Ten is labelled 'T' so every card has a clean 2-character string (e.g. TH, AH).

Card  @dataclass(frozen=True)
Immutable value object. Hashable. Can be used in sets and as dict keys.
  rank: Rank
  suit: Suit
  __str__() -> str    rank.label + suit.symbol, e.g. 'AH', '7C'

Deck
Creates all 52 cards via nested loop over Suit x Rank and shuffles immediately on __init__.
  _cards: list[Card]               internal, shuffled, 52 cards on init
  draw(count: int = 1) -> list[Card]
    Pops count cards from _cards and returns them as a list.
    Raises ValueError if count < 1 or count > remaining cards.
    Uses .pop() so the same card can never be drawn twice.

---

### player.py

Player  @dataclass
Central state object for one player. Passed by reference throughout the game.
  name: str
  chips: int
  is_human: bool = False
  hole_cards: list[Card] = field(default_factory=list)
  current_bet: int = 0
  folded: bool = False

  reset_for_hand() -> None
    Clears hole_cards with .clear(), resets current_bet=0, folded=False.
    Chips are NOT reset — they persist across hands.

  receive(cards: list[Card]) -> None
    Extends hole_cards with the given list. Uses .extend(), not .append().

  bet(amount: int) -> int
    Raises ValueError if amount < 0.
    Actual wager = min(amount, self.chips)  — enforces all-in, never negative chips.
    Deducts wager from chips. Adds wager to current_bet.
    Returns the actual wager. Caller is responsible for adding it to the pot.

  active -> bool  @property
    True if not folded AND chips > 0.

---

### table.py

Table  @dataclass
Stores shared state visible to all players during a hand.
  community_cards: list[Card] = field(default_factory=list)
  pot: int = 0

  reset() -> None
    community_cards.clear() — uses .clear(), does NOT reassign to a new list.
    pot = 0

  add_to_pot(amount: int) -> None
    Raises ValueError if amount < 0.
    pot += amount

---

### evaluator.py

HandCategory(IntEnum)
Nine hand ranks as comparable integers. Higher integer = stronger hand.
  HIGH_CARD=0, ONE_PAIR=1, TWO_PAIR=2, THREE_OF_A_KIND=3,
  STRAIGHT=4, FLUSH=5, FULL_HOUSE=6, FOUR_OF_A_KIND=7, STRAIGHT_FLUSH=8

HandRank  @dataclass(frozen=True, order=True)
Comparable value object. order=True means Python auto-generates lt, gt, eq from field order.
  category: HandCategory       compared first
  tiebreakers: tuple[int, ...] compared second, element by element
  label -> str  @property      category.name.replace("_", " ").title()

Tiebreaker tuple ordering — strongest deciding value must always come first:
  STRAIGHT_FLUSH / STRAIGHT  : (high_card,)
  FOUR_OF_A_KIND             : (quad_rank, kicker)
  FULL_HOUSE                 : (trips_rank, pair_rank)
  FLUSH / HIGH_CARD          : (rank1, rank2, rank3, rank4, rank5) descending
  THREE_OF_A_KIND            : (trips_rank, kicker1, kicker2)
  TWO_PAIR                   : (high_pair, low_pair, kicker)
  ONE_PAIR                   : (pair_rank, kicker1, kicker2, kicker3)

HandEvaluator
Stateless service. No __init__. No stored state. Never add instance variables.

  best_rank(cards: list[Card]) -> HandRank
    Raises ValueError if len(cards) < 5.
    Generates all C(n,5) 5-card combos via combinations(cards, 5).
    Returns max(HandRank) across all combos.
    In Texas Hold'em called with 7 cards (2 hole + 5 community).

  _rank_five(cards: list[Card]) -> HandRank   (private)
    Evaluates exactly 5 cards.
    Pipeline:
      1. Extract ranks sorted descending
      2. Counter(ranks) to count duplicates
      3. Sort groups as (count, rank) descending
      4. is_flush = all suits equal
      5. straight_high = _straight_high(ranks) or None
      6. Return HandRank by priority: SF > 4K > FH > F > S > 3K > 2P > 1P > HC

  _straight_high(ranks: list[int]) -> int | None   (private)
    Deduplicates ranks first — a paired board cannot form a straight.
    Special case: {14,2,3,4,5} is a wheel straight, returns 5 not 14.
    Checks all windows of 5 consecutive descending values.
    Returns highest card of the straight, or None if no straight exists.

---

### ui.py

ConsoleUI
Pure I/O layer. No game logic. No state.
All methods either print to console or return a validated value from the user.
Never import from game.py, table.py, or evaluator.py — only knows Card and Player.

  show_table(community_cards: list[Card], pot: int) -> None
    Prints "Board: AH KD 7S" or "Board: (empty)" when no cards are present.
    Prints "Pot: 120"

  show_player(player: Player) -> None
    Prints player name, hole cards, and remaining chips.

  ask_action(player: Player, call_amount: int) -> str
    Loops with while True until valid input is received.
    Normalises input with .strip().lower() before comparing.
    'c', 'call', 'check'  ->  returns 'call'
    'r', 'raise'          ->  returns 'raise'
    'f', 'fold'           ->  returns 'fold'
    Any other input repeats the prompt.

  ask_raise_amount(minimum: int, maximum: int) -> int
    Loops until valid input received.
    Handles non-numeric input with try/except ValueError and continues the loop.
    Validates minimum <= amount <= maximum before returning.

  show_message(message: str) -> None
    Plain print().

  format_cards(cards: list[Card]) -> str
    Returns all cards as a space-joined string: "AH KD 7S"
    Uses str(card) which calls Card.__str__()

---

### game.py

TexasHoldemGame
Top-level orchestrator. Owns the game loop. Delegates everything to the other modules.

  __init__(players: list[Player], small_blind: int = 5, big_blind: int = 10)
    Raises ValueError if len(players) < 2.
    Creates: self.table (Table), self.evaluator (HandEvaluator), self.ui (ConsoleUI)
    Stores: self.players, self.small_blind, self.big_blind

  play_hand() -> None
    Orchestrates one full hand. See Game Flow section below.

  _post_blinds() -> None
    players[0].bet(small_blind) — amount added to pot.
    players[1].bet(big_blind)   — amount added to pot.
    Prints "[name] posts [amount]; [name] posts [amount]".

  _show_human_cards() -> None
    Iterates all players. Calls ui.show_player() only if player.is_human is True.

  _deal_community(deck: Deck, count: int, street: str) -> None
    Returns immediately if _only_one_player_left() is True.
    Extends table.community_cards with deck.draw(count).
    Calls ui.show_message() with the street name.

  _betting_round(street: str) -> None
    For each player — skips folded players:
      call_amount = max current_bet across all players - this player's current_bet
      if player.is_human -> ui.ask_action()
      else               -> _bot_action()
      'fold'  -> player.folded = True
      'call'  -> player.bet(call_amount); table.add_to_pot(wager returned)
      'raise' -> ui.ask_raise_amount(); player.bet(amount); table.add_to_pot(wager returned)
      Breaks early if _only_one_player_left()
    Resets current_bet = 0 for ALL players at end of round.

  _bot_action(player: Player, call_amount: int) -> str
    if call_amount > player.chips // 2  ->  returns 'fold'
    else                                ->  returns 'call'

  _showdown() -> None
    Evaluates only players where not player.folded.
    For each: evaluator.best_rank(player.hole_cards + table.community_cards)
    Finds winner(s) by max HandRank.
    Splits pot evenly on tie using integer division.
    Displays winner name, hand label, and cards via ui.show_message().

  _only_one_player_left() -> bool
    Returns True if the count of non-folded players is <= 1.

---

## Game Flow — One Complete Hand

play_hand()
  Deck()                               new shuffled deck
  table.reset()                        clear board and pot
  player.reset_for_hand() for all      clear cards, bets, folded state — chips persist
  deck.draw(2) for each player         deal hole cards via player.receive()
  _post_blinds()                       players[0]=SB, players[1]=BB
  _show_human_cards()                  reveal hole cards to human players only
  _betting_round('Pre-Flop')
  _deal_community(deck, 3, 'Flop')     then _betting_round('Flop')
  _deal_community(deck, 1, 'Turn')     then _betting_round('Turn')
  _deal_community(deck, 1, 'River')    then _betting_round('River')
  _showdown()

Both _deal_community and _betting_round short-circuit if _only_one_player_left() is True.

---

## Architecture Rules — Do Not Break These

IMMUTABILITY
Card and HandRank are frozen dataclasses. Never set attributes on them after creation.

MUTABLE DEFAULTS
hole_cards (Player) and community_cards (Table) use field(default_factory=list).
Never change these to = [] — that causes all instances to share the same list object.

LIST MUTATION
Use .clear() to empty lists. Never reassign self.hole_cards = [] or self.community_cards = [].
Reassignment breaks existing references held by other parts of the code.

CHIP SAFETY
Player.bet() uses min(amount, self.chips). Chips can never go negative.
current_bet tracks chips bet in the current round only. It resets to 0 at end of every _betting_round().

RETURN VALUE FROM bet()
bet() returns the actual wager which may be less than requested due to chip limits.
The caller (_betting_round, _post_blinds) must pass this return value to table.add_to_pot().
Never assume wager equals the requested amount.

EVALUATOR PURITY
HandEvaluator has no state. It must remain a stateless service.
Never add instance variables or session state to it.

UI ISOLATION
ui.py only imports Card and Player. It must never import from game.py, table.py, or evaluator.py.

SHOWDOWN SCOPE
_showdown() only evaluates players where not player.folded.
Never pass a folded player's cards to the evaluator.

---

## Known Edge Cases — Already Handled Correctly

Wheel straight (A-2-3-4-5)
  Ace plays low. _straight_high returns 5, not 14.

Duplicate ranks in straight check
  _straight_high deduplicates ranks before checking consecutive windows.

All-in
  bet() automatically caps at available chips. No separate all-in state or method is needed.

Tie / split pot
  _showdown() handles multiple winners with equal HandRank. Pot is split with integer division.

One player left early
  Community cards stop being dealt. Betting stops. Remaining player takes pot uncontested.

Empty board display
  show_table() prints (empty) when community_cards list is empty.

Invalid console input
  ask_action() and ask_raise_amount() loop indefinitely until valid input is provided.

---

## Coding Standards — Match Existing Style

- Type hints on every method signature using built-in generics: list[Card], int | None
- Guard clauses at the top of methods — validate inputs before doing any work
- ValueError for all invalid input: negative amounts, wrong counts, too few cards
- Catch except ValueError specifically — no bare except:
- Descriptive variable names: call_amount, community_cards, straight_high — no abbreviations
- Private helpers prefixed with underscore: _rank_five, _bot_action, _only_one_player_left
- Comments explain WHY, not WHAT — never restate what the code already says

---

## Out of Scope — Do Not Add Without Explicit Discussion

- No persistence or save state between sessions
- No GUI or web interface
- No networking or remote multiplayer
- No async or threading
- No third-party packages
- No tournament bracket or multi-table logic
- No player statistics tracking across sessions
