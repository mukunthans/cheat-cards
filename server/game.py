"""Pure game logic for Cheat Cards. No sockets, no async, no wall clocks.

Every action method mutates the Game and returns a list of Events for the
socket layer to emit. Time-based payloads (doubt_deadline_ts, grace timers)
are added by the socket layer -- the game only flags that a window opened
and exposes close_doubt_window() for the layer's 5-second timer.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Any

CARD_VALUES: tuple[int, ...] = tuple(range(11))  # 0..10
MIN_PLAY: int = 1
MAX_PLAY: int = 4

ROOM: str = "room"  # Event.to sentinel: broadcast to the whole room


@dataclass
class Card:
    id: str
    value: int

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "value": self.value}


def new_card(value: int) -> Card:
    return Card(id=str(uuid.uuid4()), value=value)


@dataclass
class Settings:
    deck_mode: str = "random"  # "random" | "fixed"
    card_count: int | None = None  # random mode; None = 12 * num_players
    copies: int = 4  # fixed mode: 4 | 5
    min_doubts: int = 2  # 0..10

    def validate(self, num_players: int) -> None:
        if self.deck_mode not in ("random", "fixed"):
            raise ValueError(f"deck_mode must be 'random' or 'fixed', got {self.deck_mode!r}")
        if not 0 <= self.min_doubts <= 10:
            raise ValueError("min_doubts must be between 0 and 10")
        if self.deck_mode == "random":
            n = self.effective_card_count(num_players)
            lo, hi = 10 * num_players, 25 * num_players
            if not lo <= n <= hi:
                raise ValueError(f"card_count must be between {lo} and {hi} for {num_players} players")
        elif self.copies not in (4, 5):
            raise ValueError("copies must be 4 or 5")

    def effective_card_count(self, num_players: int) -> int:
        return self.card_count if self.card_count is not None else 12 * num_players

    def to_dict(self) -> dict[str, Any]:
        return {
            "deck_mode": self.deck_mode,
            "card_count": self.card_count,
            "copies": self.copies,
            "min_doubts": self.min_doubts,
        }


@dataclass
class Player:
    id: str
    name: str
    hand: list[Card] = field(default_factory=list)
    doubts_made: int = 0


@dataclass
class Event:
    name: str
    payload: dict[str, Any]
    to: str = ROOM  # ROOM or a player_id (private emit)


class Game:
    """State machine for one game. Players are (id, name) in join order."""

    def __init__(
        self,
        players: list[tuple[str, str]],
        settings: Settings,
        rng: random.Random | None = None,
    ) -> None:
        if not 2 <= len(players) <= 4:
            raise ValueError("Game requires 2-4 players")
        settings.validate(len(players))
        self.rng: random.Random = rng or random.Random()
        self.settings: Settings = settings
        self.players: list[Player] = [Player(id=pid, name=name) for pid, name in players]
        self._by_id: dict[str, Player] = {p.id: p for p in self.players}
        self.turn_order: list[str] = [p.id for p in self.players]
        self.active_index: int = 0
        self.turn_number: int = 1
        self.round_declared_value: int | None = None
        self.pile: list[Card] = []
        self.last_play: tuple[str, list[Card]] | None = None
        self.last_player_who_played: str | None = None
        self.passes_since_last_play: int = 0
        self.doubt_window_open: bool = False
        self.pending_winner: str | None = None
        self.state: str = "playing"  # "playing" | "finished"
        self.winner_id: str | None = None
        self._deal()

    # ------------------------------------------------------------- dealing

    def _deal(self) -> None:
        n_players = len(self.players)
        if self.settings.deck_mode == "random":
            n = self.settings.effective_card_count(n_players)
            deck = [new_card(self.rng.randint(0, 10)) for _ in range(n)]
            per = n // n_players
            for i, player in enumerate(self.players):
                player.hand = deck[i * per : (i + 1) * per]
            # deck[per * n_players:] are leftovers: discarded, never revealed
        else:
            deck = [new_card(v) for v in CARD_VALUES for _ in range(self.settings.copies)]
            self.rng.shuffle(deck)
            for i, card in enumerate(deck):  # round-robin, ALL cards dealt
                self.players[i % n_players].hand.append(card)

    def start_events(self) -> list[Event]:
        events = [
            Event(
                "game_started",
                {"turn_order": list(self.turn_order), "settings": self.settings.to_dict()},
            )
        ]
        events.extend(self._hand_event(p) for p in self.players)
        events.append(self._turn_event())
        return events

    # ------------------------------------------------------------- actions

    def play_cards(
        self,
        player_id: str,
        card_ids: list[str],
        declared_value: int | None = None,
    ) -> list[Event]:
        err = self._validate_turn(player_id)
        if err is not None:
            return [err]
        player = self._by_id[player_id]
        if not MIN_PLAY <= len(card_ids) <= MAX_PLAY:
            return [self._error(player_id, "invalid_cards", "You must play 1-4 cards.")]
        if len(set(card_ids)) != len(card_ids):
            return [self._error(player_id, "invalid_cards", "Duplicate card ids in play.")]
        hand_by_id = {c.id: c for c in player.hand}
        if any(cid not in hand_by_id for cid in card_ids):
            return [self._error(player_id, "invalid_cards", "Card is not in your hand.")]
        if self.round_declared_value is None:
            if declared_value is None:
                return [
                    self._error(
                        player_id, "invalid_declaration", "You must declare a value to start the round."
                    )
                ]
            if declared_value not in CARD_VALUES:
                return [self._error(player_id, "invalid_declaration", "Declared value must be 0-10.")]
        elif declared_value is not None:
            return [
                self._error(
                    player_id, "invalid_declaration", "The declared value is locked for this round."
                )
            ]
        if len(card_ids) == len(player.hand) and player.doubts_made < self.settings.min_doubts:
            need = self.settings.min_doubts - player.doubts_made
            return [
                self._error(
                    player_id,
                    "quota_block",
                    f"You need {need} more doubts before you can play your last cards.",
                )
            ]

        # A valid play by the next player closes the previous doubt window;
        # if that resolves a pending win, the game ends and this play is void.
        events = self._close_window()
        if self.state == "finished":
            return events

        cards = [hand_by_id[cid] for cid in card_ids]
        played_ids = set(card_ids)
        player.hand = [c for c in player.hand if c.id not in played_ids]
        self.pile.extend(cards)
        if self.round_declared_value is None:
            self.round_declared_value = declared_value
        self.last_play = (player_id, cards)
        self.last_player_who_played = player_id
        self.passes_since_last_play = 0
        self.doubt_window_open = True
        if not player.hand:
            # Win is pending until the doubt window closes (see _close_window)
            self.pending_winner = player_id
        events.append(
            Event(
                "cards_played",
                {
                    "player_id": player_id,
                    "count": len(cards),
                    "declared_value": self.round_declared_value,
                    "pile_size": len(self.pile),
                },
            )
        )
        events.append(self._hand_event(player))
        self._advance_turn()
        events.append(self._turn_event())
        return events

    def pass_turn(self, player_id: str) -> list[Event]:
        err = self._validate_turn(player_id)
        if err is not None:
            return [err]
        if self.round_declared_value is None:
            return [
                self._error(player_id, "invalid_action", "You must start the round by playing cards.")
            ]
        events = self._close_window()
        if self.state == "finished":
            return events
        self.passes_since_last_play += 1
        events.append(Event("player_passed", {"player_id": player_id}))
        self._advance_turn()
        events.extend(self._maybe_burn())
        events.append(self._turn_event())
        return events

    def call_doubt(self, doubter_id: str) -> list[Event]:
        if self.state != "playing" or doubter_id not in self.turn_order:
            return []
        if not self.doubt_window_open or self.last_play is None:
            return []  # late or second doubts are rejected silently
        played_pid, played_cards = self.last_play
        if doubter_id == played_pid:
            return [self._error(doubter_id, "invalid_action", "You cannot doubt your own play.")]

        doubter = self._by_id[doubter_id]
        doubter.doubts_made += 1  # counts toward quota, win or lose
        self.doubt_window_open = False

        declared = self.round_declared_value
        was_lie = any(card.value != declared for card in played_cards)
        receiver_id = played_pid if was_lie else doubter_id
        receiver = self._by_id[receiver_id]
        receiver.hand.extend(self.pile)
        self.pile = []
        new_starter_id = doubter_id if was_lie else played_pid

        events = [
            Event(
                "doubt_resolved",
                {
                    "doubter_id": doubter_id,
                    "played_player_id": played_pid,
                    "was_lie": was_lie,
                    "revealed_cards": [c.to_dict() for c in played_cards],
                    "pile_goes_to": receiver_id,
                    "new_starter_id": new_starter_id,
                },
            ),
            self._hand_event(receiver),
        ]

        pending = self.pending_winner
        self.pending_winner = None
        self.last_play = None
        self.last_player_who_played = None
        self.passes_since_last_play = 0
        self.round_declared_value = None

        if pending == played_pid and not was_lie:
            # Truthful last play doubted: doubter took the pile, player wins
            events.extend(self._finish(played_pid, "empty_hand"))
            return events

        self.active_index = self.turn_order.index(new_starter_id)
        self.turn_number += 1
        events.append(self._turn_event())
        return events

    def close_doubt_window(self) -> list[Event]:
        """Called by the socket layer when the 5-second timer expires."""
        return self._close_window()

    def remove_player(self, player_id: str, reason: str = "disconnect_timeout") -> list[Event]:
        if self.state != "playing" or player_id not in self.turn_order:
            return []
        events = [Event("player_removed", {"player_id": player_id, "reason": reason})]
        player = self._by_id[player_id]
        player.hand = []  # discarded -- never shuffled into the pile
        if self.pending_winner == player_id:
            self.pending_winner = None
        if self.last_play is not None and self.last_play[0] == player_id:
            # A gone player's play can no longer be doubted; its cards stay
            # in the pile and leave the game via the pass-around burn.
            self.doubt_window_open = False
        was_active = self.turn_order[self.active_index] == player_id
        idx = self.turn_order.index(player_id)
        self.turn_order.remove(player_id)
        if idx < self.active_index:
            self.active_index -= 1
        if self.active_index >= len(self.turn_order):
            self.active_index = 0
        if len(self.turn_order) < 2:
            # Quota is waived on forfeit
            events.extend(self._finish(self.turn_order[0], "forfeit"))
            return events
        if was_active:
            self.turn_number += 1
            events.extend(self._maybe_burn())
            events.append(self._turn_event())
        return events

    # ------------------------------------------------------------- queries

    @property
    def active_player_id(self) -> str | None:
        if self.state != "playing" or not self.turn_order:
            return None
        return self.turn_order[self.active_index]

    def hand_of(self, player_id: str) -> list[Card]:
        return self._by_id[player_id].hand

    def public_state(self) -> dict[str, Any]:
        return {
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "card_count": len(p.hand),
                    "doubts_made": p.doubts_made,
                }
                for p in self.players
            ],
            "turn_order": list(self.turn_order),
            "active_player_id": self.active_player_id,
            "round_declared_value": self.round_declared_value,
            "pile_size": len(self.pile),
            "turn_number": self.turn_number,
            "doubt_window_open": self.doubt_window_open,
            "state": self.state,
            "winner_id": self.winner_id,
        }

    # ------------------------------------------------------------ internal

    def _validate_turn(self, player_id: str) -> Event | None:
        if self.state != "playing":
            return self._error(player_id, "invalid_action", "The game is over.")
        if player_id not in self.turn_order:
            return self._error(player_id, "invalid_action", "You are not in this game.")
        if player_id != self.active_player_id:
            return self._error(player_id, "out_of_turn", "It is not your turn.")
        return None

    def _advance_turn(self) -> None:
        self.active_index = (self.active_index + 1) % len(self.turn_order)
        self.turn_number += 1

    def _maybe_burn(self) -> list[Event]:
        """Burn the pile when a pass-around returns to the last player who played."""
        if not self.pile or self.last_player_who_played is None:
            return []
        returned_to_last = self.active_player_id == self.last_player_who_played
        last_gone = self.last_player_who_played not in self.turn_order
        full_cycle = last_gone and self.passes_since_last_play >= len(self.turn_order)
        if not (returned_to_last or full_cycle):
            return []
        burned = len(self.pile)
        self.pile = []
        self.round_declared_value = None
        self.last_play = None
        self.last_player_who_played = None
        self.passes_since_last_play = 0
        self.doubt_window_open = False
        return [Event("round_burned", {"new_starter_id": self.active_player_id, "burned_count": burned})]

    def _close_window(self) -> list[Event]:
        if not self.doubt_window_open:
            return []
        self.doubt_window_open = False
        pending = self.pending_winner
        self.pending_winner = None
        if pending is not None:
            # Undoubted hand-emptying play survives: the player wins
            return self._finish(pending, "empty_hand")
        return []

    def _finish(self, winner_id: str, reason: str) -> list[Event]:
        self.state = "finished"
        self.winner_id = winner_id
        return [
            Event(
                "game_over",
                {
                    "winner_id": winner_id,
                    "winner_name": self._by_id[winner_id].name,
                    "reason": reason,
                },
            )
        ]

    def _hand_event(self, player: Player) -> Event:
        return Event(
            "hand_updated",
            {"your_hand": [c.to_dict() for c in player.hand]},
            to=player.id,
        )

    def _turn_event(self) -> Event:
        return Event(
            "turn_changed",
            {
                "active_player_id": self.active_player_id,
                "round_declared_value": self.round_declared_value,
                "turn_number": self.turn_number,
            },
        )

    def _error(self, player_id: str, code: str, message: str) -> Event:
        return Event("error", {"code": code, "message": message}, to=player_id)
