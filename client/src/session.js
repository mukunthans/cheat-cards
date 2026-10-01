/**
 * Storage keys for the local session.
 *
 * localStorage is shared by every tab on an origin, so testing 2–4 players on one
 * machine would otherwise have each new tab reconnect as the first player. An
 * optional `?seat=` query param namespaces the keys, making
 * `/?seat=1`, `/?seat=2`, … independent players in ordinary tabs. With no
 * `?seat=` the keys are unchanged, so deployed behaviour is exactly as before.
 */
const seat = new URLSearchParams(window.location.search).get("seat");
const suffix = seat ? `_${seat.replace(/[^a-zA-Z0-9]/g, "").slice(0, 8)}` : "";

export const SESSION_KEY = `cheatcards_session${suffix}`;
export const NAME_KEY = `cheatcards_name${suffix}`;
