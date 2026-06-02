# CLAUDE.md — Texas Hold'em Poker (Python)

## How to Use This File
Read this file fully at the start of every session. It is the single source of truth for this codebase.
Do NOT scan the entire project on every task. Use the Module Map to navigate directly to the file relevant to the current task. Only open files that are directly touched by what you are doing.

---

## Project Status
The terminal game is fully implemented and runs end-to-end via a console UI (`python main.py`).
A FastAPI web backend (lobby + realtime multi-human play over WebSocket) is implemented on top of the
SAME game engine; console mode is preserved. The frontend is a SEPARATE microservice (not in this repo)
and integrates via the contract in `backend/API.md`. See "Web / GUI Architecture" below.
Do not rewrite working implementations unless explicitly asked.

---

## Project Overview

A terminal-based Texas Hold'em poker game written in pure Python (standard library only) for the game core.
The game core has no third-party dependencies. The optional web backend adds FastAPI/uvicorn but the core
modules (cards, player, table, evaluator, bot, game) stay stdlib-only.

- Console entry point: main.py -> TexasHoldemGame (game.py)
- Python version: 3.10+ (int | None union syntax)
- All internal imports are absolute (from cards import Card, etc.) — the project runs as flat scripts
  (python main.py), not as a package. Do NOT switch to relative imports; it breaks `import bot` in tests.
- Console UI: ConsoleUI in ui.py using input() and print()

---

## Module Map

| File             | Single Responsibility                              | Imports From                |
|------------------|----------------------------------------------------|-----------------------------|
| cards.py         | Card primitives: Suit, Rank, Card, Deck            | nothing (stdlib only)       |
| player.py        | Player state, chip management, betting, all-in     | cards.py                    |
| table.py         | Community cards, pot tracking                      | cards.py                    |
| evaluator.py     | Hand ranking engine, 5-card evaluation             | cards.py                    |
| bot.py           | BotBrain: Monte-Carlo decision engine for bots     | cards.py, evaluator.py      |
| hand_history.py  | HandHistoryLogger: append hands to JSONL           | stdlib (json, datetime)     |
| stats.py         | StatsDashboard: aggregate stats from JSONL         | stdlib (json, collections)  |
| ui.py            | Console I/O, display, input validation             | cards.py, player.py         |
| game.py          | Game loop, hand orchestration, all betting rules   | all of the above            |
| main.py          | CLI menu / session loop                            | game.py, player.py, stats.py|
| test_bot.py      | Standalone assertions for BotBrain (no framework)  | cards, evaluator, bot       |

Ripple risk: cards.py is the root dependency. Any change there can affect all other files.
evaluator.py and table.py are the most isolated.
ui.py never makes game decisions. game.py owns all rules and orchestration.
hand_history.py / stats.py are decoupled via the JSONL file (`hand_history.jsonl`, gitignored).

---

## Implemented Classes and Interfaces

### cards.py

Suit(IntEnum): CLUBS=0, DIAMONDS=1, HEARTS=2, SPADES=3. `.symbol -> 'C'|'D'|'H'|'S'`.
Rank(IntEnum): TWO=2 .. ACE=14. `.label -> '2'..'9','T','J','Q','K','A'` (Ten is 'T' for 2-char cards).
Card @dataclass(frozen=True): rank, suit. `__str__()` -> e.g. 'AH', '7C', 'TS'. Hashable/immutable.
Deck: builds 52 cards (Rank x Suit) and shuffles on __init__.
  draw(count=1) -> list[Card]; pops from the end; ValueError if count<1 or count>remaining.

### player.py

Player @dataclass: name, chips, is_human=False, hole_cards=[], current_bet=0, folded=False.
  reset_for_hand(): clears hole_cards, current_bet=0, folded=False. Chips persist.
  receive(cards): hole_cards.extend(cards).
  bet(amount) -> int: ValueError if amount<0. Wager = min(amount, chips); deducts chips; adds to
    current_bet; returns the ACTUAL wager (may be capped = all-in). Caller adds it to the pot.
  all_in() -> int: returns self.bet(self.chips).
  active -> bool (property): not folded AND chips > 0.

### table.py

Table @dataclass: pot=0, community_cards=[] (field(default_factory=list)).
  reset(): community_cards.clear() (in place, no reassign); pot=0.
  add_to_pot(amount): ValueError if amount<0; pot += amount.

### evaluator.py

