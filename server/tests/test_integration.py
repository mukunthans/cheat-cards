"""Verification suite: async Socket.IO clients against a real uvicorn server.

Covers the full CLAUDE.md contract: core flow, rule enforcement, round
mechanics, doubt resolution, server-side timers, last-play edge cases,
disconnect/reconnect/forfeit, doubt-race concurrency, both deck modes, and
an information-leakage audit that records every payload each client sees.

The server subprocess runs with CHEAT_GRACE_MS=2000 so grace-expiry tests
finish quickly; the production default (30 s) is untouched.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Callable

import pytest
import socketio

SERVER_DIR = Path(__file__).resolve().parents[1]
PORT = 8972
URL = f"http://127.0.0.1:{PORT}"
GRACE_MS = 2_000  # via CHEAT_GRACE_MS below
DOUBT_WINDOW_S = 5.0
DRAIN_S = 0.35  # settle time before asserting "nothing happened"


@pytest.fixture(scope="module")
def server():
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:asgi_app", "--port", str(PORT)],
        cwd=SERVER_DIR,
        env={**os.environ, "CHEAT_GRACE_MS": str(GRACE_MS)},
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


# --------------------------------------------------------------------- bot


class Bot:
    """Socket.IO client that records EVERY event payload it receives and
    tracks its view of the game (used for both choreography and the
    information-leakage audit)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.sio = socketio.AsyncClient()
        self.recorded: list[tuple[str, Any]] = []
        self._new_event = asyncio.Event()
        self.player_id: str | None = None
        self.session_token: str | None = None
        self.room_code: str | None = None
        self.hand: list[dict[str, Any]] = []
        self.counts: dict[str, int] = {}
        self.doubts: dict[str, int] = {}
        self.settings: dict[str, Any] = {}
        self.room_state: str | None = None
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
            self.room_state = data["state"]
            self.counts = {p["id"]: p["card_count"] for p in data["players"]}
            self.doubts = {p["id"]: p["doubts_made"] for p in data["players"]}
        elif event == "game_over":
            self.game_over = data
        self.recorded.append((event, data))
        self._new_event.set()

    # ---- waiting -------------------------------------------------------

    def mark(self) -> int:
        return len(self.recorded)

    def count(self, name: str, since: int = 0) -> int:
        return sum(1 for e, _ in self.recorded[since:] if e == name)

    async def wait_until(self, desc: str, pred: Callable[[], bool], timeout: float = 10) -> None:
        deadline = time.monotonic() + timeout
        while True:
            if pred():
                return
            self._new_event.clear()
            if pred():  # re-check: an event may have landed before clear()
                return
            remaining = deadline - time.monotonic()
            assert remaining > 0, f"{self.name}: timed out waiting until {desc}"
            try:
                await asyncio.wait_for(self._new_event.wait(), remaining)
            except asyncio.TimeoutError:
                raise AssertionError(f"{self.name}: timed out waiting until {desc}")

    async def wait_for(self, name: str, since: int = 0, timeout: float = 10) -> Any:
        found: dict[str, Any] = {}

        def pred() -> bool:
            for event, data in self.recorded[since:]:
                if event == name:
                    found["data"] = data
                    return True
            return False

        await self.wait_until(f"event {name!r}", pred, timeout)
        return found["data"]

    # ---- actions -------------------------------------------------------

    async def send(self, event: str, **extra: Any) -> None:
        await self.sio.emit(
            event, {"room_code": self.room_code, "player_id": self.player_id, **extra}
        )

    async def play(self, card_ids: list[str], declared: int | None = None) -> None:
        payload: dict[str, Any] = {"card_ids": card_ids}
        if declared is not None:
            payload["declared_value"] = declared
        await self.send("play_cards", **payload)

    def hand_ids(self) -> list[str]:
        return [c["id"] for c in self.hand]


# ------------------------------------------------------------------ setup


