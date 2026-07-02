"""Phase 3 integration test: two scripted Socket.IO clients complete a full
game against a real uvicorn server (subprocess on a test port).

The choreography deterministically exercises: room create/join, settings
sync, ready/start, truthful play + doubt (truth outcome), pass-around burn,
a second doubt (either outcome) so both players meet min_doubts=1, and a
dump race ending with a win -- resolved by the SERVER's 5-second doubt
window timer, with no client action, whenever the race allows it.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest
import socketio

SERVER_DIR = Path(__file__).resolve().parents[1]
PORT = 8971
URL = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="module")
def server():
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:asgi_app", "--port", str(PORT)],
        cwd=SERVER_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_health(proc)
        yield
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _wait_for_health(proc: subprocess.Popen) -> None:
    deadline = time.time() + 20
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early:\n{proc.stdout.read().decode()}")
        try:
            with urllib.request.urlopen(f"{URL}/health", timeout=1) as resp:
                if resp.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("server did not become healthy in time")


class Bot:
    """Socket.IO client that tracks its view of the game from events."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.sio = socketio.AsyncClient()
        self.events: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self.player_id: str | None = None
        self.room_code: str | None = None
        self.hand: list[dict[str, Any]] = []
        self.counts: dict[str, int] = {}
        self.doubts: dict[str, int] = {}
        self.settings: dict[str, Any] = {}
        self.active: str | None = None
        self.declared: int | None = None
        self.turn_number: int = 0
        self.game_over: dict[str, Any] | None = None
        self.sio.on("*", self._on_event)

    async def _on_event(self, event: str, data: Any = None) -> None:
        if event == "hand_updated":
            self.hand = data["your_hand"]
        elif event == "turn_changed":
            self.active = data["active_player_id"]
            self.declared = data["round_declared_value"]
            self.turn_number = data["turn_number"]
        elif event == "room_update":
            self.settings = data["settings"]
            self.counts = {p["id"]: p["card_count"] for p in data["players"]}
            self.doubts = {p["id"]: p["doubts_made"] for p in data["players"]}
        elif event == "game_over":
            self.game_over = data
        await self.events.put((event, data))

    async def wait_for(self, name: str, timeout: float = 10) -> Any:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            assert remaining > 0, f"{self.name}: timed out waiting for event {name!r}"
            try:
                event, data = await asyncio.wait_for(self.events.get(), remaining)
            except asyncio.TimeoutError:
                raise AssertionError(f"{self.name}: timed out waiting for event {name!r}")
            if event == name:
                return data

    async def wait_until(self, desc: str, pred, timeout: float = 10) -> None:
        deadline = time.monotonic() + timeout
        while not pred():
            remaining = deadline - time.monotonic()
            assert remaining > 0, f"{self.name}: timed out waiting until {desc}"
            try:
                await asyncio.wait_for(self.events.get(), remaining)
            except asyncio.TimeoutError:
                raise AssertionError(f"{self.name}: timed out waiting until {desc}")

    async def play(self, card_ids: list[str], declared: int | None = None) -> None:
        payload: dict[str, Any] = {
            "room_code": self.room_code,
            "player_id": self.player_id,
            "card_ids": card_ids,
        }
        if declared is not None:
            payload["declared_value"] = declared
        await self.sio.emit("play_cards", payload)

    async def send(self, event: str, **extra: Any) -> None:
        await self.sio.emit(
            event, {"room_code": self.room_code, "player_id": self.player_id, **extra}
        )


def test_two_scripted_clients_complete_a_full_game(server) -> None:
    asyncio.run(_run_full_game())


def test_server_doubt_timer_resolves_pending_win(server) -> None:
    asyncio.run(_run_timer_win())


async def _run_timer_win() -> None:
    """Host dumps their whole hand while the guest only passes; after the
    final play NOBODY acts, so only the server's 5 s window timer can end
    the game. Verifies the timer fires and the pending win lands."""
    host, guest = Bot("host"), Bot("guest")
    await host.sio.connect(URL)
    await guest.sio.connect(URL)
    try:
        ack = await host.sio.call("create_room", {"player_name": "Host"})
        host.room_code = guest.room_code = ack["room_code"]
        host.player_id = ack["player_id"]
        ack = await guest.sio.call(
            "join_room", {"room_code": guest.room_code, "player_name": "Guest"}
        )
        guest.player_id = ack["player_id"]

        await host.send(
            "update_settings",
            settings={"deck_mode": "random", "card_count": 20, "min_doubts": 0},
        )
        await guest.wait_until(
            "settings sync", lambda: guest.settings.get("min_doubts") == 0
        )
        await host.send("player_ready")
        await guest.send("player_ready")
        await host.wait_for("game_started")
        await host.wait_until("10 cards dealt", lambda: len(host.hand) == 10)

        while len(host.hand) > 0:
            await host.wait_until("host's turn", lambda: host.active == host.player_id)
            cards = host.hand[: min(4, len(host.hand))]
            declared = cards[0]["value"] if host.declared is None else None
            turn_before = host.turn_number
            await host.play([c["id"] for c in cards], declared=declared)
            await host.wait_until(
                "play accepted", lambda: host.turn_number > turn_before
            )
            if len(host.hand) == 0:
                break  # final play made; leave the doubt window untouched
            await guest.wait_until("guest's turn", lambda: guest.active == guest.player_id)
            await guest.send("pass_turn")
            await host.wait_for("round_burned")  # 2 players: every pass burns

        started_waiting = time.monotonic()
        over = await host.wait_for("game_over", timeout=8)  # no client acts now
        elapsed = time.monotonic() - started_waiting
        assert over["winner_id"] == host.player_id
        assert over["reason"] == "empty_hand"
        assert elapsed >= 4.0, f"window closed too early ({elapsed:.2f}s)"
    finally:
        await host.sio.disconnect()
        await guest.sio.disconnect()


