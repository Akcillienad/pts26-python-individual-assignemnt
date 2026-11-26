from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from power_grid.interfaces import (
    InterfacePlayerBoardBuildingHouses,
    InterfacePowerPlantMarketBuildingHouses,
    InterfaceTownsBuildingHouses,
)
from power_grid.simple_types import PhaseStatus, PlayerColor, RequestError


class BuildingHouses:
    END_GAME_CITY_THRESHOLDS: dict[int, int] = {
        2: 21,
        3: 17,
        4: 17,
        5: 15,
        6: 14,
    }

    def __init__(
        self,
        towns: InterfaceTownsBuildingHouses,
        power_plant_market: InterfacePowerPlantMarketBuildingHouses,
        player_boards: Mapping[PlayerColor, InterfacePlayerBoardBuildingHouses],
        end_game_town_count: int | None = None,
    ) -> None:
        if not player_boards:
            raise ValueError("player_boards cannot be empty")

        if end_game_town_count is None:
            player_count = len(player_boards)
            if player_count not in self.END_GAME_CITY_THRESHOLDS:
                raise ValueError(
                    f"Unsupported player count: {player_count}. "
                    "Expected 2 to 6 players or an explicit end_game_town_count."
                )
            resolved_threshold = self.END_GAME_CITY_THRESHOLDS[player_count]
        else:
            if end_game_town_count < 1:
                raise ValueError("end_game_town_count must be at least 1")
            resolved_threshold = end_game_town_count

        self._towns = towns
        self._power_plant_market = power_plant_market
        self._player_boards: dict[PlayerColor, InterfacePlayerBoardBuildingHouses] = (
            dict(player_boards)
        )
        self._end_game_town_count = resolved_threshold
        self._remaining_players: list[PlayerColor] = []

    @property
    def is_active(self) -> bool:
        return bool(self._remaining_players)

    @property
    def current_player(self) -> PlayerColor | None:
        if not self._remaining_players:
            return None
        return self._remaining_players[0]

    @property
    def remaining_players(self) -> list[PlayerColor]:
        return list(self._remaining_players)

    @property
    def end_game_town_count(self) -> int:
        return self._end_game_town_count

    def start_phase(self, player_order: Sequence[PlayerColor]) -> None:
        if not player_order:
            raise ValueError("player_order cannot be empty")
        if len(set(player_order)) != len(player_order):
            raise ValueError("player_order cannot contain duplicate players")
        if set(player_order) != set(self._player_boards):
            raise ValueError(
                "player_order must contain exactly the registered players"
            )

        self._remaining_players = list(reversed(player_order))

    def buy_houses(
        self,
        player: PlayerColor,
        town_names: Sequence[str],
    ) -> PhaseStatus | RequestError:
        if not self._remaining_players:
            return RequestError("Building houses phase is not active")

        expected_player = self._remaining_players[0]
        if player != expected_player:
            return RequestError(
                f"It is {expected_player.name}'s turn, not {player.name}'s turn"
            )

        if town_names:
            player_board = self._player_boards[player]
            max_money = player_board.outstanding_money()
            result = self._towns.buy_houses(player, list(town_names), max_money)
            if isinstance(result, RequestError):
                return result
            if result < 0:
                raise ValueError("Towns.buy_houses returned a negative cost")
            if result > 0:
                player_board.spend_money(result)

            max_houses = self._towns.get_max_number_of_houses()
            self._power_plant_market.remove_power_plants_cheaper_than(max_houses)

        self._remaining_players.pop(0)
        if self._remaining_players:
            return PhaseStatus.PHASE_CONTINUES

        if self._towns.get_max_number_of_houses() >= self._end_game_town_count:
            return PhaseStatus.GAME_ENDS
        return PhaseStatus.PHASE_ENDS

    def get_state(self) -> str:
        current = self.current_player
        state: dict[str, object] = {
            "is_active": self.is_active,
            "current_player": current.name if current is not None else None,
            "remaining_players": [
                player.name for player in self._remaining_players
            ],
            "end_game_town_count": self._end_game_town_count,
        }
        return json.dumps(state)
