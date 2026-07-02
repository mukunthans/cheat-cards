"""Rule tests for game.py and room_manager.py (Phase 2).

Covers the CLAUDE.md required minimum: both deck modes, dealing (leftover
discard vs deal-all), round lock, pass-around burn, doubt lie/truth, quota
block on last play, doubted last play (both outcomes), win, forfeit.
"""

from __future__ import annotations

import random
from collections import Counter

import pytest

from game import Event, Game, Settings, new_card
from room_manager import (
    EMPTY_ROOM_TTL_MS,
    FINISHED_ROOM_TTL_MS,
    GRACE_MS,
    RoomError,
    RoomManager,
)


def make_game(hands: list[list[int]], min_doubts: int = 0) -> Game:
    """Game with rigged hands: hands[i] is player p{i}'s card values."""
    players = [(f"p{i}", f"Player{i}") for i in range(len(hands))]
    game = Game(players, Settings(deck_mode="fixed", copies=4, min_doubts=min_doubts),
                rng=random.Random(7))
    for player, values in zip(game.players, hands):
        player.hand = [new_card(v) for v in values]
    return game


def card_ids(game: Game, player_id: str, values: list[int]) -> list[str]:
    """Ids of cards matching values (in order) from the player's hand."""
    pool = list(game.hand_of(player_id))
    picked: list[str] = []
    for value in values:
        card = next(c for c in pool if c.value == value)
        pool.remove(card)
        picked.append(card.id)
    return picked


def evt(events: list[Event], name: str) -> Event:
    return next(e for e in events if e.name == name)

def names(events: list[Event]) -> list[str]:
    return [e.name for e in events]

def assert_error(events: list[Event], code: str) -> Event:
    error = evt(events, "error")
    assert error.payload["code"] == code, error.payload
    return error


# ---------------------------------------------------------------- dealing

class TestDealing:
    def test_random_mode_discards_leftovers(self):
        game = Game([("a", "A"), ("b", "B"), ("c", "C")],
                    Settings(deck_mode="random", card_count=40), rng=random.Random(1))
        assert [len(p.hand) for p in game.players] == [13, 13, 13]  # 1 discarded
        assert game.pile == []

    def test_random_mode_values_in_range(self):
        game = Game([("a", "A"), ("b", "B")],
                    Settings(deck_mode="random", card_count=50), rng=random.Random(2))
        assert all(0 <= c.value <= 10 for p in game.players for c in p.hand)

    def test_random_mode_default_card_count(self):
        game = Game([("a", "A"), ("b", "B")], Settings(deck_mode="random"),
                    rng=random.Random(3))
        assert [len(p.hand) for p in game.players] == [12, 12]  # 12 * players

    @pytest.mark.parametrize("count", [29, 76])
    def test_random_mode_card_count_bounds(self, count):
        with pytest.raises(ValueError):
            Game([("a", "A"), ("b", "B"), ("c", "C")],
                 Settings(deck_mode="random", card_count=count))

    def test_fixed_mode_deals_all_uneven(self):
        game = Game([("a", "A"), ("b", "B"), ("c", "C")],
                    Settings(deck_mode="fixed", copies=4), rng=random.Random(4))
        sizes = sorted(len(p.hand) for p in game.players)
        assert sizes == [14, 15, 15]  # 44 cards, nothing discarded
        counts = Counter(c.value for p in game.players for c in p.hand)
        assert counts == {v: 4 for v in range(11)}  # card counting intact

    def test_fixed_mode_five_copies(self):
        game = Game([("a", "A"), ("b", "B")],
                    Settings(deck_mode="fixed", copies=5), rng=random.Random(5))
        assert sorted(len(p.hand) for p in game.players) == [27, 28]

    def test_fixed_mode_invalid_copies(self):
        with pytest.raises(ValueError):
            Game([("a", "A"), ("b", "B")], Settings(deck_mode="fixed", copies=3))

    def test_player_count_bounds(self):
        with pytest.raises(ValueError):
            Game([("a", "A")], Settings())
        with pytest.raises(ValueError):
            Game([(f"p{i}", "x") for i in range(5)], Settings())


# ------------------------------------------------------------ turn/round

