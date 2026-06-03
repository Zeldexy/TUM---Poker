# Texas Hold'em Backend — Frontend Integration Guide

The full contract a frontend microservice needs to talk to this backend: lobby
management (REST), realtime play (WebSocket), and every JSON object shape.

- **Base URL (dev):** `http://localhost:8000`
- **Run the backend:** from the repo root, `uvicorn backend.app:app --reload`
- **OpenAPI/Swagger:** `http://localhost:8000/docs`
- **CORS:** all origins/methods/headers allowed (dev). Tighten for production.
- **Content type:** JSON for all REST bodies and all WebSocket messages.

---

## Mental model

- A **table** is created by a **host** and identified by a `game_id` plus a short, shareable invite
  `code`. The frontend can build an invite **link** that carries the `code` (e.g. `/join/ABC123`).
- A table has three phases: **`lobby`** → **`running`** → **`over`**.
- Each **human** (host included) gets a private **`token`** that authorizes their seat. Bots have no
  token. Use the token on the WebSocket (`?token=...`) and inside `action` messages implicitly (the
  socket is already authenticated by its token).
- **Lobby phase:** the host sets starting chips, adds bots, kicks members, and starts the game. The
  game can start once there are **≥ 2 members**.
- **Running phase:** the **host deals each hand** (`POST .../hands`). Bots auto-play; the backend only
  pauses for a human when it's that human's turn. Bot moves are streamed **one at a time** — you get a
  fresh `state` (and a `log` line) per action, with a short artificial "thinking" delay before each bot
  move (default ~1s, set by `POKER_BOT_THINK_SECONDS` on the server). So just render every `state`/`log`
  as it arrives; the pacing is already handled server-side.
- **Joining a running table** is allowed: the joiner is **pending** and is seated (with the table's
  `starting_chips`) at the start of the **next hand the host deals**.
- **Kicking is lobby-only.** Once running, seats are fixed; busted (0-chip) players auto-drop between
  hands. When one player has all the chips the table becomes `over`.
- **Hole cards are redacted per recipient** over the WebSocket: you only see your own cards until
  showdown (`hand_result`), when all live hands are revealed.

> **Seats can renumber between hands** (busted players are removed). Tokens map to a player's **name**
> (unique per table). Every `state`/`hand_result` message includes `your_seat` (your current index, or
> `null` if eliminated/spectating). Render off `your_seat`/name, not a cached index.

---

## REST endpoints

### `POST /api/tables` — create a table (become host)
Request:
```json
{ "host_name": "Anton", "starting_chips": 100, "small_blind": 5, "big_blind": 10 }
```
`starting_chips`/`small_blind`/`big_blind` are optional (defaults 100/5/10), all > 0.
Response `200`:
```json
{
  "game_id": "Xk2p9A",
  "code": "ABC123",
  "token": "HOST_TOKEN",      // the host's private seat token
  "member_id": "m_ab12",
  "is_host": true,
  "lobby": { /* LobbySnapshot */ }
}
```

### `POST /api/tables/{code}/join` — join by invite code
Request: `{ "name": "Daniel" }`  (name must be unique at the table)
Response `200`:
```json
{
  "game_id": "Xk2p9A",
  "code": "ABC123",
  "token": "DANIEL_TOKEN",
  "member_id": "m_cd34",
  "is_host": false,
  "pending": false,           // true if the table is already running (seated next hand)
  "lobby": { /* LobbySnapshot */ }
}
```
`400` if the name is taken or the game is over; `404` if the code is unknown.

### `POST /api/tables/{game_id}/bots` — host adds a bot (lobby only)
Request: `{ "host_token": "HOST_TOKEN", "name": "Bob bot" }`  (`name` optional → auto "Bot N")
Response `200`: `LobbySnapshot`. `400` if not host / not in lobby / name taken.

### `POST /api/tables/{game_id}/kick` — host kicks a member (lobby only)
Request: `{ "host_token": "HOST_TOKEN", "member_id": "m_cd34" }`
Response `200`: `LobbySnapshot`. `400` if not host, not in lobby, target missing, or target is the host.

### `POST /api/tables/{game_id}/starting-chips` — host sets the buy-in (lobby only)
Request: `{ "host_token": "HOST_TOKEN", "starting_chips": 200 }`
Response `200`: `LobbySnapshot`.

### `POST /api/tables/{game_id}/start` — host starts the game
Request: `{ "host_token": "HOST_TOKEN" }`  (requires ≥ 2 members)
Response `200`: `{ "ok": true, "status": "running" }`. Side effect: pushes `lobby` then `state`/
`your_turn`/`log` over the WebSocket.

### `POST /api/tables/{game_id}/hands` — host deals the next hand
Request: `{ "host_token": "HOST_TOKEN" }`
Seats any pending late-joiners first, then deals. Response `200`:
`{ "ok": true, "status": "running"|"over", "hand_in_progress": true|false }`.
If fewer than two players have chips, broadcasts `game_over` instead.