@asynccontextmanager
async def game_room(
    n_players: int, settings: dict[str, Any] | None = None, start: bool = True
) -> AsyncIterator[list[Bot]]:
    bots = [Bot(f"P{i + 1}") for i in range(n_players)]
    try:
        for bot in bots:
            await bot.sio.connect(URL, wait_timeout=10)
        ack = await bots[0].sio.call("create_room", {"player_name": bots[0].name})
        assert "error" not in ack, ack
        code = ack["room_code"]
        bots[0].room_code = code
        bots[0].player_id = ack["player_id"]
        bots[0].session_token = ack["session_token"]
        for bot in bots[1:]:
            bot.room_code = code
            ack = await bot.sio.call("join_room", {"room_code": code, "player_name": bot.name})
            assert "error" not in ack, ack
            bot.player_id = ack["player_id"]
            bot.session_token = ack["session_token"]
        if settings:
            await bots[0].send("update_settings", settings=settings)
            for bot in bots:
                await bot.wait_until(
                    "settings sync",
                    lambda b=bot: all(b.settings.get(k) == v for k, v in settings.items()),
                )
        if start:
            for bot in bots:
                await bot.send("player_ready")
            for bot in bots:
                await bot.wait_for("game_started")
                await bot.wait_until("hand dealt", lambda b=bot: len(b.hand) > 0)
                await bot.wait_until("first turn known", lambda b=bot: b.active is not None)
        yield bots
    finally:
        for bot in bots:
            if bot.sio.connected:
                await bot.sio.disconnect()


def wrong_value(v: int) -> int:
    return (v + 1) % 11


async def burn_down(host: Bot, guest: Bot, target: int) -> None:
    """2-player helper: host plays (guest passes -> burn) until host holds
    exactly `target` cards. Never makes a hand-emptying play."""
    while len(host.hand) > target:
        await host.wait_until(
            "host starts a round",
            lambda: host.active == host.player_id and host.declared is None,
        )
        take = min(4, len(host.hand) - target)
        cards = host.hand[:take]
        hm, gm = host.mark(), guest.mark()
        await host.play([c["id"] for c in cards], declared=cards[0]["value"])
        await guest.wait_for("cards_played", since=gm)
        await guest.wait_until("guest's turn", lambda: guest.active == guest.player_id)
        await guest.send("pass_turn")
        await host.wait_for("round_burned", since=hm)


async def assert_no_state_change(bots: list[Bot], marks: list[int], hands_before: list[int]) -> None:
    """After an expected rejection: no play/turn/hand events, hands unchanged."""
    await asyncio.sleep(DRAIN_S)
    for bot, mark, size in zip(bots, marks, hands_before):
        for name in ("cards_played", "turn_changed", "hand_updated", "player_passed"):
            assert bot.count(name, since=mark) == 0, f"{bot.name} saw unexpected {name}"
        assert len(bot.hand) == size


# ================================================================ 1. core


def test_core_flow_full_game(server) -> None:
    asyncio.run(_core_flow())


async def _core_flow() -> None:
    async with game_room(2, {"deck_mode": "random", "card_count": 20, "min_doubts": 0}) as bots:
        host, guest = bots
        assert len(host.hand) == 10 and len(guest.hand) == 10
        # hand_updated is private: neither client ever saw the other's cards
        host_ids = set(host.hand_ids())
        guest_ids = set(guest.hand_ids())
        assert not host_ids & guest_ids
        for name, data in guest.recorded:
            if name == "hand_updated":
                assert not {c["id"] for c in data["your_hand"]} & host_ids
        assert host.active == host.player_id  # join order = turn order

        # host dumps 4 / 4 / 2 with guest passing (burn) in between
        await burn_down(host, guest, 2)
        assert len(host.hand) == 2
        last = host.hand
        gm = guest.mark()
        await host.play([c["id"] for c in last], declared=last[0]["value"])
        played = await guest.wait_for("cards_played", since=gm)
        assert played["count"] == 2 and isinstance(played["doubt_deadline_ts"], int)
        await guest.wait_until("guest's turn", lambda: guest.active == guest.player_id)
        await guest.send("pass_turn")  # closes the window -> pending win lands
        over = await guest.wait_for("game_over")
        assert over["winner_id"] == host.player_id
        assert over["winner_name"] == "P1"
        assert over["reason"] == "empty_hand"
        await host.wait_until("host sees game over", lambda: host.game_over is not None)
        await host.wait_until("room finished", lambda: host.room_state == "finished")


