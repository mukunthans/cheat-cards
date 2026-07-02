# CLAUDE.md — Cheat Cards (Custom Doubt Variant)
Read this file fully before writing any code. This spec is final. Do not invent rules,
events, or behavior not written here. If something is ambiguous, STOP and ask the user.
---
## 1. What This Is
A real-time, turn-based online bluffing card game for 2–4 players, played in the browser
via a shared room code. Inspired by Cheat/BS but a custom variant with numbered cards
(0–10), a round-locked declared number, a 5-second doubt window, and a minimum-doubts
quota required to win.
- Server is the SINGLE source of truth. True card values are NEVER sent to any client
  except the card owner (own hand) or during doubt reveal (revealed cards only).
- No database. All state lives in server memory (dict of rooms).
- Hosting: server on Render.com free tier, client on Vercel/Netlify free tier.
---
## 2. Game Rules (FINAL — implement exactly)
### 2.1 Cards
- A card is a single integer from 0 to 10. No suits, no ranks beyond the number.
- Card JSON: `{ "id": "<uuid>", "value": 7 }` — `id` is required so the client can
  reference specific cards without exposing values of others.
### 2.2 Deck Modes (host chooses in lobby)
1. **RANDOM mode** — host picks total card count `N`.
   - Constraint: `10 * num_players <= N <= 25 * num_players`. Server enforces.
   - Deck = N cards, each value drawn uniformly at random from 0–10.
   - Deal: `floor(N / num_players)` cards each. **Leftover cards are discarded**
     (removed from the game, never revealed, never enter the pile).
   - Note: no card counting is possible in this mode — doubting is psychology.
2. **FIXED mode** — host picks copies-per-number `k` (4 or 5).
   - Deck = k copies of each value 0–10 → 44 or 55 cards total.
   - Deal: **ALL cards are dealt**, round-robin. Hands may be uneven by 1 card
     (e.g. 44 cards / 3 players → 15/15/14). NOTHING is discarded.
   - Reason: discarding would break card-counting, which is the entire point of
     this mode. Uneven hands are acceptable and standard in classic Cheat.
### 2.3 Host Settings (set in lobby, locked at game start)
| Setting | Values | Default |
|---|---|---|
| deck_mode | "random" \| "fixed" | "random" |
| card_count N (random mode only) | 10p–25p | 12 * players |
| copies k (fixed mode only) | 4 \| 5 | 4 |
| min_doubts | 0–10 | 2 |
### 2.4 Turn & Round System
- Turn order = join order, fixed at game start. Play proceeds clockwise (list order).
- **Round start:** the round starter plays 1–4 cards face-down and DECLARES a number
  0–10 (e.g. "three 5s" = 3 cards, declared value 5). The declared value LOCKS for the
  whole round.
- **Subsequent turns in the round:** on your turn you must do exactly one of:
  1. **Play** 1–4 cards face-down, claiming they are the locked value (you may lie), OR
  2. **Pass** (you keep your cards, turn moves on).
- First round: the round starter is the first player in turn order. After a doubt
  resolution: see 2.6. After an all-pass round end: see 2.5.
### 2.5 Round End (everyone passes)
- If play goes fully around and returns to the LAST PLAYER WHO PLAYED CARDS without
  anyone playing (i.e., every other active player passed consecutively), the round ends:
  - The entire pile is **BURNED** (discarded from the game, never revealed).
  - The last player who played cards becomes the new round starter and declares a
    new number with a new play.
- Edge case: if the round starter plays and ALL others pass, same rule applies —
  pile burns, that same player starts a new round.
### 2.6 Doubt System
- A doubt targets ONLY the most recent card play. You cannot doubt a pass.
- **Doubt window:** opens the instant cards are played. Closes at whichever comes FIRST:
  1. 5 seconds elapse (server-side timer — the server clock is authoritative), OR
  2. the next player in turn order submits a play or pass.
