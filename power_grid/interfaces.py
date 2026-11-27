# pylint: disable=unused-argument, duplicate-code
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from power_grid.power_plant import PowerPlant, PowerPlantNumber
from power_grid.simple_types import (
    PhaseStatus,
    PlayerColor,
    RequestError,
    Resource,
    SerializedGameState,
)


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


class PowerGridRulesGameInterface:
    def select_power_plant_to_bid(
        self, player_id: int, power_plant_number: int, first_bid: int
    ) -> SerializedGameState | RequestError:
        assert False

    def do_not_want_power_plant(
        self, player_id: int
    ) -> SerializedGameState | RequestError:
        assert False

    def bid_for_current_power_plant(
        self, player_id: int, bid: int
    ) -> SerializedGameState | RequestError:
        assert False

    def do_not_bid_for_current_power_plant(
        self, player_id: int
    ) -> SerializedGameState | RequestError:
        assert False

    def remove_power_plant(
        self, player_id: int, power_plant_number: int, removed_resources: str
    ) -> SerializedGameState | RequestError:
        assert False

    def buy_resources(
        self, player_id: int, resources: str
    ) -> SerializedGameState | RequestError:
        assert False

    def buy_houses(
        self, player_id: int, town_names: Sequence[str]
    ) -> SerializedGameState | RequestError:
        assert False

    def use_power_plants(
        self, player_id: int, power_plant_numbers: Sequence[int],
        resources_to_burn: str,
    ) -> SerializedGameState | RequestError:
        assert False


class InterfaceResourceMarketPlayerBoard(Protocol):
    def get_price(self, desired: list[Resource]) -> int | None:
        ...

    def take_resources(self, resources: list[Resource]) -> None:
        ...


class InterfaceResourcePoolPlayerBoard(Protocol):
    def put_resources(self, resources: list[Resource]) -> None:
        ...


class InterfaceTownsPlayerBoard(Protocol):
    def get_number_of_houses(self, player: PlayerColor) -> int:
        ...


class InterfacePlayerPowerPlantsPlayerBoard(Protocol):
    @property
    def power_plants(self) -> Sequence[PowerPlant]:
        ...

    def best_power_plant(self) -> PowerPlantNumber:
        ...

    def receive_power_plant(self, power_plant: PowerPlant) -> bool:
        ...

    def remove_power_plant(
        self, ppn: PowerPlantNumber, new_resources: list[Resource]
    ) -> RequestError | None:
        ...

    def number_of_connectable_cities(
        self, resources: list[Resource]
    ) -> int:
        ...

    def can_store_resources(self, resources: list[Resource]) -> bool:
        ...

    def use_power_plant(
        self,
        ppns: list[PowerPlantNumber],
        resources_to_burn: list[Resource],
    ) -> int | RequestError:
        ...


class InterfacePlayerBoardBuyingResources(Protocol):
    def buy_resources(self, resources: Sequence[Resource]) -> RequestError | None:
        ...


class InterfacePlayerBoardBureaucracy(Protocol):
    def use_power_plants(
        self,
        ppns: Sequence[PowerPlantNumber],
        resources_to_burn: Sequence[Resource],
    ) -> RequestError | None:
        ...


class InterfaceResourceMarketBureaucracy(Protocol):
    def refill(self) -> None:
        ...


class InterfacePowerPlantMarketBureaucracy(Protocol):
    def prepare_next_turn(self) -> None:
        ...


class InterfacePowerPlantMarketAuction(Protocol):
    def can_take_power_plant(
        self, ppn: PowerPlantNumber, price: int
    ) -> RequestError | None:
        ...

    def take_power_plant(self, ppn: PowerPlantNumber) -> PowerPlant:
        ...

    def remove_discounted_power_plant(self) -> None:
        ...


class InterfacePlayerBoardAuction(Protocol):
    def has_enough_money(self, amount: int) -> bool:
        ...

    def receive_power_plant(self, power_plant: PowerPlant, price: int) -> bool:
        ...

    def remove_power_plant(
        self, ppn: PowerPlantNumber, removed_resources: Sequence[Resource]
    ) -> RequestError | None:
        ...