# ===================================================== 2. rule enforcement


def test_error_play_out_of_turn(server) -> None:
    asyncio.run(_play_out_of_turn())


async def _play_out_of_turn() -> None:
    async with game_room(2) as bots:
        host, guest = bots
        marks = [b.mark() for b in bots]
        sizes = [len(b.hand) for b in bots]
        card = guest.hand[0]
        await guest.play([card["id"]], declared=card["value"])
        err = await guest.wait_for("error", since=marks[1])
        assert err["code"] == "out_of_turn"
        await assert_no_state_change(bots, marks, sizes)
        assert host.active == host.player_id


def test_error_cards_not_in_hand(server) -> None:
    asyncio.run(_cards_not_in_hand())


async def _cards_not_in_hand() -> None:
    async with game_room(2) as bots:
        host, guest = bots
        marks = [b.mark() for b in bots]
        sizes = [len(b.hand) for b in bots]
        # a fabricated id, and (worse) another player's real card id
        for bad_id in ("00000000-dead-beef-0000-000000000000", guest.hand[0]["id"]):
            m = host.mark()
            await host.play([bad_id], declared=3)
            err = await host.wait_for("error", since=m)
            assert err["code"] == "invalid_cards"
        await assert_no_state_change(bots, marks, sizes)


def test_error_play_size_bounds(server) -> None:
    asyncio.run(_play_size_bounds())


async def _play_size_bounds() -> None:
    async with game_room(2) as bots:
        host, _ = bots
        marks = [b.mark() for b in bots]
        sizes = [len(b.hand) for b in bots]
        m = host.mark()
        await host.play([], declared=3)  # 0 cards
        err = await host.wait_for("error", since=m)
        assert err["code"] == "invalid_cards"
        m = host.mark()
        await host.play(host.hand_ids()[:5], declared=3)  # 5 cards
        err = await host.wait_for("error", since=m)
        assert err["code"] == "invalid_cards"
        await assert_no_state_change(bots, marks, sizes)


def test_error_declared_value_mid_round(server) -> None:
    asyncio.run(_declared_mid_round())


async def _declared_mid_round() -> None:
    async with game_room(2) as bots:
        host, guest = bots
        card = host.hand[0]
        gm = guest.mark()
        await host.play([card["id"]], declared=card["value"])
        await guest.wait_for("cards_played", since=gm)
        await guest.wait_until("guest's turn", lambda: guest.active == guest.player_id)
        marks = [b.mark() for b in bots]
        sizes = [len(b.hand) for b in bots]
        await guest.play([guest.hand[0]["id"]], declared=5)  # round is locked
        err = await guest.wait_for("error", since=marks[1])
        assert err["code"] == "invalid_declaration"
        await assert_no_state_change(bots, marks, sizes)


def test_error_doubt_own_play(server) -> None:
    asyncio.run(_doubt_own_play())


async def _doubt_own_play() -> None:
    async with game_room(2) as bots:
        host, guest = bots
        card = host.hand[0]
        await host.play([card["id"]], declared=card["value"])
        await host.wait_for("cards_played")
        m = host.mark()
        await host.send("call_doubt")
        err = await host.wait_for("error", since=m)
        assert err["code"] == "invalid_action"
        await asyncio.sleep(DRAIN_S)
        assert host.count("doubt_resolved") == 0
        assert guest.count("doubt_resolved") == 0
        await host.wait_until("no quota counted", lambda: host.doubts.get(host.player_id) == 0)


def test_second_doubt_silently_ignored(server) -> None:
    asyncio.run(_second_doubt())


