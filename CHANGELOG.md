# Cheat Cards release history

Newest releases appear first. Each entry describes what changed for players and links to the corresponding code.

## [4.0.0] — 2026-11-12

- Players now take turns choosing the number for a new round. At a table with A, B and C, the openers go **A → B → C → A**, whether the round ends with a doubt or everyone passing.
- If A times out or uses an allowed pass before choosing a number and B opens instead, C opens the following round. The rotation skips players who have left the game.
- Added an [illustrated architecture guide](client/public/architecture.html) covering how devices connect, how the server handles a play or doubt, and what happens when a player reconnects.

## [3.0.0] — 2026-11-11

- Returning to a game restores your hand, the pile, the current turn, and any reveal or result. Turn timers follow the server clock, and controls pause while your device reconnects.
- Fixed a deadlock when everyone had one card, everyone still owed doubts, and the pile was empty. The opener can play their last card and the other players get the usual five seconds to challenge.
- Made the round number and the number of cards just added to the pile easier to read. Players can switch personal turn hints on or off from the home screen.
- Protected player seats so only one connection can act for a seat at a time. Added limits on stored rooms and repeated requests to create or join rooms.

## [2.0.0] — 2026-11-10

- Sorted each hand by number and removed the four-card limit. Players can select their whole hand once they meet the last-card rule.
- Gave each turn 30 seconds, including the opening turn. An opener with one card who still owes a doubt can pass immediately.
- Required everyone to pass after the most recent play before the pile clears. Adding cards resets the pass count.
- After a doubt, play resumed with the seat after the challenged player. After everyone passed, the seat after the final passer opened. Version 4 changed how the next opener is chosen.
- Added a sound when a bluff is caught and updated the software packages used by the game with security fixes.

## [Original game] — before 2.0.0

The original game had no v1 release tag. The link points to the last revision before work on version 2 began.

- Two to four players could create a private room, join with a code, choose deck and doubt settings, and mark themselves ready.
- Players could declare a number, play cards face down, bluff, pass, and challenge the latest play. A player who cleared their hand and survived the challenge window won.
- Added a mobile table layout, reconnection support, and separate browser seats for testing multiplayer on one computer.
- Set up the Render backend and Netlify frontend and added automated tests for the rules and multiplayer connections.

[4.0.0]: https://github.com/mukunthans/cheat-cards/releases/tag/v4.0.0
[3.0.0]: https://github.com/mukunthans/cheat-cards/releases/tag/v3.0.0
[2.0.0]: https://github.com/mukunthans/cheat-cards/releases/tag/v2.0.0
[Original game]: https://github.com/mukunthans/cheat-cards/tree/01f59326aba3b2af7bcd167e8420707fe4371928
