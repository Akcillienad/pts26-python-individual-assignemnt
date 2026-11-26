from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from power_grid.interfaces import (
    InterfacePlayerBoardBuildingHouses,
    InterfacePlayerPowerPlantsPlayerBoard,
    InterfaceResourceMarketPlayerBoard,
    InterfaceResourcePoolPlayerBoard,
    InterfaceTownsPlayerBoard,
)
from power_grid.player_money import PlayerMoney
from power_grid.power_plant import PowerPlant, PowerPlantNumber
from power_grid.simple_types import PlayerColor, RequestError, Resource


@dataclass(frozen=True)
class PlayerBoardContext:
    resource_market: InterfaceResourceMarketPlayerBoard
    resource_pool: InterfaceResourcePoolPlayerBoard
    towns: InterfaceTownsPlayerBoard | None = None


class PlayerBoardFacade(InterfacePlayerBoardBuildingHouses):
    PAYMENT_TABLE: tuple[int, ...] = (
        10, 22, 33, 44, 54, 64, 73, 82, 90, 98,
        105, 112, 118, 124, 129, 134, 138, 142, 145, 148, 150,
    )

    def __init__(
        self,
        player_money: PlayerMoney,
        player_power_plants: InterfacePlayerPowerPlantsPlayerBoard,
        context: PlayerBoardContext,
        initial_resources: Sequence[Resource] = (),
    ) -> None:
        resources = list(initial_resources)
        if resources and not player_power_plants.can_store_resources(
            list(resources)
        ):
            raise ValueError(
                "initial_resources cannot be stored on player_power_plants"
            )

        self._player_money = player_money
        self._player_power_plants = player_power_plants
        self._context = context
        self._resources: list[Resource] = resources

    @property
    def color(self) -> PlayerColor:
        return self._player_money.color

    @property
    def resources(self) -> list[Resource]:
        return list(self._resources)

    @property
    def power_plants(self) -> list[PowerPlant]:
        return list(self._player_power_plants.power_plants)

    def best_power_plant_number(self) -> PowerPlantNumber:
        return self._player_power_plants.best_power_plant()

    def outstanding_money(self) -> int:
        return self._player_money.current_money

    def has_enough_money(self, amount: int) -> bool:
        return self._player_money.has_enough_money(amount)

    def spend_money(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("amount cannot be negative")
        if not self._player_money.has_enough_money(amount):
            raise ValueError("Player does not have enough money")
        self._player_money.spend_money(amount)

    def number_of_connectable_cities(self) -> int:
        return self._player_power_plants.number_of_connectable_cities(
            list(self._resources)
        )

    def receive_power_plant(self, power_plant: PowerPlant, price: int) -> bool:
        if price < 0:
            raise ValueError("price cannot be negative")
        if not self._player_money.has_enough_money(price):
            raise ValueError("Player does not have enough money for power plant")
        within_limit = self._player_power_plants.receive_power_plant(
            power_plant
        )
        self._player_money.spend_money(price)
        return within_limit

    def remove_power_plant(
        self,
        ppn: PowerPlantNumber,
        removed_resources: Sequence[Resource],
    ) -> RequestError | None:
        removed_list = list(removed_resources)
        remaining = self._take_from_owned_resources(removed_list)
        if remaining is None:
            return RequestError("Player does not own the specified resources")

        error = self._player_power_plants.remove_power_plant(
            ppn, list(remaining)
        )
        if error is not None:
            return error

        self._resources = remaining
        if removed_list:
            self._context.resource_pool.put_resources(list(removed_list))
        return None

    def buy_resources(
        self,
        resources: Sequence[Resource],
    ) -> RequestError | None:
        desired = list(resources)
        if not desired:
            return None

        if not self._player_power_plants.can_store_resources(
            self._resources + list(desired)
        ):
            return RequestError("Not enough storage space on power plants")

        price = self._context.resource_market.get_price(list(desired))
        if price is None:
            return RequestError(
                "Resource market cannot supply requested resources"
            )

        if not self._player_money.has_enough_money(price):
            return RequestError("Player does not have enough money")

        self._context.resource_market.take_resources(list(desired))
        self._player_money.spend_money(price)
        self._resources.extend(list(desired))
        return None

    def use_power_plants(
        self,
        ppns: Sequence[PowerPlantNumber],
        resources_to_burn: Sequence[Resource],
    ) -> RequestError | None:
        burn_list = list(resources_to_burn)
        remaining = self._take_from_owned_resources(burn_list)
        if remaining is None:
            return RequestError("Player does not own the resources to burn")

        result = self._player_power_plants.use_power_plant(
            list(ppns), list(burn_list)
        )
        if isinstance(result, RequestError):
            return result

        supplied_cities = max(0, result)
        if self._context.towns is not None:
            owned_houses = max(
                0, self._context.towns.get_number_of_houses(self.color)
            )
            supplied_cities = min(supplied_cities, owned_houses)

        self._resources = remaining
        if burn_list:
            self._context.resource_pool.put_resources(list(burn_list))

        payout_index = min(supplied_cities, len(self.PAYMENT_TABLE) - 1)
        self._player_money.receive_money(self.PAYMENT_TABLE[payout_index])
        return None

    def state(self) -> str:
        board_state: dict[str, object] = {
            "color": self.color.name,
            "money": self.outstanding_money(),
            "power_plants": [
                plant.number.number for plant in self.power_plants
            ],
            "resources": [resource.name for resource in self._resources],
        }
        return json.dumps(board_state)

    def _take_from_owned_resources(
        self,
        to_remove: Sequence[Resource],
    ) -> list[Resource] | None:
        remaining = list(self._resources)
        for resource in to_remove:
            if resource not in remaining:
                return None
            remaining.remove(resource)
        return remaining


PAYMENT_TABLE: tuple[int, ...] = PlayerBoardFacade.PAYMENT_TABLE