async def _second_doubt() -> None:
    async with game_room(3) as bots:
        p1, p2, p3 = bots
        card = p1.hand[0]
        await p1.play([card["id"]], declared=card["value"])
        await p2.wait_for("cards_played")
        await p3.wait_for("cards_played")
        marks = [b.mark() for b in bots]
        await p2.send("call_doubt")
        await p3.send("call_doubt")  # same window, must lose silently
        resolved = await p1.wait_for("doubt_resolved", since=marks[0])
        assert resolved["doubter_id"] == p2.player_id  # first doubter wins
        await asyncio.sleep(DRAIN_S)
        for bot, m in zip(bots, marks):
            assert bot.count("doubt_resolved", since=m) == 1
        assert p3.count("error", since=marks[2]) == 0  # silent rejection
        await p1.wait_until(
            "only P2's quota counted",
            lambda: p1.doubts.get(p2.player_id) == 1 and p1.doubts.get(p3.player_id) == 0,
        )


def test_quota_blocks_hand_emptying_play(server) -> None:
    asyncio.run(_quota_block())


async def _quota_block() -> None:
    async with game_room(2, {"deck_mode": "random", "card_count": 20, "min_doubts": 2}) as bots:
        host, guest = bots
        await burn_down(host, guest, 2)
        await host.wait_until(
            "host starts a round",
            lambda: host.active == host.player_id and host.declared is None,
        )
        marks = [b.mark() for b in bots]
        sizes = [len(b.hand) for b in bots]
        await host.play(host.hand_ids(), declared=host.hand[0]["value"])
        err = await host.wait_for("error", since=marks[0])
        assert err["code"] == "quota_block"
        assert err["message"] == "You need 2 more doubts before you can play your last cards."
        await assert_no_state_change(bots, marks, sizes)


# ====================================================== 3. round mechanics


def test_pass_around_burns_pile(server) -> None:
    asyncio.run(_pass_around_burn())


async def _pass_around_burn() -> None:
    async with game_room(3, {"deck_mode": "random", "card_count": 30}) as bots:
        p1, p2, p3 = bots
        cards = p1.hand[:2]
        await p1.play([c["id"] for c in cards], declared=cards[0]["value"])
        for passer in (p2, p3):
            await passer.wait_until("their turn", lambda b=passer: b.active == b.player_id)
            await passer.send("pass_turn")
        burned = await p1.wait_for("round_burned")
        assert burned == {"new_starter_id": p1.player_id, "burned_count": 2}
        await p1.wait_until(
            "p1 starts fresh round",
            lambda: p1.active == p1.player_id and p1.declared is None,
        )
        # burned pile is gone for good: new round starts from a clean pile
        card = p1.hand[0]
        m = p2.mark()
        await p1.play([card["id"]], declared=card["value"])
        played = await p2.wait_for("cards_played", since=m)
        assert played["pile_size"] == 1


# ===================================================== 4. doubt resolution


def test_doubt_lie_player_picks_up_pile(server) -> None:
    asyncio.run(_doubt_lie())


async def _doubt_lie() -> None:
    async with game_room(2) as bots:
        host, guest = bots
        start_size = len(host.hand)
        card = host.hand[0]
        await host.play([card["id"]], declared=wrong_value(card["value"]))
        await guest.wait_for("cards_played")
        await guest.send("call_doubt")
        resolved = await guest.wait_for("doubt_resolved")
        assert resolved["was_lie"] is True
        assert resolved["pile_goes_to"] == host.player_id
        assert resolved["new_starter_id"] == guest.player_id
        assert [c["value"] for c in resolved["revealed_cards"]] == [card["value"]]
        await host.wait_until("host took pile back", lambda: len(host.hand) == start_size)
        await guest.wait_until(
            "guest quota counted win", lambda: guest.doubts.get(guest.player_id) == 1
        )
        await guest.wait_until("guest starts next round", lambda: guest.active == guest.player_id)


def test_doubt_truth_doubter_picks_up_pile(server) -> None:
    asyncio.run(_doubt_truth())