class TestRounds:
    def test_starter_must_declare(self):
        game = make_game([[1, 2], [3, 4]])
        events = game.play_cards("p0", card_ids(game, "p0", [1]))
        assert_error(events, "invalid_declaration")

    def test_starter_cannot_pass(self):
        game = make_game([[1, 2], [3, 4]])
        assert_error(game.pass_turn("p0"), "invalid_action")

    def test_declared_value_locks_for_round(self):
        game = make_game([[5, 5], [7, 7], [8, 8]])
        game.play_cards("p0", card_ids(game, "p0", [5]), declared_value=5)
        redeclare = game.play_cards("p1", card_ids(game, "p1", [7]), declared_value=3)
        assert_error(redeclare, "invalid_declaration")
        follow = game.play_cards("p1", card_ids(game, "p1", [7]))
        assert evt(follow, "cards_played").payload["declared_value"] == 5

    def test_out_of_turn_rejected(self):
        game = make_game([[1, 2], [3, 4], [5, 6]])
        assert_error(game.play_cards("p2", card_ids(game, "p2", [5]), 5), "out_of_turn")
        assert_error(game.pass_turn("p1"), "out_of_turn")

    def test_play_size_limits(self):
        game = make_game([[1, 1, 1, 1, 1, 1], [2, 2]])
        assert_error(game.play_cards("p0", [], declared_value=1), "invalid_cards")
        too_many = card_ids(game, "p0", [1, 1, 1, 1, 1])
        assert_error(game.play_cards("p0", too_many, declared_value=1), "invalid_cards")

    def test_cards_must_be_in_hand(self):
        game = make_game([[1, 2], [3, 4]])
        assert_error(game.play_cards("p0", ["not-a-real-id"], 1), "invalid_cards")

    def test_pass_around_burns_pile(self):
        game = make_game([[3, 3, 9], [7, 7], [8, 8]])
        game.play_cards("p0", card_ids(game, "p0", [3, 3]), declared_value=3)
        game.pass_turn("p1")
        events = game.pass_turn("p2")
        burn = evt(events, "round_burned")
        assert burn.payload == {"new_starter_id": "p0", "burned_count": 2}
        assert game.pile == []
        assert game.round_declared_value is None
        assert game.active_player_id == "p0"

    def test_starter_plays_all_others_pass_edge(self):
        game = make_game([[3, 9], [7, 7]])
        game.play_cards("p0", card_ids(game, "p0", [3]), declared_value=3)
        events = game.pass_turn("p1")
        assert evt(events, "round_burned").payload["new_starter_id"] == "p0"


# ----------------------------------------------------------------- doubt

class TestDoubt:
    def test_doubt_lie_player_picks_up_pile(self):
        game = make_game([[3, 7, 1], [2, 2], [9, 9]])
        game.play_cards("p0", card_ids(game, "p0", [3, 7]), declared_value=3)
        events = game.call_doubt("p1")
        resolved = evt(events, "doubt_resolved").payload
        assert resolved["was_lie"] is True
        assert resolved["pile_goes_to"] == "p0"
        assert resolved["new_starter_id"] == "p1"
        assert sorted(c["value"] for c in resolved["revealed_cards"]) == [3, 7]
        assert len(game.hand_of("p0")) == 3  # 1 kept + 2 picked up
        assert game.pile == []
        assert game.active_player_id == "p1"
        assert game.round_declared_value is None

    def test_doubt_truth_doubter_picks_up_pile(self):
        game = make_game([[3, 3, 1], [2, 2], [9, 9]])
        game.play_cards("p0", card_ids(game, "p0", [3, 3]), declared_value=3)
        events = game.call_doubt("p1")
        resolved = evt(events, "doubt_resolved").payload
        assert resolved["was_lie"] is False
        assert resolved["pile_goes_to"] == "p1"
        assert resolved["new_starter_id"] == "p0"
        assert len(game.hand_of("p1")) == 4  # 2 kept + 2 picked up
        assert game.active_player_id == "p0"

    def test_doubt_counts_toward_quota_win_or_lose(self):
        lie = make_game([[4, 1], [2, 2]])
        lie.play_cards("p0", card_ids(lie, "p0", [4]), declared_value=5)
        lie.call_doubt("p1")
        assert lie._by_id["p1"].doubts_made == 1  # won the doubt

        truth = make_game([[5, 1], [2, 2]])
        truth.play_cards("p0", card_ids(truth, "p0", [5]), declared_value=5)
        truth.call_doubt("p1")
        assert truth._by_id["p1"].doubts_made == 1  # lost the doubt, still counts

    def test_doubt_reveals_only_last_play(self):
        game = make_game([[3, 3], [9, 1, 1], [2, 2]])
        game.play_cards("p0", card_ids(game, "p0", [3]), declared_value=3)
        game.play_cards("p1", card_ids(game, "p1", [9, 1]))  # lie, pile now 3
        events = game.call_doubt("p2")
        resolved = evt(events, "doubt_resolved").payload
        assert len(resolved["revealed_cards"]) == 2  # p1's cards only
        assert resolved["pile_goes_to"] == "p1"
        assert len(game.hand_of("p1")) == 1 + 3  # picked up entire pile

    def test_cannot_doubt_own_play(self):
        game = make_game([[3, 3], [2, 2]])
        game.play_cards("p0", card_ids(game, "p0", [3]), declared_value=3)
        assert_error(game.call_doubt("p0"), "invalid_action")

    def test_second_doubt_rejected_silently(self):
        game = make_game([[3, 3], [2, 2], [9, 9]])
        game.play_cards("p0", card_ids(game, "p0", [3]), declared_value=3)
        game.call_doubt("p1")
        assert game.call_doubt("p2") == []
        assert game._by_id["p2"].doubts_made == 0

    def test_doubt_after_next_action_rejected_silently(self):
        game = make_game([[3, 3], [2, 2], [9, 9]])
        game.play_cards("p0", card_ids(game, "p0", [3]), declared_value=3)
        game.pass_turn("p1")  # closes the window
        assert game.call_doubt("p2") == []

    def test_doubt_after_timer_close_rejected_silently(self):
        game = make_game([[3, 3], [2, 2]])
        game.play_cards("p0", card_ids(game, "p0", [3]), declared_value=3)
        game.close_doubt_window()  # 5 s timer fired
        assert game.call_doubt("p1") == []

    def test_cannot_doubt_a_pass(self):
        game = make_game([[3, 3], [2, 2], [9, 9]])
        game.play_cards("p0", card_ids(game, "p0", [3]), declared_value=3)
        game.pass_turn("p1")
        # window closed by the pass; the pass itself is not doubtable
        assert game.call_doubt("p0") == []


