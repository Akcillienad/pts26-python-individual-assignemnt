from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence

from power_grid.connections import Connections
from power_grid.interfaces import (
    InterfacePlayerBoardBuildingHouses,
    InterfacePowerPlantMarketBuildingHouses,
    InterfaceTownsBuildingHouses,
)
from power_grid.maximum_number_of_usable_power_plants import (
    MaximumNumberOfUsablePowerPlants,
)
from power_grid.power_plant import PowerPlant, PowerPlantNumber
from power_grid.simple_types import (
    PhaseStatus,
    PlayerColor,
    RequestError,
    Resource,
)
from power_grid.store_resources import StoreResources
from power_grid.use_power_plants import UsePowerPlants


class FakePlayerPowerPlants:
    def __init__(
        self,
        plants: Sequence[PowerPlant] = (),
        max_plants: int = 3,
    ) -> None:
        self._plants: list[PowerPlant] = list(plants)
        self._max_plants = max_plants
        self._store = StoreResources()
        self._use = UsePowerPlants()
        self._max_usable = MaximumNumberOfUsablePowerPlants()
        self.calls: list[str] = []

    @property
    def power_plants(self) -> list[PowerPlant]:
        return list(self._plants)

    def best_power_plant(self) -> PowerPlantNumber:
        if not self._plants:
            return PowerPlantNumber(0)
        return PowerPlantNumber(
            max(plant.number.number for plant in self._plants)
        )

    def receive_power_plant(self, power_plant: PowerPlant) -> bool:
        self.calls.append(f"receive:{power_plant.number.number}")
        if any(
            owned.number.number == power_plant.number.number
            for owned in self._plants
        ):
            raise ValueError("Duplicate power plant")
        self._plants.append(power_plant)
        return len(self._plants) <= self._max_plants

    def remove_power_plant(
        self,
        ppn: PowerPlantNumber,
        new_resources: Sequence[Resource],
    ) -> RequestError | None:
        self.calls.append(f"remove:{ppn.number}")
        remaining = [
            plant
            for plant in self._plants
            if plant.number.number != ppn.number
        ]
        if len(remaining) == len(self._plants):
            return RequestError("Power plant not owned")
        if not self._store.can_store_resources(list(new_resources), remaining):
            return RequestError("Remaining resources do not fit")
        self._plants = remaining
        return None

    def number_of_connectable_cities(
        self,
        resources: Sequence[Resource],
    ) -> int:
        return self._max_usable.number_of_suppliable_towns(
            list(resources), list(self._plants)
        )

    def can_store_resources(self, resources: Sequence[Resource]) -> bool:
        return self._store.can_store_resources(
            list(resources), list(self._plants)
        )

    def use_power_plant(
        self,
        ppns: Sequence[PowerPlantNumber],
        resources_to_burn: Sequence[Resource],
    ) -> int | RequestError:
        self.calls.append("use")
        numbers = [ppn.number for ppn in ppns]
        if len(numbers) != len(set(numbers)):
            return RequestError("Duplicate power plant in use request")
        chosen: list[PowerPlant] = []
        for num in numbers:
            matched = [
                plant for plant in self._plants if plant.number.number == num
            ]
            if not matched:
                return RequestError(f"Power plant {num} not owned")
            chosen.append(matched[0])
        return self._use.number_of_suppliable_towns(
            list(resources_to_burn), chosen
        )


class FakePowerPlantMarket(InterfacePowerPlantMarketBuildingHouses):
    def __init__(self) -> None:
        self.removed_thresholds: list[int] = []
        self.prepare_calls = 0
        self.step3_ready = False
        self.step_events: list[str] = []

    def remove_power_plants_cheaper_than(self, value: int) -> None:
        self.removed_thresholds.append(value)

    def prepare_next_turn(self) -> None:
        self.prepare_calls += 1

    def is_step3_start(self) -> bool:
        return self.step3_ready

    def start_step2(self) -> None:
        self.step_events.append("step2")

    def start_step3(self) -> None:
        self.step_events.append("step3")
        self.step3_ready = False

    def to_string(self) -> str:
        return json.dumps(
            {
                "step3_ready": self.step3_ready,
                "removed_thresholds": list(self.removed_thresholds),
                "prepare_calls": self.prepare_calls,
                "step_events": list(self.step_events),
            }
        )


class FakeTowns(InterfaceTownsBuildingHouses):
    def __init__(
        self,
        connections: Connections | None = None,
        house_cost: int = 10,
    ) -> None:
        self._connections = connections
        self._house_cost = house_cost
        self._houses: dict[PlayerColor, list[str]] = {}
        self.step = 1
        self.step_events: list[str] = []
        self.next_error: RequestError | None = None

    def set_house_count(self, player: PlayerColor, count: int) -> None:
        self._houses[player] = [
            f"{player.name}_{idx}" for idx in range(count)
        ]

    def buy_houses(
        self, player: PlayerColor, town_names: Sequence[str], max_money: int
    ) -> int | RequestError:
        if self.next_error is not None:
            err = self.next_error
            self.next_error = None
            return err
        targets = list(town_names)
        owned = self._houses.get(player, [])
        if any(town in owned for town in targets) or (
            len(set(targets)) != len(targets)
        ):
            return RequestError("Duplicate or already owned town")
        conn_cost = (
            self._connections.calculate_connecting_cost(owned, targets)
            if self._connections is not None
            else 0
        )
        total_cost = conn_cost + len(targets) * self._house_cost
        if total_cost > max_money:
            return RequestError("Not enough money to buy houses")
        self._houses[player] = owned + targets
        return total_cost

    def get_number_of_houses(self, player: PlayerColor) -> int:
        return len(self._houses.get(player, ()))

    def get_max_number_of_houses(self) -> int:
        if not self._houses:
            return 0
        return max(len(towns) for towns in self._houses.values())

    def start_step2(self) -> None:
        self.step = 2
        self.step_events.append("step2")

    def start_step3(self) -> None:
        self.step = 3
        self.step_events.append("step3")

    def to_string(self) -> str:
        return json.dumps(
            {
                "step": self.step,
                "houses": {
                    player.name: list(towns)
                    for player, towns in self._houses.items()
                },
            }
        )