class InterfaceAuctionPowerPlantsGameController(Protocol):
    def start_phase(self, player_order: list[PlayerColor]) -> None:
        ...

    def select_power_plant_to_bid(
        self, player: PlayerColor, ppn: PowerPlantNumber, first_bid: int
    ) -> PhaseStatus | RequestError:
        ...

    def do_not_want_power_plant(
        self, player: PlayerColor
    ) -> PhaseStatus | RequestError:
        ...

    def bid_for_current_power_plant(
        self, player: PlayerColor, bid: int
    ) -> PhaseStatus | RequestError:
        ...

    def do_not_bid_for_current_power_plant(
        self, player: PlayerColor
    ) -> PhaseStatus | RequestError:
        ...

    def remove_power_plant(
        self,
        player: PlayerColor,
        ppn: PowerPlantNumber,
        resources: list[Resource],
    ) -> PhaseStatus | RequestError:
        ...

    def get_state(self) -> str:
        ...


class InterfaceBuyingResourcesGameController(Protocol):
    def start_phase(self, player_order: Sequence[PlayerColor]) -> None:
        ...

    def buy_resources(
        self, player: PlayerColor, resources: Sequence[Resource]
    ) -> PhaseStatus | RequestError:
        ...

    def get_state(self) -> str:
        ...


class InterfaceBuildingHousesGameController(Protocol):
    def start_phase(self, player_order: Sequence[PlayerColor]) -> None:
        ...

    def buy_houses(
        self, player: PlayerColor, town_names: Sequence[str]
    ) -> PhaseStatus | RequestError:
        ...

    def get_state(self) -> str:
        ...


class InterfaceBureaucracyGameController(Protocol):
    def start_phase(self, player_order: Sequence[PlayerColor]) -> None:
        ...

    def use_power_plants(
        self, player: PlayerColor, ppns: Sequence[PowerPlantNumber],
        resources_to_burn: Sequence[Resource],
    ) -> PhaseStatus | RequestError:
        ...

    def get_state(self) -> str:
        ...


class InterfaceCheckAndBumpStepGameController(Protocol):
    def get_step(self) -> int:
        ...

    def check_and_bump_to_step2(
        self, connected_city_counts: Sequence[int]
    ) -> bool:
        ...

    def check_and_bump_to_step3(self, step_3_card_drawn: bool) -> bool:
        ...


class InterfacePowerPlantMarketGameController(Protocol):
    def is_step3_start(self) -> bool:
        ...


class InterfaceResourceMarketGameController(Protocol):
    def to_string(self) -> str:
        ...


class InterfaceTownsGameController(Protocol):
    def get_number_of_houses(self, player: PlayerColor) -> int:
        ...


class InterfacePlayerBoardGameController(Protocol):
    def best_power_plant_number(self) -> PowerPlantNumber:
        ...

    def outstanding_money(self) -> int:
        ...

    def number_of_connectable_cities(self) -> int:
        ...

    def state(self) -> str:
        ...


class InterfaceGameControllerAdapter(Protocol):
    def select_power_plant_to_bid(
        self, player: PlayerColor, ppn: PowerPlantNumber, first_bid: int
    ) -> RequestError | None:
        ...

    def do_not_want_power_plant(
        self, player: PlayerColor
    ) -> RequestError | None:
        ...

    def bid_for_current_power_plant(
        self, player: PlayerColor, bid: int
    ) -> RequestError | None:
        ...

    def do_not_bid_for_current_power_plant(
        self, player: PlayerColor
    ) -> RequestError | None:
        ...

    def remove_power_plant(
        self, player: PlayerColor, ppn: PowerPlantNumber,
        removed_resources: Sequence[Resource],
    ) -> RequestError | None:
        ...

    def buy_resources(
        self, player: PlayerColor, resources: Sequence[Resource]
    ) -> RequestError | None:
        ...

    def buy_houses(
        self, player: PlayerColor, town_names: Sequence[str]
    ) -> RequestError | None:
        ...

    def use_power_plants(
        self, player: PlayerColor, ppns: Sequence[PowerPlantNumber],
        resources_to_burn: Sequence[Resource],
    ) -> RequestError | None:
        ...

    def get_state(self) -> str:
        ...
