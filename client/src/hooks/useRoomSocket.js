import { useCallback, useEffect, useRef, useState } from "react";
import socket from "../socket.js";

const EMPTY_ROOM = { players: [], host_id: null, settings: null, state: "lobby" };

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

  const [ready, setReady] = useState(false); // first room_update received
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

  const revealTimer = useRef(null);
  const burnedTimer = useRef(null);

  const pushToast = useCallback((message, tone = "error") => {
    const id = ++toastSeq;
    setToasts((t) => [...t, { id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);

  useEffect(() => {
    if (!socket.connected) socket.connect();

    function onConnect() {
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
      setReady(true);
    }

    function onGameStarted() {
      setReveal(null);
      setBurned(null);
      setGameOver(null);
      setPile({ size: 0, lastPlayerId: null, lastCount: null, doubtDeadline: null });
    }

    function onHandUpdated(payload) {
      setHand(payload.your_hand);
    }

    function onTurnChanged(payload) {
      setTurn({
        activePlayerId: payload.active_player_id,
        roundDeclaredValue: payload.round_declared_value,
        turnNumber: payload.turn_number,
      });
    }

    function onCardsPlayed(payload) {
      setPile({
        size: payload.pile_size,
        lastPlayerId: payload.player_id,
        lastCount: payload.count,
        doubtDeadline: payload.doubt_deadline_ts,
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

    function onDoubtResolved(payload) {
      setPile({ size: 0, lastPlayerId: null, lastCount: null, doubtDeadline: null });
      setReveal(payload);
      setLastEvent({ type: "doubt_resolved", payload, ts: Date.now() });
      clearTimeout(revealTimer.current);
      revealTimer.current = setTimeout(() => setReveal(null), 5500);
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
      setGameOver(payload);
    }

    function onError(payload) {
      pushToast(payload.message || "Something went wrong.");
    }

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

  const updateSettings = useCallback(
    (settings) => socket.emit("update_settings", { room_code: roomCode, player_id: playerId, settings }),
    [roomCode, playerId]
  );
  const setPlayerReady = useCallback(
    () => socket.emit("player_ready", { room_code: roomCode, player_id: playerId }),
    [roomCode, playerId]
  );
  const playCards = useCallback(
    (cardIds, declaredValue) => {
      const payload = { room_code: roomCode, player_id: playerId, card_ids: cardIds };
      if (declaredValue !== undefined && declaredValue !== null) payload.declared_value = declaredValue;
      socket.emit("play_cards", payload);
    },
    [roomCode, playerId]
  );
  const passTurn = useCallback(
    () => socket.emit("pass_turn", { room_code: roomCode, player_id: playerId }),
    [roomCode, playerId]
  );
  const callDoubt = useCallback(
    () => socket.emit("call_doubt", { room_code: roomCode, player_id: playerId }),
    [roomCode, playerId]
  );
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
