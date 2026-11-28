# pylint: disable=too-many-public-methods
from __future__ import annotations

import unittest

from power_grid.player_power_plants import PlayerPowerPlants
from power_grid.power_plant import PowerPlant, PowerPlantNumber
from power_grid.simple_types import RequestError, Resource


def _plant(
    number: int,
    resources: list[Resource],
    amount: int,
    cities: int,
) -> PowerPlant:
    return PowerPlant(PowerPlantNumber(number), resources, amount, cities)


class TestPlayerPowerPlants(unittest.TestCase):
    def test_init_validation_and_best_plant(self) -> None:
        empty = PlayerPowerPlants()
        self.assertEqual(empty.power_plants, [])
        self.assertEqual(empty.max_plants, 3)
        self.assertEqual(empty.best_power_plant().number, 0)

        p4 = _plant(4, [Resource.COAL], 2, 1)
        p13 = _plant(13, [], 0, 1)
        owned = PlayerPowerPlants([p4, p13], max_plants=4)
        self.assertEqual(owned.max_plants, 4)
        self.assertEqual(owned.best_power_plant().number, 13)

        # Defensive copy on property
        snap = owned.power_plants
        snap.clear()
        self.assertEqual(len(owned.power_plants), 2)

        for bad_max in (0, -1, True, False):
            with self.subTest(bad_max=bad_max):
                with self.assertRaises(ValueError):
                    PlayerPowerPlants(max_plants=bad_max)

        with self.assertRaises(ValueError):
            PlayerPowerPlants([p4, p13], max_plants=1)
        with self.assertRaises(ValueError):
            PlayerPowerPlants([p4, _plant(4, [Resource.OIL], 1, 1)])
        with self.assertRaises(ValueError):
            PlayerPowerPlants([_plant(0, [], 0, 1)])
        with self.assertRaises(ValueError):
            PlayerPowerPlants([_plant(True, [], 0, 1)])

    def test_receive_and_limit_checks(self) -> None:
        plants = PlayerPowerPlants(max_plants=3)
        self.assertTrue(
            plants.receive_power_plant(_plant(3, [Resource.OIL], 2, 1))
        )
        self.assertTrue(
            plants.receive_power_plant(_plant(5, [Resource.COAL, Resource.OIL], 2, 1))
        )
        self.assertTrue(plants.receive_power_plant(_plant(13, [], 0, 1)))
        self.assertFalse(
            plants.receive_power_plant(_plant(10, [Resource.COAL], 2, 2))
        )
        self.assertEqual(plants.best_power_plant().number, 13)

        with self.assertRaises(ValueError):
            plants.receive_power_plant(_plant(10, [Resource.COAL], 2, 2))
        with self.assertRaises(ValueError):
            plants.receive_power_plant(_plant(0, [], 0, 1))

    def test_remove_power_plant_valid_and_errors(self) -> None:
        p3 = _plant(3, [Resource.OIL], 2, 1)
        p4 = _plant(4, [Resource.COAL], 2, 1)
        plants = PlayerPowerPlants([p3, p4], max_plants=3)

        self.assertIsInstance(
            plants.remove_power_plant(PowerPlantNumber(0), []), RequestError
        )
        self.assertIsInstance(
            plants.remove_power_plant(PowerPlantNumber(True), []), RequestError
        )
        self.assertIsInstance(
            plants.remove_power_plant(PowerPlantNumber(99), []), RequestError
        )
        # Remaining plant p4 cannot store OIL
        self.assertIsInstance(
            plants.remove_power_plant(
                PowerPlantNumber(3), [Resource.OIL]
            ),
            RequestError,
        )
        self.assertEqual(len(plants.power_plants), 2)

        self.assertIsNone(
            plants.remove_power_plant(
                PowerPlantNumber(3), [Resource.COAL, Resource.COAL]
            )
        )
        self.assertEqual([p.number.number for p in plants.power_plants], [4])

    def test_storage_connectable_and_use_power_plant(self) -> None:
        p5 = _plant(5, [Resource.COAL, Resource.OIL], 2, 2)
        p13 = _plant(13, [], 0, 1)
        plants = PlayerPowerPlants([p5, p13])

        self.assertTrue(
            plants.can_store_resources([Resource.COAL, Resource.OIL, Resource.OIL])
        )
        self.assertFalse(
            plants.can_store_resources(
                [Resource.COAL] * 5
            )
        )
        self.assertEqual(plants.number_of_connectable_cities([]), 1)
        self.assertEqual(
            plants.number_of_connectable_cities([Resource.COAL, Resource.OIL]),
            3,
        )

        self.assertIsInstance(
            plants.use_power_plant([PowerPlantNumber(0)], []), RequestError
        )
        self.assertIsInstance(
            plants.use_power_plant([PowerPlantNumber(True)], []), RequestError
        )
        self.assertIsInstance(
            plants.use_power_plant(
                [PowerPlantNumber(13), PowerPlantNumber(13)], []
            ),
            RequestError,
        )
        self.assertIsInstance(
            plants.use_power_plant([PowerPlantNumber(99)], []), RequestError
        )
        self.assertIsInstance(
            plants.use_power_plant(
                [PowerPlantNumber(5)], [Resource.GARBAGE, Resource.GARBAGE]
            ),
            RequestError,
        )

        self.assertEqual(
            plants.use_power_plant(
                [PowerPlantNumber(5), PowerPlantNumber(13)],
                [Resource.COAL, Resource.OIL],
            ),
            3,
        )
