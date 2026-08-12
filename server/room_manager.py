"""Room lifecycle, reconnect tokens, cleanup bookkeeping.

No sockets, no async, no wall clocks: callers pass now_ms everywhere so the
module is unit-testable. The socket layer owns the real timers and calls
cleanup()/remove_player() when they fire.
"""

from __future__ import annotations

import os
import random
import string
import uuid
from dataclasses import dataclass, field
from typing import Any

from game import Event, Game, Settings

# Disconnected seat held for 30 s. Env override exists ONLY so integration
# tests can shrink the grace window; production uses the default.
GRACE_MS: int = int(os.environ.get("CHEAT_GRACE_MS", "30000"))
EMPTY_ROOM_TTL_MS: int = 10 * 60_000  # empty rooms deleted after 10 min
FINISHED_ROOM_TTL_MS: int = 60 * 60_000  # finished games deleted after 60 min

CODE_CHARS: str = string.ascii_uppercase + string.digits
CODE_LEN: int = 5
MAX_PLAYERS: int = 4
MIN_PLAYERS: int = 2
MAX_NAME_LEN: int = 20

ALLOWED_SETTING_KEYS: frozenset[str] = frozenset(
    {"deck_mode", "card_count", "copies", "min_doubts"}
)


class RoomError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class RoomPlayer:
    id: str
    name: str
    session_token: str
    ready: bool = False
    connected: bool = True
    grace_deadline_ms: int | None = None


@dataclass
class Room:
    code: str
    host_id: str
    players: list[RoomPlayer] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)
    game: Game | None = None
    empty_since_ms: int | None = None
    finished_at_ms: int | None = None

    @property
    def state(self) -> str:
        if self.game is None:
            return "lobby"
        return "finished" if self.game.state == "finished" else "playing"

    def player(self, player_id: str) -> RoomPlayer | None:
        return next((p for p in self.players if p.id == player_id), None)

    def player_by_token(self, session_token: str) -> RoomPlayer | None:
        return next((p for p in self.players if p.session_token == session_token), None)

    def to_public(self) -> dict[str, Any]:
        counts: dict[str, dict[str, int]] = {}
        if self.game is not None:
            counts = {
                p["id"]: {"card_count": p["card_count"], "doubts_made": p["doubts_made"]}
                for p in self.game.public_state()["players"]
            }
        return {
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "ready": p.ready,
                    "connected": p.connected,
                    "card_count": counts.get(p.id, {}).get("card_count", 0),
                    "doubts_made": counts.get(p.id, {}).get("doubts_made", 0),
                }
                for p in self.players
            ],
            "host_id": self.host_id,
            "settings": self.settings.to_dict(),
            "state": self.state,
        }


