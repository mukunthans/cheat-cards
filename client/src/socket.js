import { io } from "socket.io-client";

const URL =
  import.meta.env.MODE === "production"
    ? import.meta.env.VITE_SERVER_URL
    : "http://localhost:8000";

const socket = io(URL, { autoConnect: false });

export default socket;
