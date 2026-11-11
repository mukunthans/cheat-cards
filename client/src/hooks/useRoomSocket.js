import { useCallback, useEffect, useRef, useState } from "react";
import socket from "../socket.js";

const EMPTY_ROOM = { players: [], host_id: null, settings: null, state: "lobby" };

function localDeadline(deadline, serverNow) {
  return deadline == null ? null : Date.now() + deadline - serverNow;
}

let toastSeq = 0;

/**
 * Owns the socket connection + all server-pushed state for one room.
 * Mount once a session (room_code, player_id, session_token) exists.
 * Server is the single source of truth; this hook only mirrors events.
 *
 * Always (re)joins via `reconnect_player` on mount/connect, even right after a
 * fresh create/join ack: the server may already have pushed the first
 * `room_update` before this hook's listeners were registered (create_room /
 * join_room emit it before the ack is even sent), so relying on that first
 * push alone can leave the UI stuck. `reconnect_player` is idempotent and
 * always re-sends full state, closing that race.
 */
export default function useRoomSocket(session) {
  const { roomCode, playerId, sessionToken } = session;

  const [ready, setReady] = useState(false); // authoritative seat state received
  const [room, setRoom] = useState(EMPTY_ROOM);
  const [hand, setHand] = useState([]);
  const [turn, setTurn] = useState({ activePlayerId: null, roundDeclaredValue: null, turnNumber: 0 });
  const [pile, setPile] = useState({ size: 0, lastPlayerId: null, lastCount: null, doubtDeadline: null });
  const [reveal, setReveal] = useState(null);
  const [burned, setBurned] = useState(null);
  const [gameOver, setGameOver] = useState(null);
  const [disconnected, setDisconnected] = useState({}); // player_id -> grace_deadline_ts
  const [lastEvent, setLastEvent] = useState(null); // { type, payload, ts } for a status line
  const [toasts, setToasts] = useState([]); // { id, message, tone }
  const [fatalError, setFatalError] = useState(null);

  const synced = useRef(false);
  const revealTimer = useRef(null);
  const lastReveal = useRef(null);
  const burnedTimer = useRef(null);
  const pushToast = useCallback((message, tone = "error") => {
    const id = ++toastSeq;
    setToasts((t) => [...t, { id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);

  useEffect(() => {
    let overdueTimer;
    if (!socket.connected) socket.connect();

    function pauseActions() {
      clearTimeout(overdueTimer);
      synced.current = false;
      setReady(false);
    }

    function onDisconnect(reason) {
      pauseActions();
      if (reason === "io server disconnect") setFatalError("seat_replaced");
    }

    function onVisible() {
      if (document.visibilityState === "visible" && socket.connected) onConnect();
    }

    function onConnect() {
      pauseActions();
      socket.emit(
        "reconnect_player",
        { room_code: roomCode, session_token: sessionToken },
        (ack) => {
          if (ack && ack.error) setFatalError(ack.error.message || "Could not rejoin the room.");
        }
      );
    }

    function onRoomUpdate(payload) {
      setRoom(payload);
    }

    function onSeatSync(payload) {
      setPile({
        size: payload.pile_size, lastPlayerId: payload.last_player_id, lastCount: payload.last_count,
        doubtDeadline: localDeadline(payload.doubt_deadline_ts, payload.server_now_ts),
      });
      setGameOver(payload.game_over);
      setDisconnected(Object.fromEntries(Object.entries(payload.disconnected).map(
        ([id, deadline]) => [id, localDeadline(deadline, payload.server_now_ts)]
      )));
      if (payload.reveal && !payload.game_over) {
        showReveal(payload.reveal, payload.reveal.expires_ts - payload.server_now_ts);
      } else {
        setReveal(null);
      }
      setBurned(null);
      synced.current = true;
      setReady(true);
    }

    function onGameStarted() {
      setReveal(null);
      setBurned(null);
      setGameOver(null);
      setPile({ size: 0, lastPlayerId: null, lastCount: null, doubtDeadline: null });
    }

    function onHandUpdated(payload) {
      setHand([...payload.your_hand].sort((a, b) => a.value - b.value));
    }

    function onTurnChanged(payload) {
      clearTimeout(overdueTimer);
      const deadline = localDeadline(payload.turn_deadline_ts, payload.server_now_ts);
      if (deadline != null) {
        // Recover a missed turn update after suspension or a stalled mobile transport.
        overdueTimer = setTimeout(onVisible, Math.max(0, deadline - Date.now()) + 2000);
      }
      setTurn({
        activePlayerId: payload.active_player_id,
        roundDeclaredValue: payload.round_declared_value,
        turnNumber: payload.turn_number,
        turnDeadline: deadline,
        timedOutPlayerId: payload.timed_out_player_id,
      });
    }

    function onCardsPlayed(payload) {
      setPile({
        size: payload.pile_size,
        lastPlayerId: payload.player_id,
        lastCount: payload.count,
        doubtDeadline: localDeadline(payload.doubt_deadline_ts, payload.server_now_ts),
      });
      setLastEvent({ type: "cards_played", payload, ts: Date.now() });
    }

    function onPlayerPassed(payload) {
      setPile((p) => ({ ...p, doubtDeadline: null }));
      setLastEvent({ type: "player_passed", payload, ts: Date.now() });
    }

    function onRoundBurned(payload) {
      setPile({ size: 0, lastPlayerId: null, lastCount: null, doubtDeadline: null });
      setBurned(payload);
      setLastEvent({ type: "round_burned", payload, ts: Date.now() });
      clearTimeout(burnedTimer.current);
      burnedTimer.current = setTimeout(() => setBurned(null), 3200);
    }

    function showReveal(payload, remaining) {
      if (payload.expires_ts === lastReveal.current) return;
      lastReveal.current = payload.expires_ts;
      clearTimeout(revealTimer.current);
      setReveal(payload);
      revealTimer.current = setTimeout(() => setReveal(null), Math.max(0, remaining));
    }

    function onDoubtResolved(payload) {
      setPile({ size: 0, lastPlayerId: null, lastCount: null, doubtDeadline: null });
      showReveal(payload, payload.expires_ts - payload.server_now_ts);
      setLastEvent({ type: "doubt_resolved", payload, ts: Date.now() });
    }

    function onPlayerDisconnected(payload) {
      setDisconnected((d) => ({ ...d, [payload.player_id]: payload.grace_deadline_ts }));
    }

    function onPlayerReconnected(payload) {
      setDisconnected((d) => {
        const next = { ...d };
        delete next[payload.player_id];
        return next;
      });
    }

    function onPlayerRemoved(payload) {
      setDisconnected((d) => {
        const next = { ...d };
        delete next[payload.player_id];
        return next;
      });
      setLastEvent({ type: "player_removed", payload, ts: Date.now() });
    }

    function onGameOver(payload) {
      clearTimeout(overdueTimer);
      setGameOver(payload);
    }

    function onError(payload) {
      pushToast(payload.message || "Something went wrong.");
    }

    document.addEventListener("visibilitychange", onVisible);
    socket.on("disconnect", onDisconnect);
    socket.on("seat_sync", onSeatSync);
    socket.on("connect", onConnect);
    socket.on("room_update", onRoomUpdate);
    socket.on("game_started", onGameStarted);
    socket.on("hand_updated", onHandUpdated);
    socket.on("turn_changed", onTurnChanged);
    socket.on("cards_played", onCardsPlayed);
    socket.on("player_passed", onPlayerPassed);
    socket.on("round_burned", onRoundBurned);
    socket.on("doubt_resolved", onDoubtResolved);
    socket.on("player_disconnected", onPlayerDisconnected);
    socket.on("player_reconnected", onPlayerReconnected);
    socket.on("player_removed", onPlayerRemoved);
    socket.on("game_over", onGameOver);
    socket.on("error", onError);

    if (socket.connected) onConnect();

    return () => {
      clearTimeout(overdueTimer);
      document.removeEventListener("visibilitychange", onVisible);
      socket.off("disconnect", onDisconnect);
      socket.off("seat_sync", onSeatSync);
      socket.off("connect", onConnect);
      socket.off("room_update", onRoomUpdate);
      socket.off("game_started", onGameStarted);
      socket.off("hand_updated", onHandUpdated);
      socket.off("turn_changed", onTurnChanged);
      socket.off("cards_played", onCardsPlayed);
      socket.off("player_passed", onPlayerPassed);
      socket.off("round_burned", onRoundBurned);
      socket.off("doubt_resolved", onDoubtResolved);
      socket.off("player_disconnected", onPlayerDisconnected);
      socket.off("player_reconnected", onPlayerReconnected);
      socket.off("player_removed", onPlayerRemoved);
      socket.off("game_over", onGameOver);
      socket.off("error", onError);
      clearTimeout(revealTimer.current);
      clearTimeout(burnedTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomCode, sessionToken]);

  const submit = useCallback((event, payload = {}) => {
    if (synced.current && socket.connected) {
      socket.emit(event, { ...payload, room_code: roomCode, player_id: playerId });
    }
  }, [roomCode, playerId]);

  const updateSettings = (settings) => submit("update_settings", { settings });
  const setPlayerReady = () => submit("player_ready");
  const playCards = (cardIds, declaredValue) => submit("play_cards", {
    card_ids: cardIds, declared_value: declaredValue,
  });
  const passTurn = () => submit("pass_turn");
  const callDoubt = () => submit("call_doubt");
  const dismissReveal = useCallback(() => setReveal(null), []);

  return {
    ready,
    room,
    hand,
    turn,
    pile,
    reveal,
    burned,
    gameOver,
    disconnected,
    lastEvent,
    toasts,
    fatalError,
    actions: { updateSettings, setPlayerReady, playCards, passTurn, callDoubt, dismissReveal },
  };
}
