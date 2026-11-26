from collections.abc import Sequence
from dataclasses import dataclass

from power_grid.power_plant import PowerPlantNumber
from power_grid.simple_types import PlayerColor


@dataclass(frozen=True)
class PlayerOrderData:
    color: PlayerColor
    connected_cities: int
    largest_power_plant: PowerPlantNumber
    powered_cities: int
    remaining_money: int

    def __post_init__(self) -> None:
        if self.connected_cities < 0:
            raise ValueError("connected_cities cannot be negative")
        if self.powered_cities < 0:
            raise ValueError("powered_cities cannot be negative")
        if self.remaining_money < 0:
            raise ValueError("remaining_money cannot be negative")
        if self.largest_power_plant.number < 0:
            raise ValueError("power plant number cannot be negative")


class DeterminePlayerOrder:

    def __init__(self, players: Sequence[PlayerOrderData]) -> None:
        if len({player.color for player in players}) != len(players):
            raise ValueError("player colors must be unique")
        self._players = list(players)

    def reorder(self) -> list[PlayerColor]:
        ordered = sorted(
            self._players,
            key=lambda player: (
                player.connected_cities,
                player.largest_power_plant.number,
            ),
            reverse=True,
        )
        return [player.color for player in ordered]

    def game_result(self) -> list[PlayerColor]:
        ranked = sorted(
            self._players,
            key=lambda player: (
                player.powered_cities,
                player.remaining_money,
                player.connected_cities,
            ),
            reverse=True,
        )
        return [player.color for player in ranked]