# ---------------------------------------------------------- quota & wins

class TestQuotaAndWin:
    def test_quota_blocks_hand_emptying_play(self):
        game = make_game([[5], [6, 6]], min_doubts=2)
        events = game.play_cards("p0", card_ids(game, "p0", [5]), declared_value=5)
        error = assert_error(events, "quota_block")
        assert error.payload["message"] == (
            "You need 2 more doubts before you can play your last cards."
        )
        assert len(game.hand_of("p0")) == 1  # nothing left the hand
        assert game.pile == []

    def test_quota_block_counts_remaining_doubts(self):
        game = make_game([[5], [6, 6]], min_doubts=2)
        game._by_id["p0"].doubts_made = 1
        events = game.play_cards("p0", card_ids(game, "p0", [5]), declared_value=5)
        assert "You need 1 more doubts" in evt(events, "error").payload["message"]

    def test_quota_met_allows_last_play(self):
        game = make_game([[5], [6, 6]], min_doubts=1)
        game._by_id["p0"].doubts_made = 1
        events = game.play_cards("p0", card_ids(game, "p0", [5]), declared_value=5)
        assert "cards_played" in names(events)
        assert game.pending_winner == "p0"

    def test_win_when_doubt_window_times_out(self):
        game = make_game([[5, 5], [6, 6]])
        game.play_cards("p0", card_ids(game, "p0", [5, 5]), declared_value=5)
        assert game.state == "playing"  # win is pending, not instant
        events = game.close_doubt_window()
        over = evt(events, "game_over").payload
        assert over == {"winner_id": "p0", "winner_name": "Player0", "reason": "empty_hand"}
        assert game.state == "finished"

    def test_win_when_next_player_acts(self):
        game = make_game([[5, 5], [6, 6]])
        game.play_cards("p0", card_ids(game, "p0", [5, 5]), declared_value=5)
        events = game.pass_turn("p1")  # closes the window -> pending win lands
        assert evt(events, "game_over").payload["winner_id"] == "p0"
        assert "player_passed" not in names(events)  # game ended first

    def test_doubted_last_play_lie_continues_game(self):
        game = make_game([[4], [6, 6]])
        game.play_cards("p0", card_ids(game, "p0", [4]), declared_value=5)  # lie
        events = game.call_doubt("p1")
        assert "game_over" not in names(events)
        assert game.state == "playing"
        assert len(game.hand_of("p0")) == 1  # picked the pile back up
        assert game.active_player_id == "p1"  # doubter won, starts next round

    def test_doubted_last_play_truth_wins(self):
        game = make_game([[5], [6, 6]])
        game.play_cards("p0", card_ids(game, "p0", [5]), declared_value=5)  # truth
        events = game.call_doubt("p1")
        resolved = evt(events, "doubt_resolved").payload
        assert resolved["was_lie"] is False
        assert resolved["pile_goes_to"] == "p1"
        assert evt(events, "game_over").payload["reason"] == "empty_hand"
        assert len(game.hand_of("p1")) == 3  # doubter still eats the pile

    def test_hand_emptying_play_needs_no_doubt_to_win(self):
        # quota 0 by default in make_game: covered above; explicit quota case:
        game = make_game([[5], [6, 6]], min_doubts=1)
        game._by_id["p0"].doubts_made = 3
        game.play_cards("p0", card_ids(game, "p0", [5]), declared_value=5)
        events = game.close_doubt_window()
        assert evt(events, "game_over").payload["winner_id"] == "p0"