class RoomManager:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rooms: dict[str, Room] = {}
        self._rng: random.Random = rng or random.Random()

    # -------------------------------------------------------------- lobby

    def create_room(self, player_name: str) -> tuple[Room, RoomPlayer]:
        player = self._new_player(player_name)
        room = Room(code=self._generate_code(), host_id=player.id, players=[player])
        self._rooms[room.code] = room
        return room, player

    def join_room(self, code: str, player_name: str) -> tuple[Room, RoomPlayer]:
        room = self.get_room(code)
        if room.state != "lobby":
            raise RoomError("game_in_progress", "This game has already started.")
        if len(room.players) >= MAX_PLAYERS:
            raise RoomError("room_full", f"Room is full (max {MAX_PLAYERS} players).")
        player = self._new_player(player_name)
        room.players.append(player)
        room.empty_since_ms = None
        return room, player

    def get_room(self, code: str) -> Room:
        room = self._rooms.get(code)
        if room is None:
            raise RoomError("room_not_found", "Room not found.")
        return room

    def update_settings(self, code: str, player_id: str, updates: dict[str, Any]) -> Room:
        room = self.get_room(code)
        if room.state != "lobby":
            raise RoomError("game_in_progress", "Settings are locked once the game starts.")
        if player_id != room.host_id:
            raise RoomError("not_host", "Only the host can change settings.")
        unknown = set(updates) - ALLOWED_SETTING_KEYS
        if unknown:
            raise RoomError("invalid_settings", f"Unknown settings: {sorted(unknown)}")
        candidate = Settings(**{**room.settings.to_dict(), **updates})
        # Validate against at least MIN_PLAYERS; start_game re-validates with
        # the final player count and rejects the start if it no longer fits.
        try:
            candidate.validate(max(MIN_PLAYERS, len(room.players)))
        except (ValueError, TypeError) as exc:
            raise RoomError("invalid_settings", str(exc)) from exc
        room.settings = candidate
        return room

    def set_ready(
        self, code: str, player_id: str, rng: random.Random | None = None
    ) -> tuple[Room, list[Event]]:
        """Mark ready; auto-starts the game (returning its start events) when
        all players (>= 2) are ready. Returns (room, []) otherwise."""
        room = self.get_room(code)
        if room.state != "lobby":
            raise RoomError("game_in_progress", "This game has already started.")
        player = room.player(player_id)
        if player is None:
            raise RoomError("not_in_room", "You are not in this room.")
        player.ready = True
        if len(room.players) >= MIN_PLAYERS and all(p.ready for p in room.players):
            return room, self._start_game(room, rng)
        return room, []

    def _start_game(self, room: Room, rng: random.Random | None) -> list[Event]:
        try:
            room.settings.validate(len(room.players))
        except ValueError as exc:
            raise RoomError("invalid_settings", str(exc)) from exc
        room.game = Game(
            [(p.id, p.name) for p in room.players], room.settings, rng=rng
        )
        return room.game.start_events()

    # ------------------------------------------------------ connect state

    def mark_disconnected(
        self, code: str, player_id: str, now_ms: int
    ) -> tuple[Room, bool, int | None]:
        """Returns (room, removed_immediately, grace_deadline_ms).

        Lobby: the player is removed outright (no seat to protect).
        In game: the seat is held for GRACE_MS; the socket layer's timer
        calls remove_player() if it expires."""
        room = self.get_room(code)
        player = room.player(player_id)
        if player is None:
            raise RoomError("not_in_room", "Player is not in this room.")
        if room.state == "lobby":
            room.players.remove(player)
            self._pass_host(room, player_id)
            self._update_empty(room, now_ms)
            return room, True, None
        player.connected = False
        player.grace_deadline_ms = now_ms + GRACE_MS
        self._pass_host(room, player_id)
        self._update_empty(room, now_ms)
        return room, False, player.grace_deadline_ms

    def reconnect(self, code: str, session_token: str, now_ms: int) -> tuple[Room, RoomPlayer]:
        room = self.get_room(code)
        player = room.player_by_token(session_token)
        if player is None:
            raise RoomError("invalid_token", "No seat matches this session token.")
        player.connected = True
        player.grace_deadline_ms = None
        room.empty_since_ms = None
        return room, player

    def remove_player(
        self, code: str, player_id: str, now_ms: int, reason: str = "disconnect_timeout"
    ) -> tuple[Room, list[Event]]:
        """Permanent removal (grace expired or explicit leave)."""
        room = self.get_room(code)
        player = room.player(player_id)
        if player is None:
            return room, []
        room.players.remove(player)
        self._pass_host(room, player_id)
        events: list[Event] = []
        if room.game is not None and room.game.state == "playing":
            events = room.game.remove_player(player_id, reason=reason)
            if room.game.state == "finished":
                room.finished_at_ms = now_ms
        self._update_empty(room, now_ms)
        return room, events

    def note_game_over(self, code: str, now_ms: int) -> None:
        self.get_room(code).finished_at_ms = now_ms

    # ------------------------------------------------------------ cleanup

    def cleanup(self, now_ms: int) -> list[str]:
        """Delete expired rooms; returns the deleted room codes."""
        expired = [
            code
            for code, room in self._rooms.items()
            if (
                room.empty_since_ms is not None
                and now_ms - room.empty_since_ms >= EMPTY_ROOM_TTL_MS
            )
            or (
                room.finished_at_ms is not None
                and now_ms - room.finished_at_ms >= FINISHED_ROOM_TTL_MS
            )
        ]
        for code in expired:
            del self._rooms[code]
        return expired

    @property
    def room_count(self) -> int:
        return len(self._rooms)

    # ----------------------------------------------------------- internal

    def _new_player(self, player_name: str) -> RoomPlayer:
        name = player_name.strip()[:MAX_NAME_LEN]
        if not name:
            raise RoomError("invalid_name", "Name cannot be empty.")
        return RoomPlayer(id=str(uuid.uuid4()), name=name, session_token=str(uuid.uuid4()))

    def _generate_code(self) -> str:
        while True:
            code = "".join(self._rng.choices(CODE_CHARS, k=CODE_LEN))
            if code not in self._rooms:
                return code

    def _pass_host(self, room: Room, leaving_player_id: str) -> None:
        if room.host_id != leaving_player_id:
            return
        remaining = [p for p in room.players if p.id != leaving_player_id and p.connected]
        if not remaining:
            remaining = [p for p in room.players if p.id != leaving_player_id]
        if remaining:
            room.host_id = remaining[0].id

    def _update_empty(self, room: Room, now_ms: int) -> None:
        if not room.players or not any(p.connected for p in room.players):
            if room.empty_since_ms is None:
                room.empty_since_ms = now_ms
        else:
            room.empty_since_ms = None
