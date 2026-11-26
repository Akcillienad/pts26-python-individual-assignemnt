from __future__ import annotations

from power_grid.simple_types import Resource
from power_grid.power_plant import PowerPlant


class MaximumNumberOfUsablePowerPlants:

    def number_of_suppliable_towns(
        self, resources: list[Resource], powerplants: list[PowerPlant]
    ) -> int:
        sorted_plants = sorted(
            powerplants, key=lambda plant: len(plant.accepted_resources)
        )
        return self._find_max_towns(resources, sorted_plants, 0)

    def _find_max_towns(
        self,
        resources: list[Resource],
        powerplants: list[PowerPlant],
        index: int,
    ) -> int:
        if index == len(powerplants):
            return 0

        plant = powerplants[index]
        if plant.resource_amount == 0:
            return plant.number_of_cities + self._find_max_towns(
                resources, powerplants, index + 1
            )

        best = self._find_max_towns(resources, powerplants, index + 1)
        remaining = self._use_resources(resources, plant)
        if remaining is not None:
            towns = plant.number_of_cities + self._find_max_towns(
                remaining, powerplants, index + 1
            )
            best = max(best, towns)

        return best

    def _use_resources(
        self, resources: list[Resource], plant: PowerPlant
    ) -> list[Resource] | None:
        remaining = resources.copy()
        for _ in range(plant.resource_amount):
            for resource_type in plant.accepted_resources:
                if resource_type in remaining:
                    remaining.remove(resource_type)
                    break
            else:
                return None
        return remaining