class FakeResourcePool:
    def __init__(self) -> None:
        self.returned: list[list[Resource]] = []

    def put_resources(self, resources: list[Resource]) -> None:
        self.returned.append(list(resources))


class FakeResourceMarket:
    def __init__(
        self,
        unit_prices: Mapping[Resource, int] | None = None,
        unavailable: set[Resource] | None = None,
    ) -> None:
        self._unit_prices: dict[Resource, int] = dict(unit_prices or {})
        self._unavailable: set[Resource] = set(unavailable or ())
        self.taken: list[list[Resource]] = []
        self.refill_calls = 0
        self.raw_state = json.dumps({"market": "ok"})

    def get_price(self, desired: list[Resource]) -> int | None:
        if any(res in self._unavailable for res in desired):
            return None
        return sum(self._unit_prices.get(res, 1) for res in desired)

    def take_resources(self, resources: list[Resource]) -> None:
        self.taken.append(list(resources))

    def refill(self) -> None:
        self.refill_calls += 1

    def to_string(self) -> str:
        return self.raw_state


class FakeAuctionPhase:
    def __init__(
        self,
        state_str: str = '{"phase": "auction"}',
        on_start: Callable[[Sequence[PlayerColor]], None] | None = None,
    ) -> None:
        self.started_orders: list[list[PlayerColor]] = []
        self.calls: list[tuple[str, object]] = []
        self.next_result: PhaseStatus | RequestError = (
            PhaseStatus.PHASE_CONTINUES
        )
        self.state_str = state_str
        self._on_start = on_start

    def start_phase(self, player_order: Sequence[PlayerColor]) -> None:
        self.started_orders.append(list(player_order))
        if self._on_start is not None:
            self._on_start(player_order)

    def select_power_plant_to_bid(
        self, player: PlayerColor, ppn: PowerPlantNumber, first_bid: int
    ) -> PhaseStatus | RequestError:
        self.calls.append(("select", (player, ppn.number, first_bid)))
        return self.next_result

    def do_not_want_power_plant(
        self,
        player: PlayerColor,
    ) -> PhaseStatus | RequestError:
        self.calls.append(("pass_select", player))
        return self.next_result

    def bid_for_current_power_plant(
        self,
        player: PlayerColor,
        bid: int,
    ) -> PhaseStatus | RequestError:
        self.calls.append(("bid", (player, bid)))
        return self.next_result

    def do_not_bid_for_current_power_plant(
        self,
        player: PlayerColor,
    ) -> PhaseStatus | RequestError:
        self.calls.append(("pass_bid", player))
        return self.next_result

    def remove_power_plant(
        self, player: PlayerColor, ppn: PowerPlantNumber,
        resources: Sequence[Resource],
    ) -> PhaseStatus | RequestError:
        self.calls.append(("remove", (player, ppn.number, list(resources))))
        return self.next_result

    def get_state(self) -> str:
        return self.state_str


class SimplePlayerBoardFake(InterfacePlayerBoardBuildingHouses):
    def __init__(
        self,
        color: PlayerColor,
        money: int = 50,
        best_plant: int = 0,
        connectable: int = 0,
    ) -> None:
        self.color = color
        self.money = money
        self.best_plant = best_plant
        self.connectable = connectable
        self.next_error: RequestError | None = None
        self.history: list[tuple[str, object]] = []
        self.raw_state: str | None = None

    def best_power_plant_number(self) -> PowerPlantNumber:
        return PowerPlantNumber(self.best_plant)

    def outstanding_money(self) -> int:
        return self.money

    def spend_money(self, amount: int) -> None:
        self.money -= amount

    def number_of_connectable_cities(self) -> int:
        return self.connectable

    def buy_resources(
        self,
        resources: Sequence[Resource],
    ) -> RequestError | None:
        if self.next_error is not None:
            return self.next_error
        self.history.append(("buy", list(resources)))
        return None

    def use_power_plants(
        self,
        ppns: Sequence[PowerPlantNumber],
        resources_to_burn: Sequence[Resource],
    ) -> RequestError | None:
        if self.next_error is not None:
            return self.next_error
        self.history.append(
            ("use", ([ppn.number for ppn in ppns], list(resources_to_burn)))
        )
        return None

    def state(self) -> str:
        if self.raw_state is not None:
            return self.raw_state
        return json.dumps({"color": self.color.name, "money": self.money})