# ------------------------------------------------------- removal/forfeit

class TestRemoval:
    def test_removed_players_cards_are_discarded_not_piled(self):
        game = make_game([[3, 3, 1], [2, 2], [9, 9]])
        game.play_cards("p0", card_ids(game, "p0", [3, 3]), declared_value=3)
        game.remove_player("p2")
        assert len(game.pile) == 2  # untouched
        assert game.hand_of("p2") == []
        assert game.turn_order == ["p0", "p1"]

    def test_forfeit_waives_quota(self):
        game = make_game([[3, 3], [2, 2]], min_doubts=5)
        events = game.remove_player("p1")
        over = evt(events, "game_over").payload
        assert over["winner_id"] == "p0"
        assert over["reason"] == "forfeit"

    def test_removing_active_player_advances_turn(self):
        game = make_game([[3, 3], [2, 2], [9, 9]])
        game.play_cards("p0", card_ids(game, "p0", [3]), declared_value=3)
        events = game.remove_player("p1")  # p1 was active
        assert evt(events, "turn_changed").payload["active_player_id"] == "p2"

    def test_burn_still_happens_after_last_player_removed(self):
        game = make_game([[3, 3], [2, 2], [9, 9]])
        game.play_cards("p0", card_ids(game, "p0", [3]), declared_value=3)
        game.remove_player("p0")  # the only player who played leaves
        game.pass_turn("p1")
        events = game.pass_turn("p2")  # full pass cycle of remaining players
        assert "round_burned" in names(events)
        assert game.pile == []

    def test_gone_players_play_cannot_be_doubted(self):
        game = make_game([[3, 3], [2, 2], [9, 9]])
        game.play_cards("p0", card_ids(game, "p0", [3]), declared_value=3)
        game.remove_player("p0")
        assert game.call_doubt("p1") == []


# ---------------------------------------------------------- room manager