async def _run_full_game() -> None:
    host, guest = Bot("host"), Bot("guest")
    await host.sio.connect(URL)
    await guest.sio.connect(URL)
    try:
        # ---- lobby: create / join / settings / ready ---------------------
        ack = await host.sio.call("create_room", {"player_name": "Host"})
        assert "error" not in ack and len(ack["room_code"]) == 5
        host.room_code = guest.room_code = ack["room_code"]
        host.player_id = ack["player_id"]

        ack = await guest.sio.call(
            "join_room", {"room_code": guest.room_code, "player_name": "Guest"}
        )
        assert "error" not in ack
        guest.player_id = ack["player_id"]

        await host.send(
            "update_settings",
            settings={"deck_mode": "random", "card_count": 20, "min_doubts": 1},
        )
        await guest.wait_until(
            "settings sync", lambda: guest.settings.get("card_count") == 20
        )

        await host.send("player_ready")
        await guest.send("player_ready")
        started = await host.wait_for("game_started")
        assert started["turn_order"] == [host.player_id, guest.player_id]
        for bot in (host, guest):
            await bot.wait_until("10 cards dealt", lambda b=bot: len(b.hand) == 10)
            await bot.wait_until("host active", lambda b=bot: b.active == host.player_id)

        # ---- truthful play, doubted: doubter eats the pile ---------------
        card = host.hand[0]
        await host.play([card["id"]], declared=card["value"])
        played = await guest.wait_for("cards_played")
        assert played["pile_size"] == 1 and played["count"] == 1
        assert isinstance(played["doubt_deadline_ts"], int)  # server-side clock

        await guest.send("call_doubt")
        resolved = await host.wait_for("doubt_resolved")
        assert resolved["was_lie"] is False
        assert resolved["pile_goes_to"] == guest.player_id
        assert resolved["new_starter_id"] == host.player_id
        assert [c["value"] for c in resolved["revealed_cards"]] == [card["value"]]
        await guest.wait_until("guest picked up pile", lambda: len(guest.hand) == 11)
        await host.wait_until(
            "guest quota counted", lambda: host.doubts.get(guest.player_id) == 1
        )

        # ---- pass-around burn --------------------------------------------
        card = host.hand[0]
        await host.play([card["id"]], declared=card["value"])
        await guest.wait_for("cards_played")
        await guest.send("pass_turn")
        burned = await host.wait_for("round_burned")
        assert burned == {"new_starter_id": host.player_id, "burned_count": 1}
        # hands: host 8, guest 11

        # ---- host earns their doubt (outcome may go either way) ----------
        card = host.hand[0]
        await host.play([card["id"]], declared=card["value"])
        await guest.wait_until("guest's turn", lambda: guest.active == guest.player_id)
        await guest.play([guest.hand[0]["id"]])  # claims the locked value
        await host.wait_for("cards_played")
        await host.send("call_doubt")
        await host.wait_for("doubt_resolved")
        await host.wait_until(
            "host quota counted", lambda: host.doubts.get(host.player_id) == 1
        )

        # ---- dump race: both quotas met, play until someone empties ------
        bots = {host.player_id: host, guest.player_id: guest}
        game_deadline = time.monotonic() + 90
        while host.game_over is None:
            assert time.monotonic() < game_deadline, "game did not finish in time"
            await host.wait_until(
                "someone active or game over",
                lambda: host.game_over is not None or host.active in bots,
            )
            if host.game_over is not None:
                break
            actor = bots[host.active]
            opponent = guest if actor is host else host
            if host.counts.get(opponent.player_id, 1) == 0:
                # Opponent's hand-emptying play is pending: nobody acts, the
                # SERVER's 5 s doubt-window timer must end the game by itself.
                await host.wait_for("game_over", timeout=8)
                break
            await asyncio.sleep(0.2)  # let hand_updated/room_update settle
            turn_before = host.turn_number
            cards = actor.hand[: min(4, len(actor.hand))]
            declared = actor.declared if actor.declared is not None else cards[0]["value"]
            await actor.play(
                [c["id"] for c in cards],
                declared=None if actor.declared is not None else declared,
            )
            await host.wait_until(
                "turn advanced or game over",
                lambda: host.turn_number > turn_before or host.game_over is not None,
            )

        # ---- final assertions ---------------------------------------------
        await guest.wait_until("guest sees game over", lambda: guest.game_over is not None)
        over = host.game_over
        assert over["reason"] == "empty_hand"
        winner = bots[over["winner_id"]]
        assert over["winner_name"] in ("Host", "Guest")
        assert len(winner.hand) == 0
        assert host.doubts[over["winner_id"]] >= 1  # quota was met, not waived
    finally:
        await host.sio.disconnect()
        await guest.sio.disconnect()