async def _doubt_truth() -> None:
    async with game_room(2) as bots:
        host, guest = bots
        guest_start = len(guest.hand)
        card = host.hand[0]
        await host.play([card["id"]], declared=card["value"])
        await guest.wait_for("cards_played")
        await guest.send("call_doubt")
        resolved = await guest.wait_for("doubt_resolved")
        assert resolved["was_lie"] is False
        assert resolved["pile_goes_to"] == guest.player_id
        assert resolved["new_starter_id"] == host.player_id
        await guest.wait_until(
            "guest ate the pile", lambda: len(guest.hand) == guest_start + 1
        )
        await guest.wait_until(
            "guest quota counted lose", lambda: guest.doubts.get(guest.player_id) == 1
        )
        await host.wait_until("host starts next round", lambda: host.active == host.player_id)


# ============================================================== 5. timers


def test_doubt_after_window_expiry_rejected(server) -> None:
    asyncio.run(_doubt_after_expiry())


async def _doubt_after_expiry() -> None:
    async with game_room(2) as bots:
        host, guest = bots
        card = host.hand[0]
        await host.play([card["id"]], declared=card["value"])
        await guest.wait_for("cards_played")
        await asyncio.sleep(DOUBT_WINDOW_S + 0.6)  # server timer closes the window
        m = guest.mark()
        await guest.send("call_doubt")
        await asyncio.sleep(DRAIN_S)
        assert guest.count("doubt_resolved", since=m) == 0
        assert host.count("doubt_resolved") == 0
        await guest.wait_until("no quota counted", lambda: guest.doubts.get(guest.player_id) == 0)
        # pile untouched by the late doubt: passing now burns exactly 1 card
        await guest.send("pass_turn")
        burned = await guest.wait_for("round_burned")
        assert burned["burned_count"] == 1


def test_next_players_action_closes_window_early(server) -> None:
    asyncio.run(_early_window_close())


async def _early_window_close() -> None:
    async with game_room(3, {"deck_mode": "random", "card_count": 30}) as bots:
        p1, p2, p3 = bots
        card = p1.hand[0]
        await p1.play([card["id"]], declared=card["value"])
        await p2.wait_until("p2's turn", lambda: p2.active == p2.player_id)
        await p2.send("pass_turn")  # closes the window well before 5 s
        await p3.wait_for("player_passed")
        m = p3.mark()
        await p3.send("call_doubt")
        await asyncio.sleep(DRAIN_S)
        for bot in bots:
            assert bot.count("doubt_resolved") == 0
        await p3.wait_until("no quota counted", lambda: p3.doubts.get(p3.player_id) == 0)
        # pile intact: p3 passing completes the pass-around and burns 1 card
        await p3.send("pass_turn")
        burned = await p3.wait_for("round_burned", since=m)
        assert burned["burned_count"] == 1


# ================================================ 6. last-play edge cases


def test_last_play_truthful_doubted_player_still_wins(server) -> None:
    asyncio.run(_last_play_truth())


async def _last_play_truth() -> None:
    async with game_room(2, {"deck_mode": "random", "card_count": 20, "min_doubts": 0}) as bots:
        host, guest = bots
        await burn_down(host, guest, 1)
        card = host.hand[0]
        gm = guest.mark()
        await host.play([card["id"]], declared=card["value"])  # truthful, hand-emptying
        await guest.wait_for("cards_played", since=gm)
        await guest.send("call_doubt")
        resolved = await guest.wait_for("doubt_resolved", since=gm)
        assert resolved["was_lie"] is False
        assert resolved["pile_goes_to"] == guest.player_id
        over = await guest.wait_for("game_over", since=gm)
        assert over["winner_id"] == host.player_id
        assert over["reason"] == "empty_hand"
        await guest.wait_until("doubter still ate the pile", lambda: len(guest.hand) == 11)


def test_last_play_lie_doubted_game_continues(server) -> None:
    asyncio.run(_last_play_lie())


async def _last_play_lie() -> None:
    async with game_room(2, {"deck_mode": "random", "card_count": 20, "min_doubts": 0}) as bots:
        host, guest = bots
        await burn_down(host, guest, 1)
        card = host.hand[0]
        gm = guest.mark()
        await host.play([card["id"]], declared=wrong_value(card["value"]))  # lying dump
        await guest.wait_for("cards_played", since=gm)
        await guest.send("call_doubt")
        resolved = await guest.wait_for("doubt_resolved", since=gm)
        assert resolved["was_lie"] is True
        assert resolved["pile_goes_to"] == host.player_id
        await host.wait_until("host took the pile back", lambda: len(host.hand) == 1)
        await asyncio.sleep(DRAIN_S)
        assert host.game_over is None and guest.game_over is None
        await guest.wait_until("game still playing", lambda: guest.room_state == "playing")
        await guest.wait_until("guest starts next round", lambda: guest.active == guest.player_id)