- Any player EXCEPT the one who just played may doubt. First doubt received by the
  server wins; later doubts in the same window are rejected silently.
- **Resolution (server-side only):**
  - Flip the doubted cards. If ANY flipped card ≠ declared value → the play was a LIE
    → the player who played picks up the ENTIRE pile.
  - If ALL flipped cards = declared value → TRUTH → the doubter picks up the ENTIRE pile.
  - Reveal ONLY the doubted cards' values to all clients (not the rest of the pile).
- After resolution: the pile is empty. The player who WON the doubt (the doubter if it
  was a lie, the player if it was truth) becomes the new round starter.
- **Quota counting:** every doubt made counts toward the doubter's quota, WIN OR LOSE.
  Quota measures doubts made, not doubts won.
### 2.7 Win Condition & Quota Enforcement
- A player wins by having ZERO cards in hand AND `doubts_made >= min_doubts`, evaluated
  after their play survives (see below).
- **Quota block rule:** the server REJECTS any play that would empty a player's hand
  while their `doubts_made < min_doubts`. Error message:
  `"You need X more doubts before you can play your last cards."` The client must also
  show this proactively (disable the play button for a hand-emptying selection).
- A hand-emptying play does not win instantly — the doubt window still runs. If the
  play is doubted and was a lie, the player picks up the pile and the game continues.
  If undoubted (window closes) or doubted-but-truthful, the player wins immediately.
- If a truthful last play is doubted: the doubter picks up the pile, the player still
  has zero cards and quota met → player wins.
### 2.8 Disconnect / Reconnect
- On disconnect, the server holds the player's seat and hand for **30 seconds**
  (grace timer). Broadcast `player_disconnected`.
- Reconnect: client presents its `session_token` (issued at join). Server restores the
  seat, re-sends full private state (`hand_updated`) and public state. Broadcast
  `player_reconnected`.
- If it was the disconnected player's turn: their turn timer is paused for the grace
  period only. If grace expires, they are auto-passed and then removed.
- Grace expiry: player is REMOVED. Their cards are **discarded** (not shuffled into
  the pile — that corrupts doubt math). Turn order shrinks. If fewer than 2 active
  players remain, the last remaining player wins by forfeit (quota waived in forfeit).
- Host disconnect in LOBBY: host role passes to the next joined player. Host disconnect
  in game: same as any player; host role (irrelevant mid-game) passes on.
### 2.9 Misc Rules
- Play size is always 1–4 cards. Server rejects 0 or >4.
- Server validates card ids belong to the player's actual hand.
- Out-of-turn plays/passes are rejected with an error.
- Room codes: 5 uppercase alphanumeric chars, collision-checked.
- Rooms are deleted after 10 minutes of being empty, or 60 minutes after game_over.
---
## 3. Architecture Rules (NON-NEGOTIABLE)
1. Server is the single source of truth. Clients render state; they never decide it.
2. A client only ever receives: its own hand, public counts (cards per player, pile
   size), declared value, turn info, and doubt-reveal values of doubted cards only.
3. All timers (doubt window, reconnect grace) run on the SERVER. Client countdowns are
   cosmetic and synced via server timestamps in events.
4. All game mutations happen inside a per-room lock (asyncio.Lock per room) to prevent
   race conditions (e.g., two simultaneous doubts).
5. Game logic (`game.py`) is PURE PYTHON — no socket imports, no async. It exposes
   methods that take an action and return (new_state, list_of_events). Socket layer
   (`main.py`) translates events to emits. This makes logic unit-testable.
