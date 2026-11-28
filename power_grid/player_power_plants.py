from __future__ import annotations

from collections.abc import Sequence

from power_grid.maximum_number_of_usable_power_plants import (
    MaximumNumberOfUsablePowerPlants,
)
from power_grid.power_plant import PowerPlant, PowerPlantNumber
from power_grid.simple_types import RequestError, Resource
from power_grid.store_resources import StoreResources
from power_grid.use_power_plants import UsePowerPlants


class PlayerPowerPlants:
    """Manages a player's owned power plants, capacity, and fuel usage."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        power_plants: Sequence[PowerPlant] = (),
        *,
        max_plants: int = 3,
        store_resources: StoreResources | None = None,
        use_power_plants: UsePowerPlants | None = None,
        max_usable: MaximumNumberOfUsablePowerPlants | None = None,
    ) -> None:
        if (
            isinstance(max_plants, bool)
            or not isinstance(max_plants, int)
            or max_plants < 1
        ):
            raise ValueError("max_plants must be a positive integer")

        initial_plants = list(power_plants)
        if len(initial_plants) > max_plants:
            raise ValueError(
                f"Cannot initialize with {len(initial_plants)} plants; "
                f"max_plants is {max_plants}"
            )

        seen_numbers: set[int] = set()
        for plant in initial_plants:
            num = plant.number.number
            if not self._is_valid_positive_int(num):
                raise ValueError(f"Invalid power plant number: {num}")
            if num in seen_numbers:
                raise ValueError(f"Duplicate power plant number: {num}")
            seen_numbers.add(num)

        self._plants: list[PowerPlant] = initial_plants
        self._max_plants = max_plants
        self._store = (
            store_resources if store_resources is not None else StoreResources()
        )
        self._use = (
            use_power_plants
            if use_power_plants is not None
            else UsePowerPlants()
        )
        self._max_usable = (
            max_usable
            if max_usable is not None
            else MaximumNumberOfUsablePowerPlants()
        )

    @property
    def power_plants(self) -> list[PowerPlant]:
        return list(self._plants)

    @property
    def max_plants(self) -> int:
        return self._max_plants

    def best_power_plant(self) -> PowerPlantNumber:
        if not self._plants:
            return PowerPlantNumber(0)
        return PowerPlantNumber(
            max(plant.number.number for plant in self._plants)
        )

    def receive_power_plant(self, power_plant: PowerPlant) -> bool:
        num = power_plant.number.number
        if not self._is_valid_positive_int(num):
            raise ValueError(f"Invalid power plant number: {num}")
        if any(plant.number.number == num for plant in self._plants):
            raise ValueError(f"Player already owns power plant {num}")
        self._plants.append(power_plant)
        return len(self._plants) <= self._max_plants

    def remove_power_plant(
        self,
        ppn: PowerPlantNumber,
        new_resources: list[Resource],
    ) -> RequestError | None:
        if not self._is_valid_positive_int(ppn.number):
            return RequestError(f"Invalid power plant number: {ppn.number}")

        remaining = [
            plant
            for plant in self._plants
            if plant.number.number != ppn.number
        ]
        if len(remaining) == len(self._plants):
            return RequestError(
                f"Player does not own power plant {ppn.number}"
            )
        if not self._store.can_store_resources(list(new_resources), remaining):
            return RequestError(
                "Remaining resources do not fit on remaining power plants"
            )
        self._plants = remaining
        return None

    def number_of_connectable_cities(
        self, resources: list[Resource]
    ) -> int:
        return self._max_usable.number_of_suppliable_towns(
            list(resources), list(self._plants)
        )

    def can_store_resources(self, resources: list[Resource]) -> bool:
        return self._store.can_store_resources(
            list(resources), list(self._plants)
        )

    def use_power_plant(
        self,
        ppns: list[PowerPlantNumber],
        resources_to_burn: list[Resource],
    ) -> int | RequestError:
        numbers: list[int] = []
        for ppn in ppns:
            if not self._is_valid_positive_int(ppn.number):
                return RequestError(
                    f"Invalid power plant number: {ppn.number}"
                )
            numbers.append(ppn.number)

        if len(numbers) != len(set(numbers)):
            return RequestError("Duplicate power plant in use request")

        by_number = {plant.number.number: plant for plant in self._plants}
        chosen: list[PowerPlant] = []
        for num in numbers:
            plant = by_number.get(num)
            if plant is None:
                return RequestError(f"Player does not own power plant {num}")
            chosen.append(plant)

        return self._use.number_of_suppliable_towns(
            list(resources_to_burn), chosen
        )

    @staticmethod
    def _is_valid_positive_int(value: int) -> bool:
        return (
            not isinstance(value, bool)
            and isinstance(value, int)
            and value >= 1
        )
