import asyncio

import main
from room_manager import RoomError, RoomManager
import pytest


def test_room_admission_is_bounded_and_expires(monkeypatch):
    monkeypatch.setattr(main, "entry_counts", main.OrderedDict())
    monkeypatch.setattr(main, "ENTRY_LIMIT", 2)
    monkeypatch.setattr(main.sio, "get_environ", lambda sid: {"asgi.scope": {"client": (sid, 0)}})
    for sid in ["one", "one", "two"]:
        assert main._allow_entry(sid)
    assert not main._allow_entry("one")
    main._expire_entry_counts(main.time.monotonic() + main.ENTRY_WINDOW_S)
    assert not main.entry_counts
    assert main._allow_entry("one")


def test_missing_room_does_not_allocate_runtime(monkeypatch):
    monkeypatch.setattr(main, "_entry_guard", lambda sid: None)
    monkeypatch.setattr(main, "_allow_entry", lambda sid: True)
    before = set(main.runtimes)
    for request in (main.join_room, main.reconnect_player):
        reply = asyncio.run(request("test", {"room_code": "NO123"}))
        assert reply["error"]["code"] == "room_not_found"
    assert set(main.runtimes) == before


def test_room_capacity_recovers_after_cleanup(monkeypatch):
    import room_manager
    monkeypatch.setattr(room_manager, "MAX_ROOMS", 1)
    manager = RoomManager()
    room, host = manager.create_room("First")
    with pytest.raises(RoomError, match="tables are in use"):
        manager.create_room("Second")
    manager.mark_disconnected(room.code, host.id, 0)
    manager.cleanup(room_manager.EMPTY_ROOM_TTL_MS)
    manager.create_room("Second")
    assert manager.room_count == 1