# ============================================ 7. disconnect / reconnect


def test_disconnect_reconnect_within_grace_restores_hand(server) -> None:
    asyncio.run(_reconnect_within_grace())


async def _reconnect_within_grace() -> None:
    async with game_room(3, {"deck_mode": "random", "card_count": 30}) as bots:
        p1, p2, p3 = bots
        hand_before = sorted((c["id"], c["value"]) for c in p3.hand)
        m1 = p1.mark()
        before_ms = time.time() * 1000
        await p3.sio.disconnect()  # p3 is not the active player
        gone = await p1.wait_for("player_disconnected", since=m1)
        assert gone["player_id"] == p3.player_id
        assert before_ms + GRACE_MS - 500 <= gone["grace_deadline_ts"] <= before_ms + GRACE_MS + 1500

        fresh = Bot("P3-back")
        try:
            await fresh.sio.connect(URL, wait_timeout=10)
            fresh.room_code, fresh.session_token = p3.room_code, p3.session_token
            ack = await fresh.sio.call(
                "reconnect_player",
                {"room_code": fresh.room_code, "session_token": fresh.session_token},
            )
            assert ack.get("player_id") == p3.player_id
            fresh.player_id = p3.player_id
            back = await p1.wait_for("player_reconnected", since=m1)
            assert back["player_id"] == p3.player_id
            await fresh.wait_until("hand restored", lambda: len(fresh.hand) == 10)
            assert sorted((c["id"], c["value"]) for c in fresh.hand) == hand_before
            await fresh.wait_until("turn state resent", lambda: fresh.active is not None)
            await asyncio.sleep(DRAIN_S)
            assert p1.count("player_removed") == 0  # grace timer was cancelled
        finally:
            if fresh.sio.connected:
                await fresh.sio.disconnect()


def test_grace_expiry_removes_player_game_continues(server) -> None:
    asyncio.run(_grace_expiry())


async def _grace_expiry() -> None:
    async with game_room(3, {"deck_mode": "random", "card_count": 30}) as bots:
        p1, p2, p3 = bots
        m1 = p1.mark()
        await p3.sio.disconnect()
        await p1.wait_for("player_disconnected", since=m1)
        removed = await p1.wait_for("player_removed", since=m1, timeout=GRACE_MS / 1000 + 4)
        assert removed["player_id"] == p3.player_id
        assert removed["reason"] == "disconnect_timeout"
        await p1.wait_until(
            "seat gone, cards discarded",
            lambda: p3.player_id not in p1.counts and len(p1.counts) == 2,
        )
        # game continues between the two survivors
        card = p1.hand[0]
        m2 = p2.mark()
        await p1.play([card["id"]], declared=card["value"])
        await p2.wait_for("cards_played", since=m2)
        assert p1.game_over is None


def test_two_player_forfeit_on_removal(server) -> None:
    asyncio.run(_forfeit())


async def _forfeit() -> None:
    # default min_doubts=2 and host has doubted 0 times: quota must be waived
    async with game_room(2) as bots:
        host, guest = bots
        m = host.mark()
        await guest.sio.disconnect()
        await host.wait_for("player_disconnected", since=m)
        over = await host.wait_for("game_over", since=m, timeout=GRACE_MS / 1000 + 4)
        assert over["winner_id"] == host.player_id
        assert over["reason"] == "forfeit"


# ========================================================= 8. concurrency


def test_concurrent_doubts_resolve_exactly_once(server) -> None:
    for _ in range(20):
        asyncio.run(_concurrent_doubts_once())