class TestRoomManager:
    def test_create_room_code_and_token(self):
        manager = RoomManager(rng=random.Random(1))
        room, player = manager.create_room("Alice")
        assert len(room.code) == 5
        assert room.code.isalnum() and room.code == room.code.upper()
        assert player.session_token
        assert room.host_id == player.id
        assert room.state == "lobby"

    def test_join_and_ready_starts_game(self):
        manager = RoomManager(rng=random.Random(1))
        room, host = manager.create_room("Alice")
        _, joiner = manager.join_room(room.code, "Bob")
        _, events = manager.set_ready(room.code, host.id)
        assert events == []  # only one ready
        _, events = manager.set_ready(room.code, joiner.id, rng=random.Random(9))
        assert "game_started" in names(events)
        assert room.state == "playing"
        started = evt(events, "game_started").payload
        assert started["turn_order"] == [host.id, joiner.id]  # join order

    def test_single_ready_player_does_not_start(self):
        manager = RoomManager(rng=random.Random(1))
        room, host = manager.create_room("Alice")
        _, events = manager.set_ready(room.code, host.id)
        assert events == [] and room.state == "lobby"

    def test_room_full_rejected(self):
        manager = RoomManager(rng=random.Random(1))
        room, _ = manager.create_room("Alice")
        for i in range(3):
            manager.join_room(room.code, f"P{i}")
        with pytest.raises(RoomError) as exc:
            manager.join_room(room.code, "Late")
        assert exc.value.code == "room_full"

    def test_join_after_start_rejected(self):
        manager = RoomManager(rng=random.Random(1))
        room, host = manager.create_room("Alice")
        _, joiner = manager.join_room(room.code, "Bob")
        manager.set_ready(room.code, host.id)
        manager.set_ready(room.code, joiner.id, rng=random.Random(9))
        with pytest.raises(RoomError) as exc:
            manager.join_room(room.code, "Late")
        assert exc.value.code == "game_in_progress"

    def test_only_host_updates_settings_lobby_only(self):
        manager = RoomManager(rng=random.Random(1))
        room, host = manager.create_room("Alice")
        _, joiner = manager.join_room(room.code, "Bob")
        with pytest.raises(RoomError) as exc:
            manager.update_settings(room.code, joiner.id, {"min_doubts": 3})
        assert exc.value.code == "not_host"
        manager.update_settings(room.code, host.id, {"min_doubts": 3, "deck_mode": "fixed"})
        assert room.settings.min_doubts == 3
        manager.set_ready(room.code, host.id)
        manager.set_ready(room.code, joiner.id, rng=random.Random(9))
        with pytest.raises(RoomError) as exc:
            manager.update_settings(room.code, host.id, {"min_doubts": 1})
        assert exc.value.code == "game_in_progress"

    def test_invalid_settings_rejected(self):
        manager = RoomManager(rng=random.Random(1))
        room, host = manager.create_room("Alice")
        manager.join_room(room.code, "Bob")
        with pytest.raises(RoomError) as exc:
            manager.update_settings(room.code, host.id, {"card_count": 5})
        assert exc.value.code == "invalid_settings"
        with pytest.raises(RoomError):
            manager.update_settings(room.code, host.id, {"nonsense": True})

    def test_host_leaving_lobby_passes_host(self):
        manager = RoomManager(rng=random.Random(1))
        room, host = manager.create_room("Alice")
        _, joiner = manager.join_room(room.code, "Bob")
        _, removed, _ = manager.mark_disconnected(room.code, host.id, now_ms=0)
        assert removed is True  # lobby disconnects drop the player outright
        assert room.host_id == joiner.id

    def test_disconnect_in_game_holds_seat_then_reconnect(self):
        manager = RoomManager(rng=random.Random(1))
        room, host = manager.create_room("Alice")
        _, joiner = manager.join_room(room.code, "Bob")
        manager.set_ready(room.code, host.id)
        manager.set_ready(room.code, joiner.id, rng=random.Random(9))
        _, removed, deadline = manager.mark_disconnected(room.code, joiner.id, now_ms=1_000)
        assert removed is False
        assert deadline == 1_000 + GRACE_MS
        _, back = manager.reconnect(room.code, joiner.session_token, now_ms=10_000)
        assert back.id == joiner.id and back.connected is True

    def test_reconnect_bad_token(self):
        manager = RoomManager(rng=random.Random(1))
        room, _ = manager.create_room("Alice")
        with pytest.raises(RoomError) as exc:
            manager.reconnect(room.code, "wrong-token", now_ms=0)
        assert exc.value.code == "invalid_token"

    def test_grace_expiry_removal_forfeits_game(self):
        manager = RoomManager(rng=random.Random(1))
        room, host = manager.create_room("Alice")
        _, joiner = manager.join_room(room.code, "Bob")
        manager.set_ready(room.code, host.id)
        manager.set_ready(room.code, joiner.id, rng=random.Random(9))
        manager.mark_disconnected(room.code, joiner.id, now_ms=0)
        _, events = manager.remove_player(room.code, joiner.id, now_ms=GRACE_MS)
        assert evt(events, "game_over").payload["reason"] == "forfeit"
        assert room.state == "finished"
        assert room.finished_at_ms == GRACE_MS

    def test_cleanup_empty_and_finished_rooms(self):
        manager = RoomManager(rng=random.Random(1))
        empty_room, solo = manager.create_room("Alice")
        manager.mark_disconnected(empty_room.code, solo.id, now_ms=0)
        finished_room, _ = manager.create_room("Bob")
        manager.note_game_over(finished_room.code, now_ms=0)

        assert manager.cleanup(now_ms=EMPTY_ROOM_TTL_MS - 1) == []
        assert manager.cleanup(now_ms=EMPTY_ROOM_TTL_MS) == [empty_room.code]
        assert manager.cleanup(now_ms=FINISHED_ROOM_TTL_MS) == [finished_room.code]
        assert manager.room_count == 0

    def test_empty_name_rejected(self):
        manager = RoomManager(rng=random.Random(1))
        with pytest.raises(RoomError) as exc:
            manager.create_room("   ")
        assert exc.value.code == "invalid_name"
