from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from power_grid.interfaces import InterfacePlayerBoardBuyingResources
from power_grid.simple_types import (
    PhaseStatus,
    PlayerColor,
    RequestError,
    Resource,
)


class BuyingResources:
    def __init__(
        self,
        player_boards: Mapping[PlayerColor, InterfacePlayerBoardBuyingResources],
    ) -> None:
        if not player_boards:
            raise ValueError("player_boards cannot be empty")
        self._player_boards: dict[
            PlayerColor, InterfacePlayerBoardBuyingResources
        ] = dict(player_boards)
        self._remaining_players: list[PlayerColor] = []

    @property
    def is_active(self) -> bool:
        return len(self._remaining_players) > 0

    @property
    def current_player(self) -> PlayerColor | None:
        return self._remaining_players[0] if self._remaining_players else None

    @property
    def remaining_players(self) -> list[PlayerColor]:
        return list(self._remaining_players)

    def start_phase(self, player_order: Sequence[PlayerColor]) -> None:
        ordered_players = list(player_order)
        if not ordered_players:
            raise ValueError("Player order must not be empty")
        unique_players = set(ordered_players)
        if len(unique_players) != len(ordered_players):
            raise ValueError("Player order must not contain duplicates")
        if unique_players != set(self._player_boards):
            raise ValueError("Player order does not match registered players")
        self._remaining_players = list(reversed(ordered_players))

    def buy_resources(
        self,
        player: PlayerColor,
        resources: Sequence[Resource],
    ) -> PhaseStatus | RequestError:
        if not self._remaining_players:
            return RequestError("Buying resources phase is not active")

        active_player = self._remaining_players[0]
        if player != active_player:
            return RequestError(
                f"Expected {active_player.name} to buy resources, "
                f"not {player.name}"
            )

        if resources:
            error = self._player_boards[player].buy_resources(list(resources))
            if error is not None:
                return error

        self._remaining_players.pop(0)
        if self._remaining_players:
            return PhaseStatus.PHASE_CONTINUES
        return PhaseStatus.PHASE_ENDS

    def get_state(self) -> str:
        active = self.current_player
        payload: dict[str, object] = {
            "is_active": self.is_active,
            "current_player": active.name if active is not None else None,
            "remaining_players": [
                color.name for color in self._remaining_players
            ],
        }
        return json.dumps(payload)