async def _concurrent_doubts_once() -> None:
    async with game_room(3) as bots:  # defaults: random, 36 cards, 12 each
        p1, p2, p3 = bots
        card = p1.hand[0]
        marks = [b.mark() for b in bots]
        await p1.play([card["id"]], declared=card["value"])
        await p2.wait_for("cards_played", since=marks[1])
        await p3.wait_for("cards_played", since=marks[2])
        await asyncio.gather(p2.send("call_doubt"), p3.send("call_doubt"))
        resolved = await p1.wait_for("doubt_resolved", since=marks[0])
        assert resolved["doubter_id"] in (p2.player_id, p3.player_id)
        await asyncio.sleep(0.25)
        for bot, m in zip(bots, marks):
            assert bot.count("doubt_resolved", since=m) == 1
        # pile transferred exactly once: totals conserved, one quota counted
        await p1.wait_until(
            "one doubt counted", lambda: sum(p1.doubts.values()) == 1, timeout=5
        )
        assert sum(p1.counts.values()) == 36


# ========================================================== 9. deck modes


def test_random_deck_50_cards_4_players(server) -> None:
    asyncio.run(_random_deck())


async def _random_deck() -> None:
    async with game_room(4, {"deck_mode": "random", "card_count": 50}) as bots:
        hands = [bot.hand for bot in bots]
        assert [len(h) for h in hands] == [12, 12, 12, 12]  # floor(50/4), 2 discarded
        all_cards = [c for h in hands for c in h]
        assert len({c["id"] for c in all_cards}) == 48
        assert all(0 <= c["value"] <= 10 for c in all_cards)


def test_fixed_deck_k4_3_players(server) -> None:
    asyncio.run(_fixed_deck())


async def _fixed_deck() -> None:
    async with game_room(3, {"deck_mode": "fixed", "copies": 4}) as bots:
        hands = [bot.hand for bot in bots]
        assert sorted(len(h) for h in hands) == [14, 15, 15]  # all 44 dealt, uneven ok
        all_cards = [c for h in hands for c in h]
        assert len({c["id"] for c in all_cards}) == 44
        assert Counter(c["value"] for c in all_cards) == {v: 4 for v in range(11)}


# ================================================ TASK B: leakage audit