HandCategory(IntEnum): HIGH_CARD=0 .. STRAIGHT_FLUSH=8 (higher int = stronger).
HandRank @dataclass(frozen=True, order=True): category, tiebreakers: tuple[int, ...].
  `__str__()` -> category.name.replace("_"," ").title() (e.g. "Two Pair"). Comparable via order=True.
  Tiebreaker tuples AS CURRENTLY IMPLEMENTED (note: kickers are NOT stored for quads/trips/pairs/two-pair):
    STRAIGHT_FLUSH / STRAIGHT : (high_card,)
    FLUSH / HIGH_CARD         : full ranks sorted descending
    FOUR_OF_A_KIND            : (quad_rank,)
    FULL_HOUSE                : (trips_rank, pair_rank)
    THREE_OF_A_KIND           : (trips_rank,)
    TWO_PAIR                  : (high_pair, low_pair)
    ONE_PAIR                  : (pair_rank,)
HandEvaluator: stateless service (no __init__, no state).
  best_rank(cards) -> HandRank: ValueError if <5 cards; max over all C(n,5) combos.
  _rank_five(cards) -> HandRank (private): Counter on ranks, groups sorted by count, flush check,
    _straight_high; classifies SF > 4K > FH > F > S > 3K > 2P > 1P > HC.
  _straight_high(ranks) -> int | None (private): sorts; consecutive run of 5 -> top; wheel {2,3,4,5,14} -> 5.

### bot.py

