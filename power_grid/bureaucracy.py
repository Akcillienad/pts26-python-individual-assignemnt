from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from power_grid.interfaces import (
    InterfacePlayerBoardBureaucracy,
    InterfacePowerPlantMarketBureaucracy,
    InterfaceResourceMarketBureaucracy,
)
from power_grid.power_plant import PowerPlantNumber
from power_grid.simple_types import (
    PhaseStatus,
    PlayerColor,
    RequestError,
    Resource,
)


class Bureaucracy:
    def __init__(
        self,
        player_boards: Mapping[PlayerColor, InterfacePlayerBoardBureaucracy],
        resource_market: InterfaceResourceMarketBureaucracy,
        power_plant_market: InterfacePowerPlantMarketBureaucracy,
    ) -> None:
        if not player_boards:
            raise ValueError("player_boards cannot be empty")
        self._player_boards: dict[
            PlayerColor, InterfacePlayerBoardBureaucracy
        ] = dict(player_boards)
        self._resource_market = resource_market
        self._power_plant_market = power_plant_market
        self._turn_queue: list[PlayerColor] = []

    @property
    def is_active(self) -> bool:
        return bool(self._turn_queue)

    @property
    def current_player(self) -> PlayerColor | None:
        return self._turn_queue[0] if self._turn_queue else None

    @property
    def remaining_players(self) -> list[PlayerColor]:
        return list(self._turn_queue)

    def start_phase(self, player_order: Sequence[PlayerColor]) -> None:
        if len(player_order) != len(self._player_boards) or (
            set(player_order) != set(self._player_boards)
        ):
            raise ValueError(
                "player_order must be a permutation of the registered players"
            )
        self._turn_queue = list(player_order)

    def use_power_plants(
        self,
        player: PlayerColor,
        ppns: Sequence[PowerPlantNumber],
        resources_to_burn: Sequence[Resource],
    ) -> PhaseStatus | RequestError:
        if not self._turn_queue:
            return RequestError("Bureaucracy phase is not active")

        turn_player = self._turn_queue[0]
        if player != turn_player:
            return RequestError(
                f"Expected {turn_player.name} to operate power plants, "
                f"not {player.name}"
            )

        error = self._player_boards[player].use_power_plants(
            list(ppns), list(resources_to_burn)
        )
        if error is not None:
            return error

        self._turn_queue.pop(0)
        if self._turn_queue:
            return PhaseStatus.PHASE_CONTINUES

        self._resource_market.refill()
        self._power_plant_market.prepare_next_turn()
        return PhaseStatus.PHASE_ENDS

    def get_state(self) -> str:
        current_turn = self.current_player
        snapshot: dict[str, object] = {
            "is_active": self.is_active,
            "current_player": (
                current_turn.name if current_turn is not None else None
            ),
            "remaining_players": [
                player.name for player in self._turn_queue
            ],
        }
        return json.dumps(snapshot)
