import { useState } from "react";
import Home from "./pages/Home.jsx";
import Game from "./pages/Game.jsx";

export default function App() {
  const [room, setRoom] = useState(null); // { roomCode, playerId, playerName }

  if (room) {
    return <Game room={room} onLeave={() => setRoom(null)} />;
  }
  return <Home onJoin={setRoom} />;
}
