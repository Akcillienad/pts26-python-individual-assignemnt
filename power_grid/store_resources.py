# test
from power_grid.power_plant import PowerPlant
from power_grid.simple_types import Resource


class StoreResources:

    def can_store_resources(
        self, resources: list[Resource], powerplants: list[PowerPlant]
    ) -> bool:
        remaining = resources.copy()

        # elektrarne s jednym typom suroviny
        for plant in powerplants:
            if len(plant.accepted_resources) == 1:
                capacity = plant.resource_amount * 2
                resource_type = plant.accepted_resources[0]
                for _ in range(capacity):
                    if resource_type in remaining:
                        remaining.remove(resource_type)

        # hybridne elektrarne
        for plant in powerplants:
            if len(plant.accepted_resources) > 1:
                capacity = plant.resource_amount * 2
                for _ in range(capacity):
                    for resource_type in plant.accepted_resources:
                        if resource_type in remaining:
                            remaining.remove(resource_type)
                            break

        # nezostali suroviny, vsetky sa zmestili
        return len(remaining) == 0
