import unittest

from power_grid.simple_types import Resource
from power_grid.power_plant import PowerPlant, PowerPlantNumber
from power_grid.maximum_number_of_usable_power_plants import (
    MaximumNumberOfUsablePowerPlants,
)


class TestMaximumNumberOfUsablePowerPlants(unittest.TestCase):

    def test_single_power_plant(self) -> None:
        plant = PowerPlant(PowerPlantNumber(8), [Resource.COAL], 3, 2)
        calculator = MaximumNumberOfUsablePowerPlants()
        resources = [Resource.COAL, Resource.COAL, Resource.COAL]

        result = calculator.number_of_suppliable_towns(resources, [plant])

        self.assertEqual(result, 2)

    def test_extra_resources_allowed(self) -> None:
        plant = PowerPlant(PowerPlantNumber(4), [Resource.COAL], 2, 1)
        calculator = MaximumNumberOfUsablePowerPlants()
        resources = [Resource.COAL, Resource.COAL, Resource.COAL, Resource.OIL]

        result = calculator.number_of_suppliable_towns(resources, [plant])

        self.assertEqual(result, 1)

    def test_not_enough_resources(self) -> None:
        plant = PowerPlant(PowerPlantNumber(8), [Resource.COAL], 3, 2)
        calculator = MaximumNumberOfUsablePowerPlants()
        resources = [Resource.COAL, Resource.COAL]

        result = calculator.number_of_suppliable_towns(resources, [plant])

        self.assertEqual(result, 0)

    def test_wrong_resource_type(self) -> None:
        plant = PowerPlant(PowerPlantNumber(6), [Resource.GARBAGE], 1, 1)
        calculator = MaximumNumberOfUsablePowerPlants()
        resources = [Resource.URANIUM]

        result = calculator.number_of_suppliable_towns(resources, [plant])

        self.assertEqual(result, 0)

    def test_hybrid_power_plant(self) -> None:
        plant = PowerPlant(
            PowerPlantNumber(5), [Resource.COAL, Resource.OIL], 2, 1
        )
        calculator = MaximumNumberOfUsablePowerPlants()
        resources = [Resource.COAL, Resource.OIL]

        result = calculator.number_of_suppliable_towns(resources, [plant])

        self.assertEqual(result, 1)

    def test_ecological_power_plant(self) -> None:
        plant = PowerPlant(PowerPlantNumber(13), [], 0, 1)
        calculator = MaximumNumberOfUsablePowerPlants()

        result = calculator.number_of_suppliable_towns([], [plant])

        self.assertEqual(result, 1)

    def test_empty_plants_and_resources(self) -> None:
        calculator = MaximumNumberOfUsablePowerPlants()

        result = calculator.number_of_suppliable_towns([], [])

        self.assertEqual(result, 0)

    def test_no_power_plants_with_resources(self) -> None:
        calculator = MaximumNumberOfUsablePowerPlants()

        result = calculator.number_of_suppliable_towns([Resource.OIL], [])

        self.assertEqual(result, 0)

    def test_chooses_higher_city_plant_when_competing(self) -> None:
        small_coal = PowerPlant(PowerPlantNumber(4), [Resource.COAL], 2, 1)
        large_coal = PowerPlant(PowerPlantNumber(15), [Resource.COAL], 2, 3)
        calculator = MaximumNumberOfUsablePowerPlants()
        resources = [Resource.COAL, Resource.COAL]

        result = calculator.number_of_suppliable_towns(
            resources, [small_coal, large_coal]
        )

        self.assertEqual(result, 3)

    def test_chooses_two_smaller_plants_over_one_larger(self) -> None:
        big_plant = PowerPlant(PowerPlantNumber(20), [Resource.COAL], 3, 3)
        small_plant_1 = PowerPlant(PowerPlantNumber(25), [Resource.COAL], 1, 2)
        small_plant_2 = PowerPlant(PowerPlantNumber(10), [Resource.COAL], 2, 2)
        calculator = MaximumNumberOfUsablePowerPlants()
        resources = [Resource.COAL, Resource.COAL, Resource.COAL]

        result = calculator.number_of_suppliable_towns(
            resources, [big_plant, small_plant_1, small_plant_2]
        )

        self.assertEqual(result, 4)

    def test_hybrid_and_single_resource_optimal_allocation(self) -> None:
        coal_plant = PowerPlant(PowerPlantNumber(10), [Resource.COAL], 2, 2)
        hybrid_plant = PowerPlant(
            PowerPlantNumber(12), [Resource.COAL, Resource.OIL], 2, 3
        )
        oil_plant = PowerPlant(PowerPlantNumber(9), [Resource.OIL], 1, 2)
        calculator = MaximumNumberOfUsablePowerPlants()
        resources = [Resource.COAL, Resource.COAL, Resource.OIL]

        result = calculator.number_of_suppliable_towns(
            resources, [hybrid_plant, coal_plant, oil_plant]
        )

        self.assertEqual(result, 5)

    def test_multiple_power_plants_with_eco_and_hybrid(self) -> None:
        uranium_plant = PowerPlant(PowerPlantNumber(11), [Resource.URANIUM], 1, 2)
        hybrid_plant = PowerPlant(
            PowerPlantNumber(12), [Resource.COAL, Resource.OIL], 2, 2
        )
        eco_plant = PowerPlant(PowerPlantNumber(13), [], 0, 1)
        coal_plant = PowerPlant(PowerPlantNumber(15), [Resource.COAL], 2, 3)
        calculator = MaximumNumberOfUsablePowerPlants()
        resources = [
            Resource.COAL,
            Resource.COAL,
            Resource.OIL,
            Resource.URANIUM,
        ]

        result = calculator.number_of_suppliable_towns(
            resources, [uranium_plant, hybrid_plant, eco_plant, coal_plant]
        )

        self.assertEqual(result, 6)

    def test_does_not_mutate_inputs(self) -> None:
        coal_plant = PowerPlant(PowerPlantNumber(10), [Resource.COAL], 2, 2)
        hybrid_plant = PowerPlant(
            PowerPlantNumber(12), [Resource.COAL, Resource.OIL], 2, 3
        )
        calculator = MaximumNumberOfUsablePowerPlants()
        resources = [Resource.COAL, Resource.COAL, Resource.OIL]
        plants = [hybrid_plant, coal_plant]

        calculator.number_of_suppliable_towns(resources, plants)

        self.assertEqual(resources, [Resource.COAL, Resource.COAL, Resource.OIL])
        self.assertEqual(plants, [hybrid_plant, coal_plant])