BotBrain: pure decision logic — never prints, reads input, or mutates shared state.
  __init__(simulations=1000): stores simulations; creates one shared stateless HandEvaluator (never reassign).
  decide(hole_cards, community_cards, pot, call_amount, player_chips, position_index,
         total_active_players) -> 'fold' | 'call' | 'raise'.
    Layer 1: win probability via Monte-Carlo (_estimate_win_probability).
    Layer 2: pot_odds = call_amount/(pot+call_amount); position loosens the threshold slightly.
    Layer 3: free action -> raise if win>0.65 else call; otherwise raise if win>=0.65,
             call if win>=adjusted_threshold, else fold.
  _estimate_win_probability(hole, community, num_opponents) -> float: runs `simulations` random
    rollouts; counts STRICT wins (ties don't count); returns 0.5 if no valid iterations.
  Note: decide() never returns "all in" — only humans choose all-in via the UI/web action.

### hand_history.py

HandHistoryLogger(filename="hand_history.jsonl"): appends one JSON object per hand to a JSONL file.
  start_hand(hand_number, players): begins an in-memory record (players' names + starting chips).
  log_action(player_name, action, amount=0, street="preflop"): appends an action; no-op if no hand started.
  log_community_cards(street, cards): records dealt board cards as strings.
  finish_hand(winners: list[str], pot): records winners+pot, writes the JSON line, resets.
  Action strings logged by game.py: "small_blind", "big_blind", "fold", "check", "call", "raise", "all_in".

### stats.py

StatsDashboard(filename="hand_history.jsonl"): reads the JSONL and aggregates per player.
  load_hands() -> list[dict]; calculate_stats() -> dict[name -> counters]
    (hands_played, hands_won, total_winnings, folds, calls, raises, checks, bets,
     small_blinds, big_blinds). Note: action_map has no "all_in" key, so all-ins are not yet counted.
  print_dashboard() -> None: prints a per-player table. (A JSON-returning method is added for the web API.)

### ui.py

ConsoleUI: pure console I/O. Imports only Card/Deck and Player. Never imports game/table/evaluator.
  format_cards(cards) -> str: space-joined str(card), e.g. "AH KD 7C".
  show_table(community_cards, pot): prints "Community Cards: ..." (or "empty") and "Pot: ...".
  show_player(player): prints name, hole cards (or "None"), chips.
  ask_action(player, call_amount, allow_raise=True) -> str: blocks on input(); recurses on bad input.
    Returns 'call' (also for check), 'raise' (only if allow_raise), 'all in', or 'fold'.
    allow_raise=False hides the raise option — used when a player is only owed a call on a
    sub-minimum all-in (poker re-opening rule: they may call/fold/all-in but not raise).
  ask_raise_amount(minimum, maximum) -> int: blocks; loops until an int within [minimum, maximum].
  show_message(message): print(message) then a blank line.

### game.py

TexasHoldemGame: top-level orchestrator. Owns the game loop and ALL betting/pot rules.

  __init__(players, small_blind=5, big_blind=10): ValueError if <2 players.
    Creates table, evaluator, ui (ConsoleUI), history (HandHistoryLogger), bot_brain (BotBrain(1000)).
    hand_number=0. button = len(players)-1 so hand 1 has SB=players[0], BB=players[1].

  play_hand() -> None: orchestrates one full hand. See Game Flow.

  _commit(player, wager): table.add_to_pot(wager) AND contributions[name] += wager.
    Single choke point so the per-player contribution map stays in sync with the pot (drives side pots).

  _post_blinds(): SB at _sb_index posts small_blind, BB at _bb_index posts big_blind (capped/all-in safe
    via bet()), each via _commit. Logs blinds; prints the posting line.

  _show_players_chips() / _show_human_cards(): console display (chip stacks; human hole cards only).

  _deal_community(deck, count, street): returns early if only one player left; draws+extends the board;
    logs community cards; prints the street header and board.

  _betting_round(street): the core betting loop. Returns immediately if only one player left, or if
    fewer than 2 players can still wager (rest folded/all-in). Tracks highest_bet, last_raise_size
    (min legal raise; starts at big_blind), and `acted` (players who acted since the last full raise).
    Iterates players in `_action_order(preflop)`. Per turn:
      - skip folded / all-in; skip if already acted and nothing to call.
      - allow_raise = not already-acted (sub-minimum all-in does NOT reopen action to prior actors).
      - human -> ui.ask_action()/ui.ask_raise_amount(); bot -> _bot_action() (a bot 'raise' it isn't
        allowed becomes 'call').
      - fold / check / call (with " (all in)" suffix when capped) / all in / raise.
      - a full raise (increment >= last_raise_size) updates last_raise_size and resets `acted`.
      - highest_bet only ever rises (monotonic) so call_amount can never go negative.
    Resets every player's current_bet=0 at the end of the round.

  _bot_action(player, call_amount) -> str: builds position_index/total_active from non-folded players
    and delegates to bot_brain.decide().
  _bot_raise_increment(minimum, maximum) -> int: bots raise the minimum legal size, or shove if they
    cannot afford it.

  _showdown(): _refund_uncalled_bet() first; if only one player left they take the whole pot; otherwise
    rank all non-folded hands and award side pots.

  _refund_uncalled_bet(): if exactly one player contributed strictly more than everyone else, the
    surplus above the next-highest contribution was never called and is returned to them.

  _build_side_pots() -> list[(amount, eligible_players)]: peels the pot into layers smallest-contribution
    first; each layer = floor * participants; folded contributors are included as eligible (their chips
    stay in the pot) but cannot win.

  _merge_contested_pots(pots): collapses adjacent layers contested by the SAME set of non-folded players
    so dead money (e.g. a surrendered blind) does not show up as a bogus "side pot".

  _award_pot(amount, winners, best_rank, label): splits with integer division; the odd chip goes to the
    first winner clockwise from the button (small-blind seat first); prints the result.

  _player_by_name(name) -> Player; _only_one_player_left() -> bool (count of non-folded == 1).
  _action_order(preflop) -> list[Player]: clockwise from UTG (button+3) preflop, else from SB (button+1).
    Puts the big blind last preflop (the BB option).

  Button / blind rotation: button starts at len(players)-1. Each hand: button %= len(players);
    _sb_index=(button+1)%n; _bb_index=(button+2)%n. After the hand: button=(button+1)%n. Busted
    (0-chip) players are removed at the start of play_hand (slice assignment, keeps caller's list in sync).

### main.py

Menu-driven session loop, shown at start-up AND after every game ends:
  "=== Texas Hold'em ===" / 1. Play hand / 2. Show stats / 3. Quit.
  Option 1 plays hands until only one player has chips (then prints the winner). Option 2 prints the
  StatsDashboard. Option 3 quits. Players: "You" (human) + two bots, 100 chips each.

---

## Game Flow — One Complete Hand

play_hand()
  drop busted (0-chip) players; bail if <2 remain
  hand_number += 1; history.start_hand(...)
  rotate/derive button, _sb_index, _bb_index
  Deck(); table.reset(); contributions = {name: 0}
  reset_for_hand() for all; deal 2 hole cards each
  _post_blinds(); _show_players_chips(); _show_human_cards()
  _betting_round('Pre-Flop')
  _deal_community(3,'Flop')  then _betting_round('Flop')
  _deal_community(1,'Turn')  then _betting_round('Turn')
  _deal_community(1,'River') then _betting_round('River')
  _showdown()
  button advances one seat; print a separator (2 blank lines, 40 dashes, 2 blank lines)

_deal_community and _betting_round short-circuit when _only_one_player_left().
_betting_round also short-circuits when fewer than 2 players can still wager (all-in/folded).

---

## No-Limit Texas Hold'em — Official Rules Reference
These are the authoritative game rules. Every method in game.py that touches betting, blinds,
raises, or pot distribution must comply with these rules exactly.
When in doubt about any betting behaviour, consult this section before writing any logic.

DECK AND PLAYERS
  Standard 52-card deck. 2 to 10 players per table.

POSITIONS AND BLINDS
  Dealer button rotates clockwise after every hand.
  Small blind (SB): player immediately left of the dealer posts half the big blind.
    Round up if the result is not a whole number of chips.
  Big blind (BB): player two seats left of the dealer posts the full big blind.
  In the code players[0] = SB, players[1] = BB on the first hand (button starts at the last seat);
    the button shifts these each hand.

PLAYER ACTIONS — available each turn
  Fold    — always available; player surrenders their hand and all chips bet this hand
  Check   — only available if no bet has been made in the current round (call_amount == 0)
  Call    — match the current highest bet
  Bet     — place the first bet of a round (no prior bet exists)
  Raise   — increase a bet already made in the current round
  Re-raise / 3-bet / 4-bet — raise a prior raise; no cap on number of raises in no-limit

MINIMUM BET
  The first bet of any round must be at least equal to the big blind.

MINIMUM RAISE
  A raise must be at least equal to the size of the previous bet or raise in the same round.
  Track last_raise_size per betting round. Reset to big_blind at the start of each round.

ALL-IN AND INCOMPLETE RAISE RULE — critical edge case
  A player may go all-in for any amount, even less than the minimum raise.
  If the all-in amount is LESS than a full legal raise it does NOT reopen action to players who have
    already called/bet this round; only players who have not yet acted may still act.
  If the all-in amount IS a full legal raise or more, action is reopened to all remaining active players.
  In game.py this is enforced by `allow_raise` and by only resetting `acted` on a full raise.

RE-OPENING THE BET
  A prior bettor/raiser may only act again if a subsequent raise constitutes a full legal raise.

NUMBER OF RAISES
  No-limit: no cap on the number of raises in a single round.

SIDE POTS — required when a player is all-in
  Created when a player is all-in for less than the full call amount.
  Main pot: all contributing players eligible. Side pots: only players who contributed beyond the
    all-in level. Evaluate side pots separately; each won by the best hand among eligible players.
  Implemented via per-player `contributions` + _build_side_pots / _merge_contested_pots / _refund_uncalled_bet.

TIES AND SPLIT POTS
  Equal hands split the pot equally. The odd (indivisible) chip goes to the first eligible player left
  of the dealer button (small-blind seat first). Tracked explicitly in _award_pot.

---

## Web / GUI Architecture (IMPLEMENTED backend; frontend is a separate microservice)
One shared engine drives both the terminal and a JSON/WebSocket API. The frontend is a SEPARATE
microservice (not in this repo); the integration contract lives in `backend/API.md`. The decoupling
principle: the engine never owns I/O.

- Input: human decision points SUSPEND the betting loop. `TexasHoldemGame._run_hand()` is a generator
  that yields an `engine_events.DecisionRequest` when a human must act and is resumed with an
  `ActionResponse` via `.send()`. It also yields `engine_events.Tick` after the deal, after each
  community street, and after EACH player's action (resume with `.send(None)`); a Tick after a bot
  carries `pause=True`. `play_hand()` is the CONSOLE driver (ignores Ticks, no delay); the backend
  driver broadcasts on every Tick and sleeps `bot_think_seconds` on a bot Tick so the frontend sees
  bots act one at a time. Bots resolve synchronously inside the engine and never produce a DecisionRequest.
  Thinking time is tunable via `POKER_BOT_THINK_SECONDS` (default 1.0).
- Output: pluggable UI — `ConsoleUI` prints (terminal); `ui.HeadlessUI` buffers log lines for the web.
  Clients render from `state.py` serializers (per-recipient redacted: you see only your own hole cards
  until showdown). Card strings are 2 chars (`"AH"`); hand ranks appear in log text ("Two Pair").
- Backend: FastAPI + uvicorn (`requirements.txt`). REST for lobby/setup/queries; WebSocket for realtime.
- Threads: NOT for the game loop (turn-based). Concurrency = asyncio; a per-table `asyncio.Lock`
  serializes start/deal/action; the CPU-bound bot Monte-Carlo is offloaded with `asyncio.to_thread`.
- Layout: `engine_events.py` (DecisionRequest/ActionResponse/Tick), `state.py` (serializers),
  `backend/app.py` (FastAPI routes + WS), `backend/sessions.py` (Table lobby + driver + registry),
  `backend/schemas.py` (Pydantic), `backend/API.md` (frontend contract). Sessions are in-memory.

### Lobby / table model (host-driven)
A `Table` (backend/sessions.py) has phases `lobby` -> `running` -> `over`.

- **Create table**: the host creates a lobby and gets a `game_id`, a short invite `code`, and a host
  `token`. The host configures `starting_chips` and may add bots.
- **Join table**: friends join with the `code` (shareable as a link) and a name; each human gets their
  own `token`. Names must be unique per table.
- **Host controls (lobby only)**: add bots, kick any member except the host, set starting chips, and
  start the game. The game can start once there are >= 2 members.
- **Host deals each hand**: after `start`, the host triggers each subsequent hand (`POST .../hands`).
  Bots auto-play; the backend only waits on a human when it is that human's turn.
- **Late join (while running)**: joining mid-game marks the member `pending`; they are seated with the
  table's `starting_chips` at the start of the next hand the host deals.
- **Kicking is lobby-only.** Once running, seats are fixed; busted (0-chip) players still auto-drop
  between hands. When only one player has chips, the table goes `over` and a `game_over` is broadcast.

### REST endpoints (see backend/API.md for full request/response shapes)
- `POST /api/tables` (create) · `POST /api/tables/{code}/join` · `POST /api/tables/{id}/bots`
- `POST /api/tables/{id}/kick` · `POST /api/tables/{id}/starting-chips`
- `POST /api/tables/{id}/start` · `POST /api/tables/{id}/hands` (deal next, host)
- `GET /api/tables/{id}` · `DELETE /api/tables/{id}` · `GET /api/stats`

### WebSocket `WS /api/tables/{id}/ws?token=...`
- Client -> server: `{type:"action", action, amount?}`, `{type:"start_game"}`, `{type:"deal_hand"}`.
- Server -> client: `lobby` (lobby snapshot), `state` (redacted), `log` (action lines),
  `your_turn` (to the acting seat only), `hand_result` (showdown, all live hands revealed),
  `game_over`, `error`. Spectators connect without a token.

---

## Architecture Rules — Do Not Break These

IMMUTABILITY: Card and HandRank are frozen dataclasses. Never set attributes after creation.
MUTABLE DEFAULTS: hole_cards (Player) and community_cards (Table) use field(default_factory=list).
  Never change to = []; that shares one list across instances.
LIST MUTATION: empty lists with .clear(); never reassign self.hole_cards/self.community_cards.
  play_hand uses self.players[:] = [...] (slice assignment) on purpose to keep the caller's list in sync.
CHIP SAFETY: Player.bet() caps at min(amount, chips); chips never go negative. current_bet resets to 0
  at the end of every _betting_round().
RETURN VALUE FROM bet(): the actual wager may be less than requested (all-in). Always pass the return
  value to _commit()/add_to_pot(); never assume wager == requested amount.
HIGHEST BET IS MONOTONIC: in _betting_round, highest_bet only ever increases (an all-in for less than the
  call must not lower it), or call_amount goes negative.
EVALUATOR PURITY: HandEvaluator is stateless. Never add instance/session state.
UI ISOLATION: ui.py imports only Card/Deck and Player; never game/table/evaluator.
SHOWDOWN SCOPE: never pass a folded player's cards to the evaluator.
ABSOLUTE IMPORTS: keep `from cards import ...` style (flat scripts, not a package).

---

## Known Edge Cases — Already Handled

Wheel straight (A-2-3-4-5): Ace plays low; _straight_high returns 5.
All-in: bet() caps at available chips; explicit "all in" action also supported via the UI.
All-in for less than the call: highest_bet stays put; uncalled surplus refunded; side pots built.
Sub-minimum all-in raise: does not reopen action (allow_raise / acted handling).
Tie / split pot: multiple winners; odd chip to first seat left of the button.
Busted player: dropped before the next hand (no free rides to showdown).
Folded-around hand: betting/dealing stop; last player takes the pot uncontested.
One player can still wager: betting rounds skipped; remaining streets dealt out.

---

## Coding Standards — Match Existing Style

- Type hints on every method signature using built-in generics: list[Card], int | None.
- Guard clauses at the top of methods; ValueError for invalid input (negatives, wrong counts, <5 cards).
- Catch except ValueError specifically — no bare except.
- Descriptive names: call_amount, community_cards, last_raise_size — no abbreviations.
- Private helpers prefixed with underscore.
- Comments explain WHY, not WHAT.

---

## Out of Scope — Do Not Add Without Explicit Discussion

- No persistence/save state between sessions beyond the hand_history.jsonl log.
- No networking beyond the planned FastAPI/WebSocket backend described above.
- No third-party packages in the GAME CORE (cards/player/table/evaluator/bot/game stay stdlib-only).
- No tournament bracket or multi-table logic.
- No player statistics tracking across sessions beyond the existing JSONL + StatsDashboard.
