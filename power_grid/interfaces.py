# pylint: disable=unused-argument, duplicate-code
from __future__ import annotations
from typing import Sequence
from power_grid.simple_types import PlayerColor, RequestError, Resource


class InterfaceResourcePoolResourceMarket:
    def can_take_resources_from_storage_space(self, resources: Sequence[Resource]) -> bool:
        assert False

    def get_from_storage_space(self, resources: Sequence[Resource]) -> None:
        assert False

    def take_resources(self, resources: Sequence[Resource]) -> list[Resource]:
        assert False

    def to_string(self) -> str:
        assert False


class InterfaceTownsBuildingHouses:
    def buy_houses(
        self,
        player: PlayerColor,
        town_names: Sequence[str],
        max_money: int,
    ) -> int | RequestError:
        assert False

    def get_max_number_of_houses(self) -> int:
        assert False


class InterfacePowerPlantMarketBuildingHouses:
    def remove_power_plants_cheaper_than(self, value: int) -> None:
        assert False


class InterfacePlayerBoardBuildingHouses:
    def outstanding_money(self) -> int:
        assert False

    def spend_money(self, amount: int) -> None:
        assert False
