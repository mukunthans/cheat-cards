"""Socket layer: translates Socket.IO events into game actions and back.

All game mutations run inside a per-room asyncio.Lock. All timers live here,
not in the game logic: turn deadlines, doubt windows, reconnect grace,
and the periodic room cleanup sweep. game.py stays pure and sync.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from functools import wraps
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import socketio
from fastapi import FastAPI

from game import ROOM, Event
from room_manager import GRACE_MS, Room, RoomError, RoomManager

DOUBT_WINDOW_MS: int = 5_000
TURN_MS: int = 30_000
REVEAL_MS: int = 5_500
CLEANUP_INTERVAL_S: int = 60

# Comma-separated list of allowed client origins, e.g.
# "https://cheat-cards.vercel.app,https://cheat-cards.example.com".
# Unset (or "*") allows any origin — fine for local dev, loosen deliberately
# in production by setting CORS_ORIGINS to the deployed client's real URL(s).
_cors_env = os.environ.get("CORS_ORIGINS", "*").strip()
CORS_ORIGINS: str | list[str] = (
    "*" if _cors_env in ("", "*") else [o.strip() for o in _cors_env.split(",") if o.strip()]
)


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class RoomRuntime:
    """Per-room concurrency state (lock + live timers)."""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    reveal: dict[str, Any] | None = None
    doubt_deadline: int | None = None
    doubt_gen: int = 0  # bumped whenever the current window becomes stale
    doubt_task: asyncio.Task[None] | None = None
    grace_tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    turn_task: asyncio.Task[None] | None = None
    turn_deadline: int | None = None
    turn_remaining: int = TURN_MS


manager = RoomManager()
runtimes: dict[str, RoomRuntime] = {}
sid_to_player: dict[str, tuple[str, str]] = {}  # sid -> (room_code, player_id)
player_to_sid: dict[str, str] = {}

# One fixed-window counter per peer, expired by the room sweeper.
entry_counts: OrderedDict[str, tuple[float, int]] = OrderedDict()
ENTRY_WINDOW_S = 60
ENTRY_LIMIT = int(os.environ.get("CHEAT_ENTRY_LIMIT", "120"))
MAX_TRACKED_PEERS = 4096


def _expire_entry_counts(now: float) -> None:
    while entry_counts and next(iter(entry_counts.values()))[0] <= now:
        entry_counts.popitem(last=False)


def _allow_entry(sid: str) -> bool:
    environ = sio.get_environ(sid) or {}
    client = environ.get("asgi.scope", {}).get("client")
    peer = client[0] if client else environ.get("REMOTE_ADDR", "unknown")
    now = time.monotonic()
    _expire_entry_counts(now)
    if peer not in entry_counts and len(entry_counts) >= MAX_TRACKED_PEERS:
        return False
    expires, count = entry_counts.get(peer, (now + ENTRY_WINDOW_S, 0))
    if count >= ENTRY_LIMIT:
        return False
    entry_counts[peer] = expires, count + 1
    return True


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    sweeper = asyncio.create_task(_cleanup_loop())
    yield
    sweeper.cancel()


sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=CORS_ORIGINS)
app = FastAPI(lifespan=lifespan)
asgi_app = socketio.ASGIApp(sio, other_asgi_app=app)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ------------------------------------------------------------------ emits


async def emit_error(sid: str, code: str, message: str) -> None:
    await sio.emit("error", {"code": code, "message": message}, to=sid)


async def emit_events(room_code: str, events: list[Event]) -> None:
    for event in events:
        if event.name == "turn_changed":
            rt = _runtime(room_code)
            _stop_turn_timer(rt)
            rt.turn_remaining = TURN_MS
            _start_turn_timer(manager.get_room(room_code), rt)
            event.payload.update(_turn_clock(rt))
        elif event.name == "game_over":
            _stop_turn_timer(_runtime(room_code))
        if event.to == ROOM:
            await sio.emit(event.name, event.payload, room=room_code)
        else:  # private: routed to the player's current sid, if connected
            sid = player_to_sid.get(event.to)
            if sid is not None:
                await sio.emit(event.name, event.payload, to=sid)


async def emit_room_update(room_code: str) -> None:
    try:
        room = manager.get_room(room_code)
    except RoomError:
        return
    await sio.emit("room_update", room.to_public(), room=room_code)


async def after_action(room_code: str, events: list[Event]) -> None:
    """Emit action results plus a room_update; handle game-over bookkeeping."""
    if not events:
        return
    if any(e.name == "game_over" for e in events):
        manager.note_game_over(room_code, now_ms())
        rt = runtimes.get(room_code)
        if rt is not None:
            _invalidate_doubt_timer(rt)
    await emit_events(room_code, events)
    if any(e.name != "error" for e in events):
        await emit_room_update(room_code)


# ----------------------------------------------------------------- timers


def _turn_clock(rt: RoomRuntime) -> dict[str, int | None]:
    return {"turn_deadline_ts": rt.turn_deadline, "server_now_ts": now_ms()}


def _stop_turn_timer(rt: RoomRuntime) -> None:
    if rt.turn_task is not None:
        rt.turn_task.cancel()
    rt.turn_task = None
    rt.turn_deadline = None


def _start_turn_timer(room: Room, rt: RoomRuntime) -> None:
    game = room.game
    if game is None or game.active_player_id is None:
        return
    if not room.player(game.active_player_id).connected:
        return  # The disconnect grace timer holds this seat.
    rt.turn_deadline = now_ms() + rt.turn_remaining
    rt.turn_task = asyncio.create_task(_turn_timer(room, rt))


async def _turn_timer(room: Room, rt: RoomRuntime) -> None:
    await asyncio.sleep(rt.turn_remaining / 1000)
    async with rt.lock:
        if rt.turn_task is asyncio.current_task():
            rt.turn_task = None
            await after_action(room.code, room.game.expire_turn())


def _invalidate_doubt_timer(rt: RoomRuntime) -> None:
    rt.doubt_deadline = None
    rt.doubt_gen += 1
    if rt.doubt_task is not None and not rt.doubt_task.done():
        rt.doubt_task.cancel()
    rt.doubt_task = None


def _schedule_doubt_timer(room_code: str, rt: RoomRuntime) -> int:
    """Starts the 5 s window timer; returns the authoritative deadline."""
    _invalidate_doubt_timer(rt)
    generation = rt.doubt_gen
    deadline = now_ms() + DOUBT_WINDOW_MS
    rt.doubt_deadline = deadline
    rt.doubt_task = asyncio.create_task(_doubt_timer(room_code, generation))
    return deadline


async def _doubt_timer(room_code: str, generation: int) -> None:
    await asyncio.sleep(DOUBT_WINDOW_MS / 1000)
    rt = runtimes.get(room_code)
    if rt is None or rt.doubt_gen != generation:
        return  # a newer play/pass/doubt already superseded this window
    async with rt.lock:
        if rt.doubt_gen != generation:
            return
        try:
            room = manager.get_room(room_code)
        except RoomError:
            return
        if room.game is None:
            return
        rt.doubt_task = None
        events = room.game.close_doubt_window()
        await after_action(room_code, events)


async def _grace_timer(room_code: str, player_id: str) -> None:
    await asyncio.sleep(GRACE_MS / 1000)
    rt = runtimes.get(room_code)
    if rt is None:
        return
    async with rt.lock:
        rt.grace_tasks.pop(player_id, None)
        try:
            room = manager.get_room(room_code)
        except RoomError:
            return
        seat = room.player(player_id)
        if seat is None or seat.connected:
            return  # reconnected in time (or already removed)
        _, events = manager.remove_player(room_code, player_id, now_ms())
        await after_action(room_code, events)
        await emit_room_update(room_code)


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_S)
        _expire_entry_counts(time.monotonic())
        for code in manager.cleanup(now_ms()):
            rt = runtimes.pop(code, None)
            if rt is not None:
                _stop_turn_timer(rt)
                _invalidate_doubt_timer(rt)
                for task in rt.grace_tasks.values():
                    task.cancel()
            members = list(sio.manager.get_participants("/", code))
            for sid, _ in members:
                binding = sid_to_player.get(sid)
                if binding and binding[0] == code:
                    sid_to_player.pop(sid)
                    player_to_sid.pop(binding[1], None)
                    await sio.disconnect(sid)


def _runtime(room_code: str) -> RoomRuntime:
    rt = runtimes.get(room_code)
    if rt is None:
        rt = RoomRuntime()
        runtimes[room_code] = rt
    return rt


# --------------------------------------------------------------- handlers


def _bind(sid: str, room_code: str, player_id: str) -> None:
    sid_to_player[sid] = (room_code, player_id)
    player_to_sid[player_id] = sid


async def _resolve(sid: str, data: dict[str, Any]) -> tuple[str, str] | None:
    """Identity comes from the connection, never from the payload."""
    ctx = sid_to_player.get(sid)
    if ctx is None:
        await emit_error(sid, "not_joined", "Join a room first.")
        return None
    room_code, player_id = ctx
    if data.get("room_code") not in (None, room_code) or data.get("player_id") not in (
        None,
        player_id,
    ):
        await emit_error(sid, "auth_mismatch", "Identity does not match this connection.")
        return None
    return room_code, player_id


def _entry_error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def _entry_guard(sid: str) -> dict | None:
    if not sio.manager.is_connected(sid, "/"):
        return _entry_error("disconnected", "Reconnect to join a room.")
    if sid in sid_to_player:
        return _entry_error("already_joined", "Leave your current seat first.")
    if not _allow_entry(sid):
        return _entry_error("rate_limited", "Too many room requests. Try again in a minute.")
    return None


@sio.event
async def create_room(sid: str, data: dict[str, Any]) -> dict[str, Any]:
    if error := _entry_guard(sid):
        return error
    try:
        room, player = manager.create_room(str(data.get("player_name", "")))
    except RoomError as exc:
        return {"error": {"code": exc.code, "message": exc.message}}
    _bind(sid, room.code, player.id)
    _runtime(room.code)
    await sio.enter_room(sid, room.code)
    await emit_room_update(room.code)
    return {"room_code": room.code, "player_id": player.id, "session_token": player.session_token}


@sio.event
async def join_room(sid: str, data: dict[str, Any]) -> dict[str, Any]:
    room_code = str(data.get("room_code", "")).upper()
    if error := _entry_guard(sid):
        return error
    rt = runtimes.get(room_code)
    if rt is None:
        return _entry_error("room_not_found", "Room not found.")
    async with rt.lock:
        if sid in sid_to_player or not sio.manager.is_connected(sid, "/"):
            return _entry_error("seat_unavailable", "Reconnect before joining another seat.")
        try:
            room, player = manager.join_room(room_code, str(data.get("player_name", "")))
        except RoomError as exc:
            return {"error": {"code": exc.code, "message": exc.message}}
        _bind(sid, room.code, player.id)
        await sio.enter_room(sid, room.code)
        await emit_room_update(room.code)
        return {"player_id": player.id, "session_token": player.session_token}


@sio.event
async def reconnect_player(sid: str, data: dict[str, Any]) -> dict[str, Any]:
    room_code = str(data.get("room_code", "")).upper()
    if sid not in sid_to_player and not _allow_entry(sid):
        return _entry_error("rate_limited", "Too many room requests. Try again in a minute.")
    rt = runtimes.get(room_code)
    if rt is None:
        return _entry_error("room_not_found", "Room not found.")
    async with rt.lock:
        if not sio.manager.is_connected(sid, "/"):
            return _entry_error("disconnected", "Reconnect to reclaim your seat.")
        try:
            room = manager.get_room(room_code)
            token = str(data.get("session_token", ""))
            seat = room.player_by_token(token)
            bound = sid_to_player.get(sid)
            if bound and (seat is None or bound != (room_code, seat.id)):
                return _entry_error("already_joined", "Leave your current seat first.")
            room, player = manager.reconnect(room_code, token, now_ms())
        except RoomError as exc:
            return {"error": {"code": exc.code, "message": exc.message}}
        grace = rt.grace_tasks.pop(player.id, None)
        if grace is not None:
            grace.cancel()
        previous = player_to_sid.get(player.id)
        _bind(sid, room.code, player.id)
        if previous and previous != sid:
            sid_to_player.pop(previous, None)
            await sio.disconnect(previous)
        await sio.enter_room(sid, room.code)
        if grace:
            await sio.emit("player_reconnected", {"player_id": player.id}, room=room.code)
        if room.game is not None:
            game = room.game
            await sio.emit(
                "hand_updated",
                {"your_hand": [c.to_dict() for c in game.hand_of(player.id)]},
                to=sid,
            )
            resume = grace is not None and game.active_player_id == player.id
            if resume:
                _start_turn_timer(room, rt)
            turn = game.turn_event()
            turn.payload.update(_turn_clock(rt))
            await sio.emit(turn.name, turn.payload, to=room.code if resume else sid)
        await emit_room_update(room.code)
        game = room.game
        last = game.last_play if game else None
        await sio.emit("seat_sync", {
            "pile_size": len(game.pile) if game else 0,
            "last_player_id": last[0] if last else None,
            "last_count": len(last[1]) if last else None,
            "doubt_deadline_ts": rt.doubt_deadline if game and game.doubt_window_open else None,
            "server_now_ts": now_ms(),
            "game_over": game.result if game else None,
            "reveal": rt.reveal if rt.reveal and rt.reveal["expires_ts"] > now_ms() else None,
            "disconnected": {p.id: p.grace_deadline_ms for p in room.players if not p.connected},
        }, to=sid)
        return {"player_id": player.id}


RoomAction = Callable[[str, dict[str, Any], str, str, RoomRuntime], Awaitable[None]]


def room_action(handler: RoomAction) -> Callable:
    """Authorize under the room lock so a queued action cannot outlive seat ownership."""
    @wraps(handler)
    async def authorized(sid: str, data: dict[str, Any]) -> None:
        binding = sid_to_player.get(sid)
        rt = runtimes.get(binding[0]) if binding else None
        if rt is None:
            await emit_error(sid, "not_joined", "Join a room first.")
            return
        async with rt.lock:
            if await _resolve(sid, data) == binding:
                await handler(sid, data, *binding, rt)
    return sio.event(authorized)


@room_action
async def update_settings(sid: str, data: dict[str, Any], room_code: str, player_id: str, rt: RoomRuntime) -> None:
    try:
        manager.update_settings(room_code, player_id, dict(data.get("settings") or {}))
    except RoomError as exc:
        await emit_error(sid, exc.code, exc.message)
        return
    await emit_room_update(room_code)


@room_action
async def player_ready(sid: str, data: dict[str, Any], room_code: str, player_id: str, rt: RoomRuntime) -> None:
    try:
        _, events = manager.set_ready(room_code, player_id)
    except RoomError as exc:
        await emit_error(sid, exc.code, exc.message)
        return
    await emit_room_update(room_code)
    await emit_events(room_code, events)


@room_action
async def play_cards(sid: str, data: dict[str, Any], room_code: str, player_id: str, rt: RoomRuntime) -> None:
    room = manager.get_room(room_code)
    if room.game is None:
        await emit_error(sid, "not_started", "The game has not started.")
        return
    if rt.turn_deadline is not None and now_ms() >= rt.turn_deadline:
        await after_action(room_code, room.game.expire_turn())
        await emit_error(sid, "turn_expired", "Your turn expired.")
        return
    events = room.game.play_cards(
        player_id, list(data.get("card_ids") or []), data.get("declared_value")
    )
    played = next((e for e in events if e.name == "cards_played"), None)
    if played is not None:
        # New doubt window: server clock is authoritative for the deadline
        played.payload["doubt_deadline_ts"] = _schedule_doubt_timer(room_code, rt)
        played.payload["server_now_ts"] = now_ms()
    await after_action(room_code, events)


@room_action
async def pass_turn(sid: str, data: dict[str, Any], room_code: str, player_id: str, rt: RoomRuntime) -> None:
    room = manager.get_room(room_code)
    if room.game is None:
        await emit_error(sid, "not_started", "The game has not started.")
        return
    events = room.game.pass_turn(player_id)
    if any(e.name in ("player_passed", "game_over") for e in events):
        _invalidate_doubt_timer(rt)  # the pass closed the window
    await after_action(room_code, events)


@room_action
async def call_doubt(sid: str, data: dict[str, Any], room_code: str, player_id: str, rt: RoomRuntime) -> None:
    room = manager.get_room(room_code)
    if room.game is None:
        await emit_error(sid, "not_started", "The game has not started.")
        return
    claim, count = room.game.round_declared_value, len(room.game.pile)
    events = room.game.call_doubt(player_id)
    resolution = next((e for e in events if e.name == "doubt_resolved"), None)
    if resolution:
        now = now_ms()
        resolution.payload.update(declared_value=claim, pile_count=count, server_now_ts=now, expires_ts=now + REVEAL_MS)
        rt.reveal = resolution.payload
        _invalidate_doubt_timer(rt)
    await after_action(room_code, events)  # [] for late doubts: silent


@sio.event
async def disconnect(sid: str) -> None:
    ctx = sid_to_player.pop(sid, None)
    if ctx is None:
        return
    room_code, player_id = ctx
    rt = _runtime(room_code)
    async with rt.lock:
        if player_to_sid.get(player_id) != sid:
            return  # A reconnect already replaced this socket.
        del player_to_sid[player_id]
        try:
            room, removed, grace_deadline = manager.mark_disconnected(
                room_code, player_id, now_ms()
            )
        except RoomError:
            return
        if removed:  # lobby: seat dropped outright
            await emit_room_update(room_code)
            return
        if rt.turn_deadline is not None and room.game.active_player_id == player_id:
            rt.turn_remaining = max(0, rt.turn_deadline - now_ms())
            _stop_turn_timer(rt)
            turn = room.game.turn_event()
            turn.payload.update(_turn_clock(rt))
            await sio.emit(turn.name, turn.payload, room=room_code)
        await sio.emit(
            "player_disconnected",
            {"player_id": player_id, "grace_deadline_ts": grace_deadline},
            room=room_code,
        )
        rt.grace_tasks[player_id] = asyncio.create_task(_grace_timer(room_code, player_id))
        await emit_room_update(room_code)
