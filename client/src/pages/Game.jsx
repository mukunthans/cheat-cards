export default function Game({ room, onLeave }) {
  return (
    <div className="min-h-screen bg-green-800 text-white p-8">
      <h1 className="text-2xl font-bold">Game Table — coming in Step 5</h1>
      <p className="mt-2 text-green-300">Room: {room.roomCode}</p>
      <button onClick={onLeave} className="mt-4 underline text-sm">
        Leave
      </button>
    </div>
  );
}