### `GET /api/tables/{game_id}` — snapshot
Returns a `LobbySnapshot` while in the lobby, otherwise a public (unredacted: all `hole_cards` null)
`state` message. `404` if unknown.

### `POST /api/tables/{game_id}/leave` — leave the table
Request: `{ "token": "YOUR_TOKEN" }`. Removes you (reassigns host if needed), broadcasts `lobby`.
Response `200`: `{ "ok": true }`. (Usually you'll just send the `leave` WebSocket message instead.)

### `DELETE /api/tables/{game_id}` — tear down → `{ "ok": true }`
Also deletes this table's hand-history file.

### `GET /api/tables/{game_id}/history` — this table's hand history
Response `200`: `{ "game_id": "...", "hands": [ HandRecord, ... ] }` (oldest first; `[]` before any
hand finishes). `404` if unknown. Each `HandRecord`:
```json
{ "hand_number": 1, "started_at": "2026-06-03T12:00:00",
  "players": [ { "name": "You", "starting_chips": 100 }, ... ],
  "actions": [ { "street": "Pre-Flop", "player": "You", "action": "call", "amount": 10,
                 "time": "..." }, ... ],
  "community_cards": [ { "street": "Flop", "cards": ["AH","KD","7C"] }, ... ],
  "winners": ["You"], "pot": 40 }
```
Each table writes to its OWN file (`hand_histories/{game_id}.jsonl`); the file is deleted when the
table's last WebSocket connection closes (or on `DELETE`), so query/store it before everyone leaves.

### `GET /api/tables/{game_id}/stats` — per-player stats for THIS table
Response `200`: `{ "game_id": "...", "players": { <name>: { ...stats } } }`. Same per-player shape as
`GET /api/stats` below (`hands_played, hands_won, total_winnings, win_rate, folds, calls, raises,
checks, bets, small_blinds, big_blinds`). `players` is `{}` before any hand finishes. `404` if unknown.

### `GET /api/stats` — aggregated stats (across ALL tables, from `hand_history.jsonl`)
Map keyed by player name; each value:
`hands_played, hands_won, total_winnings, win_rate, folds, calls, raises, checks, bets,
small_blinds, big_blinds`. (`{}` if no history; all-ins not yet tallied.) Note: the console game
writes here; live web tables use the per-table endpoints above.

---

## WebSocket

### Connect
```
ws://localhost:8000/api/tables/{game_id}/ws?token=<token>
```
- `token` optional. With a human token you control that seat; without one you are a **spectator**
  (redacted state + logs, no `your_turn`, cannot act).
- Unknown `game_id` → socket closed with code `4004`.
- **On connect** the server sends `lobby` (if still in the lobby) or `state` (if running); if it is
  already your turn you also get a `your_turn`.

### Client → server messages
```json
{ "type": "action", "action": "call", "amount": 0 }   // gameplay (must be your turn)
{ "type": "start_game" }                                // host only (same as POST .../start)
{ "type": "deal_hand" }                                 // host only (same as POST .../hands)
{ "type": "leave" }                                     // leave the table (server acks + closes)
```
`action` ∈ `fold | check | call | raise | all in` (`all_in`/`allin` also accepted).
- `amount` is used only for `raise` = chips **on top of** the call, within `[min_raise, max_raise]`
  from your latest `your_turn`. The server clamps defensively. If `min_raise > max_raise`, the only
  legal raise is an all-in (send `all in`, or `raise` with `amount = max_raise`).
- Sending `call` when nothing is owed counts as a check.
- Lobby mutations (create/join/bots/kick/start chips) are **REST only**; lobby changes are pushed to
  everyone as `lobby` messages.

### Server → client messages (all have a `type`)
- **`lobby`** — `LobbySnapshot` (sent on connect in lobby phase, and after every lobby change).
- **`state`** — redacted table snapshot (sent on connect when running, and after every advancement).
  ```json
  { "type": "state", "game_id": "...", "status": "running",
    "hand_in_progress": true, "your_seat": 0, "state": { /* StateSnapshot */ } }
  ```
- **`log`** — `{ "type": "log", "lines": ["Bob bot calls 10.", "You: AH KH - Two Pair"] }`
  (replay with small delays to animate bot turns).
- **`your_turn`** — sent only to the acting seat:
  ```json
  { "type": "your_turn", "seat": 0, "name": "You", "call_amount": 10,
    "can_check": false, "can_raise": true, "min_raise": 10, "max_raise": 90, "can_all_in": true }
  ```
- **`hand_result`** — same shape as `state` but `type` is `hand_result` and all live `hole_cards` are
  revealed (`hand_in_progress` is false). Winners/amounts are in the preceding `log` lines.
- **`game_over`** — `{ "type": "game_over", "winner": "Anton" }` (or `winner: null`).
- **`error`** — `{ "type": "error", "message": "It is not your turn." }`; state unchanged.
- **`left`** — `{ "type": "left" }` ack right before the server closes your socket (in response to a
  `leave` message). The socket is **also closed server-side** on any disconnect, so `onclose` fires.

### Leaving a table
To leave: send `{ "type": "leave" }` (or `POST /api/tables/{game_id}/leave` with `{token}`), then close
the socket. The backend removes you from the lobby (reassigning the host if you were it), broadcasts the
updated `lobby` to everyone else, sends you `left`, and closes your socket. **Navigate to your main
screen in `ws.onclose` and/or on the `left` message, and drop your socket reference** — the server does
not keep your connection alive, so a lingering socket is purely a client-side reference. If you leave
while a hand is running your seat's turns are **auto-folded** (the table never stalls waiting on you);
the seat is dropped at the next dealt hand.

---

## Object shapes

### LobbySnapshot
```jsonc
{
  "type": "lobby",
  "game_id": "Xk2p9A",
  "code": "ABC123",
  "status": "lobby",              // "lobby" | "running" | "over"
  "starting_chips": 100,
  "small_blind": 5,
  "big_blind": 10,
  "can_start": true,              // status == "lobby" and >= 2 members
  "members": [
    { "id": "m_ab12", "name": "Anton",   "kind": "human", "is_host": true,  "pending": false },
    { "id": "m_cd34", "name": "Daniel",  "kind": "human", "is_host": false, "pending": false },
    { "id": "m_ef56", "name": "Bob bot", "kind": "bot",   "is_host": false, "pending": false }
  ]
}
```
Use `members[].id` for kick requests. `kind` is `"human"` or `"bot"`. `pending` = joined mid-game,
seated at the next dealt hand.

### StateSnapshot (the `state` field)
```jsonc
{
  "hand_number": 3,
  "button": 2,                 // dealer seat index
  "small_blind_seat": 0,       // int | null
  "big_blind_seat": 1,         // int | null
  "small_blind": 5,
  "big_blind": 10,
  "pot": 30,
  "board": ["AH", "KD", "7C"], // 0..5 community cards
  "players": [ /* PlayerView, in seat order */ ]
}
```

### PlayerView
```jsonc
{
  "seat": 0, "name": "Anton", "chips": 90, "current_bet": 10,
  "folded": false, "is_human": true, "all_in": false,
  "is_button": false, "is_small_blind": true, "is_big_blind": false,
  "hole_cards": ["AH", "KH"],  // 2 strings if visible to you (or at showdown), else null
  "hole_card_count": 2          // render face-down cards for opponents
}
```

### your_turn fields
`seat:int, name:str, call_amount:int, can_check:bool, can_raise:bool, min_raise:int, max_raise:int,
can_all_in:bool`.

---

## Card & hand string formats
Cards are `<rank><suit>`, 2 chars. Ranks `2 3 4 5 6 7 8 9 T J Q K A`; suits `C D H S`.
Examples: `"AH"`, `"TS"`, `"7C"`. Hand names appear only inside `log` text, title-cased
(`High Card … Straight Flush`).

---

## End-to-end flow

1. Host: `POST /api/tables` → store `game_id`, `code`, host `token`. Share `code`/link.
2. Friends: `POST /api/tables/{code}/join` → each stores its `token`.
3. Everyone opens the WebSocket with `?token=...` (spectators omit it) → receive `lobby`.
4. Host: `POST .../bots`, `.../kick`, `.../starting-chips` as desired (each pushes `lobby`).
5. Host: `POST .../start` (≥ 2 members) → first hand is dealt; clients get `state` + `your_turn`/`log`.
6. Acting client: `{type:"action", ...}` → server advances (bots auto-play) → `log` + `state`, then
   `your_turn` to the next human, or `hand_result` at showdown.
7. Host: `POST .../hands` to deal the next hand (seats pending late-joiners first). Repeat.
8. When one player has all chips → `game_over`.

### Minimal client sketch
```js
const ws = new WebSocket(`ws://localhost:8000/api/tables/${gameId}/ws?token=${token}`);
ws.onmessage = (ev) => {
  const msg = JSON.parse(ev.data);
  switch (msg.type) {
    case "lobby":        renderLobby(msg); break;          // members, can_start, host controls
    case "state":        renderTable(msg.state, msg.your_seat); break;
    case "log":          appendLog(msg.lines); break;
    case "your_turn":    enableControls(msg); break;        // call_amount, min_raise, max_raise...
    case "hand_result":  revealAndRender(msg.state); break;
    case "game_over":    showWinner(msg.winner); break;
    case "error":        toast(msg.message); break;
  }
};
ws.send(JSON.stringify({ type: "action", action: "raise", amount: 20 }));
```

---

## Concurrency / guarantees (informational)
- Turn-based: one human action advances the game at a time; a per-table lock serializes concurrent
  submits, so two browsers racing is safe.
- Bot decision-making (Monte-Carlo) runs off the event loop; the server stays responsive across many
  tables/clients.
- Sessions are **in-memory**: a backend restart drops tables (re-create via `POST /api/tables`).