---
## 4. Socket.IO Event Contract
### Client → Server
| Event | Payload | Notes |
|---|---|---|
| create_room | { player_name } | → ack { room_code, player_id, session_token } |
| join_room | { room_code, player_name } | → ack { player_id, session_token } or error |
| reconnect_player | { room_code, session_token } | restores seat within grace |
| update_settings | { room_code, player_id, settings } | host only, lobby only |
| player_ready | { room_code, player_id } | game starts when all ready (min 2) |
| play_cards | { room_code, player_id, card_ids[], declared_value? } | declared_value ONLY allowed/required when starting a round |
| pass_turn | { room_code, player_id } | |
| call_doubt | { room_code, player_id } | first-wins inside window |
### Server → Clients
| Event | To | Payload |
|---|---|---|
| room_update | room | { players[{id,name,ready,connected,card_count,doubts_made}], host_id, settings, state: "lobby"\|"playing"\|"finished" } |
| game_started | room | { turn_order[], settings } |
| hand_updated | private | { your_hand: Card[] } |
| turn_changed | room | { active_player_id, round_declared_value \| null, turn_number } |
| cards_played | room | { player_id, count, declared_value, pile_size, doubt_deadline_ts } |
| player_passed | room | { player_id } |
| round_burned | room | { new_starter_id, burned_count } |
| doubt_resolved | room | { doubter_id, played_player_id, was_lie, revealed_cards: Card[], pile_goes_to, new_starter_id } |
| player_disconnected / player_reconnected | room | { player_id, grace_deadline_ts? } |
| player_removed | room | { player_id, reason } |
| game_over | room | { winner_id, winner_name, reason: "empty_hand"\|"forfeit" } |
| error | private | { code, message } |
---
## 5. Project Structure
```
cheat-cards/
├── CLAUDE.md
├── design/                  ← Claude Design exports (screenshots, reference code)
├── server/
│   ├── main.py              ← FastAPI + Socket.IO mount, event handlers only
│   ├── game.py              ← pure game logic (deck, deal, rounds, doubt, quota, win)
│   ├── room_manager.py      ← room lifecycle, reconnect tokens, cleanup timers
│   ├── requirements.txt     ← fastapi, uvicorn, python-socketio, pytest
│   └── tests/
│       └── test_game.py     ← REQUIRED before socket layer is written
├── client/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── socket.js        ← socket.io-client singleton, reads VITE_SERVER_URL
│   │   ├── pages/
│   │   │   ├── Home.jsx     ← create/join
│   │   │   ├── Lobby.jsx    ← players, host settings, ready
│   │   │   └── Game.jsx     ← table, owns game state from socket events
│   │   └── components/
│   │       ├── Hand.jsx  ├── Pile.jsx  ├── PlayerList.jsx
│   │       ├── DoubtButton.jsx  ├── DeclareBar.jsx  ├── RevealModal.jsx
│   ├── index.html / package.json / vite.config.js
└── README.md
```
---
## 6. Code Conventions
- Python: type hints everywhere, dataclasses for Room/Player/GameState, no globals
  except the room dict inside RoomManager.
- pytest tests are REQUIRED for game.py covering at minimum: both deck modes, dealing
  (leftover discard vs deal-all), round lock, pass-around burn, doubt lie/truth, quota
  block on last play, doubted last play (both outcomes), win, forfeit.
- React: functional components + hooks only. One component per file. Tailwind only —
  no CSS files, no inline style objects. Match layouts in /design.
- All server→client timestamps are epoch ms; client renders countdowns from them.
---
## 7. Build Phases (one phase per session, commit per phase)
| Phase | Deliverable | Done when |
|---|---|---|
| 1 | Scaffold + deps + hello-world server on :8000 | curl returns 200; vite dev serves |
| 2 | game.py + room_manager.py + tests | `pytest` green, all rule tests pass |
| 3 | Socket layer wired, per-room locks, timers | scripted 2-client python test completes a full game |
| 4 | Home + Lobby pages | 2 tabs can create/join/ready and see settings sync |
| 5 | Game page + components per /design | full game playable in 3 tabs |
| 6 | Reconnect flow + polish (reveal animation, sounds optional) | kill-tab mid-game recovers within 30s |
| 7 | Deploy: Render (server) + Vercel (client), CORS, env vars | friends can play via public URL |
Do not start a phase until the previous phase's "done" condition is verified.