def _card_dicts(obj: Any, out: list[dict[str, Any]]) -> None:
    """Recursively collect every dict that carries a card 'value' field."""
    if isinstance(obj, dict):
        if "value" in obj:
            out.append(obj)
        for v in obj.values():
            _card_dicts(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _card_dicts(v, out)


def test_information_leakage_audit(server, capsys) -> None:
    report = asyncio.run(_leakage_game())
    with capsys.disabled():
        print("\n\n=== INFORMATION LEAKAGE REPORT (fields observed per event) ===")
        for name in sorted(report):
            print(f"  {name:22s} -> {sorted(report[name])}")
        print("  verdict: no cross-player card values observed in any payload")


async def _leakage_game() -> dict[str, set[str]]:
    """Plays a scripted 2-player game exercising every reveal path (truth
    doubt, lie doubt, burn, winning dump) while a driver-side simulation
    tracks exact card ownership. Then audits every recorded payload."""
    async with game_room(2, {"deck_mode": "random", "card_count": 20, "min_doubts": 1}) as bots:
        host, guest = bots
        sim: dict[str, dict[str, int]] = {
            b.player_id: {c["id"]: c["value"] for c in b.hand} for b in bots
        }
        assert not set(sim[host.player_id]) & set(sim[guest.player_id])
        ever_owned: dict[str, set[str]] = {pid: set(h) for pid, h in sim.items()}
        pile: dict[str, int] = {}
        allowed_reveals: set[frozenset[str]] = set()

        def sim_play(bot: Bot, ids: list[str]) -> None:
            for cid in ids:
                pile[cid] = sim[bot.player_id].pop(cid)

        def sim_pickup(receiver: Bot) -> None:
            sim[receiver.player_id].update(pile)
            ever_owned[receiver.player_id].update(pile)
            pile.clear()

        async def check_hand(bot: Bot) -> None:
            expect = sim[bot.player_id]
            await bot.wait_until(
                f"{bot.name} hand == simulation",
                lambda: {c["id"]: c["value"] for c in bot.hand} == expect,
            )

        # 1. truthful play, guest doubts -> guest eats the pile (quota 1)
        card = host.hand[0]
        await host.play([card["id"]], declared=card["value"])
        sim_play(host, [card["id"]])
        allowed_reveals.add(frozenset([card["id"]]))
        await guest.wait_for("cards_played")
        await guest.send("call_doubt")
        r = await guest.wait_for("doubt_resolved")
        assert r["was_lie"] is False
        sim_pickup(guest)
        await check_hand(guest)
        await check_hand(host)

        # 2. host truthful start; guest lies; host doubts -> guest eats pile
        card = host.hand[0]
        m = guest.mark()
        await host.play([card["id"]], declared=card["value"])
        sim_play(host, [card["id"]])
        allowed_reveals.add(frozenset([card["id"]]))
        locked = card["value"]
        await guest.wait_for("cards_played", since=m)
        await guest.wait_until("guest's turn", lambda: guest.active == guest.player_id)
        liar_card = next(c for c in guest.hand if c["value"] != locked)
        hm = host.mark()
        await guest.play([liar_card["id"]])
        sim_play(guest, [liar_card["id"]])
        allowed_reveals.add(frozenset([liar_card["id"]]))
        await host.wait_for("cards_played", since=hm)
        await host.send("call_doubt")
        r = await host.wait_for("doubt_resolved", since=hm)
        assert r["was_lie"] is True
        sim_pickup(guest)
        await check_hand(guest)
        await check_hand(host)

        # 3. pass-around burn
        await host.wait_until(
            "host starts", lambda: host.active == host.player_id and host.declared is None
        )
        card = host.hand[0]
        gm = guest.mark()
        await host.play([card["id"]], declared=card["value"])
        sim_play(host, [card["id"]])
        allowed_reveals.add(frozenset([card["id"]]))  # doubtable until pass
        await guest.wait_for("cards_played", since=gm)
        await guest.wait_until("guest's turn", lambda: guest.active == guest.player_id)
        await guest.send("pass_turn")
        await host.wait_for("round_burned")
        pile.clear()

        # 4. host dumps to victory (quota 1 met); guest passes every round
        while sim[host.player_id]:
            await host.wait_until(
                "host starts", lambda: host.active == host.player_id and host.declared is None
            )
            ids = list(sim[host.player_id])[:4]
            declared = sim[host.player_id][ids[0]]
            gm = guest.mark()
            await host.play(ids, declared=declared)
            sim_play(host, ids)
            allowed_reveals.add(frozenset(ids))
            await guest.wait_for("cards_played", since=gm)
            await guest.wait_until("guest's turn", lambda: guest.active == guest.player_id)
            hm = host.mark()
            await guest.send("pass_turn")
            if sim[host.player_id]:
                await host.wait_for("round_burned", since=hm)
                pile.clear()
        over = await guest.wait_for("game_over")
        assert over["winner_id"] == host.player_id

        # ---------------- audit every payload each client received --------
        report: dict[str, set[str]] = defaultdict(set)
        for bot in bots:
            for name, payload in bot.recorded:
                if isinstance(payload, dict):
                    report[name].update(payload.keys())
                found: list[dict[str, Any]] = []
                _card_dicts(payload, found)
                if name == "hand_updated":
                    assert set(payload.keys()) == {"your_hand"}
                    ids = {c["id"] for c in payload["your_hand"]}
                    assert ids <= ever_owned[bot.player_id], (
                        f"{bot.name} received a hand containing cards it never owned"
                    )
                elif name == "doubt_resolved":
                    revealed = frozenset(c["id"] for c in payload["revealed_cards"])
                    assert revealed in allowed_reveals, (
                        f"doubt_resolved revealed cards beyond the doubted play"
                    )
                    assert len(found) == len(payload["revealed_cards"]), (
                        f"doubt_resolved carried card values outside revealed_cards"
                    )
                else:
                    assert not found, (
                        f"{name} leaked card values to {bot.name}: {found}"
                    )
        return report
