"""Socket layer: translates Socket.IO events into game actions and back.

All game mutations run inside a per-room asyncio.Lock. All timers live here,
not in the game logic: the 5-second doubt window, the 30-second reconnect
grace, and the periodic room cleanup sweep. game.py stays pure and sync.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import socketio
from fastapi import FastAPI

from game import ROOM, Event
from room_manager import GRACE_MS, RoomError, RoomManager

DOUBT_WINDOW_MS: int = 5_000
CLEANUP_INTERVAL_S: int = 60


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class RoomRuntime:
    """Per-room concurrency state (lock + live timers)."""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    doubt_gen: int = 0  # bumped whenever the current window becomes stale
    doubt_task: asyncio.Task[None] | None = None
    grace_tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)


manager = RoomManager()
runtimes: dict[str, RoomRuntime] = {}
sid_to_player: dict[str, tuple[str, str]] = {}  # sid -> (room_code, player_id)
player_to_sid: dict[str, str] = {}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    sweeper = asyncio.create_task(_cleanup_loop())
    yield
    sweeper.cancel()


sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
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


def _invalidate_doubt_timer(rt: RoomRuntime) -> None:
    rt.doubt_gen += 1
    if rt.doubt_task is not None and not rt.doubt_task.done():
        rt.doubt_task.cancel()
    rt.doubt_task = None


def _schedule_doubt_timer(room_code: str, rt: RoomRuntime) -> int:
    """Starts the 5 s window timer; returns the authoritative deadline."""
    _invalidate_doubt_timer(rt)
    generation = rt.doubt_gen
    deadline = now_ms() + DOUBT_WINDOW_MS
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
        for code in manager.cleanup(now_ms()):
            rt = runtimes.pop(code, None)
            if rt is not None:
                _invalidate_doubt_timer(rt)
                for task in rt.grace_tasks.values():
                    task.cancel()


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


@sio.event
async def create_room(sid: str, data: dict[str, Any]) -> dict[str, Any]:
    try:
        room, player = manager.create_room(str(data.get("player_name", "")))
    except RoomError as exc:
        return {"error": {"code": exc.code, "message": exc.message}}
    _bind(sid, room.code, player.id)
    await sio.enter_room(sid, room.code)
    await emit_room_update(room.code)
    return {"room_code": room.code, "player_id": player.id, "session_token": player.session_token}


@sio.event
async def join_room(sid: str, data: dict[str, Any]) -> dict[str, Any]:
    room_code = str(data.get("room_code", "")).upper()
    rt = _runtime(room_code)
    async with rt.lock:
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
    rt = _runtime(room_code)
    async with rt.lock:
        try:
            room, player = manager.reconnect(
                room_code, str(data.get("session_token", "")), now_ms()
            )
        except RoomError as exc:
            return {"error": {"code": exc.code, "message": exc.message}}
        grace = rt.grace_tasks.pop(player.id, None)
        if grace is not None:
            grace.cancel()
        _bind(sid, room.code, player.id)
        await sio.enter_room(sid, room.code)
        await sio.emit("player_reconnected", {"player_id": player.id}, room=room.code)
        if room.game is not None:
            game = room.game
            await sio.emit(
                "hand_updated",
                {"your_hand": [c.to_dict() for c in game.hand_of(player.id)]},
                to=sid,
            )
            await sio.emit(
                "turn_changed",
                {
                    "active_player_id": game.active_player_id,
                    "round_declared_value": game.round_declared_value,
                    "turn_number": game.turn_number,
                },
                to=sid,
            )
        await emit_room_update(room.code)
        return {"player_id": player.id}


@sio.event
async def update_settings(sid: str, data: dict[str, Any]) -> None:
    ctx = await _resolve(sid, data)
    if ctx is None:
        return
    room_code, player_id = ctx
    rt = _runtime(room_code)
    async with rt.lock:
        try:
            manager.update_settings(room_code, player_id, dict(data.get("settings") or {}))
        except RoomError as exc:
            await emit_error(sid, exc.code, exc.message)
            return
        await emit_room_update(room_code)


@sio.event
async def player_ready(sid: str, data: dict[str, Any]) -> None:
    ctx = await _resolve(sid, data)
    if ctx is None:
        return
    room_code, player_id = ctx
    rt = _runtime(room_code)
    async with rt.lock:
        try:
            _, events = manager.set_ready(room_code, player_id)
        except RoomError as exc:
            await emit_error(sid, exc.code, exc.message)
            return
        await emit_room_update(room_code)
        await emit_events(room_code, events)


@sio.event
async def play_cards(sid: str, data: dict[str, Any]) -> None:
    ctx = await _resolve(sid, data)
    if ctx is None:
        return
    room_code, player_id = ctx
    rt = _runtime(room_code)
    async with rt.lock:
        room = manager.get_room(room_code)
        if room.game is None:
            await emit_error(sid, "not_started", "The game has not started.")
            return
        events = room.game.play_cards(
            player_id, list(data.get("card_ids") or []), data.get("declared_value")
        )
        played = next((e for e in events if e.name == "cards_played"), None)
        if played is not None:
            # New doubt window: server clock is authoritative for the deadline
            played.payload["doubt_deadline_ts"] = _schedule_doubt_timer(room_code, rt)
        await after_action(room_code, events)


@sio.event
async def pass_turn(sid: str, data: dict[str, Any]) -> None:
    ctx = await _resolve(sid, data)
    if ctx is None:
        return
    room_code, player_id = ctx
    rt = _runtime(room_code)
    async with rt.lock:
        room = manager.get_room(room_code)
        if room.game is None:
            await emit_error(sid, "not_started", "The game has not started.")
            return
        events = room.game.pass_turn(player_id)
        if any(e.name in ("player_passed", "game_over") for e in events):
            _invalidate_doubt_timer(rt)  # the pass closed the window
        await after_action(room_code, events)


@sio.event
async def call_doubt(sid: str, data: dict[str, Any]) -> None:
    ctx = await _resolve(sid, data)
    if ctx is None:
        return
    room_code, player_id = ctx
    rt = _runtime(room_code)
    async with rt.lock:
        room = manager.get_room(room_code)
        if room.game is None:
            await emit_error(sid, "not_started", "The game has not started.")
            return
        events = room.game.call_doubt(player_id)
        if any(e.name == "doubt_resolved" for e in events):
            _invalidate_doubt_timer(rt)
        await after_action(room_code, events)  # [] for late doubts: silent


@sio.event
async def disconnect(sid: str) -> None:
    ctx = sid_to_player.pop(sid, None)
    if ctx is None:
        return
    room_code, player_id = ctx
    if player_to_sid.get(player_id) == sid:
        del player_to_sid[player_id]
    rt = _runtime(room_code)
    async with rt.lock:
        try:
            _, removed, grace_deadline = manager.mark_disconnected(
                room_code, player_id, now_ms()
            )
        except RoomError:
            return
        if removed:  # lobby: seat dropped outright
            await emit_room_update(room_code)
            return
        await sio.emit(
            "player_disconnected",
            {"player_id": player_id, "grace_deadline_ts": grace_deadline},
            room=room_code,
        )
        rt.grace_tasks[player_id] = asyncio.create_task(_grace_timer(room_code, player_id))
        await emit_room_update(room_code)
