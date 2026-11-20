import unittest

from power_grid.determine_player_order import DeterminePlayerOrder, PlayerOrderData
from power_grid.power_plant import PowerPlantNumber
from power_grid.simple_types import PlayerColor


class TestDeterminePlayerOrder(unittest.TestCase):
    def test_reorder_uses_connected_cities_then_largest_plant(self) -> None:
        ordering = DeterminePlayerOrder([
            PlayerOrderData(
                PlayerColor.RED, 3, PowerPlantNumber(17), 0, 20
            ),
            PlayerOrderData(
                PlayerColor.BLUE, 5, PowerPlantNumber(10), 0, 20
            ),
            PlayerOrderData(
                PlayerColor.YELLOW, 3, PowerPlantNumber(22), 0, 20
            ),
            PlayerOrderData(
                PlayerColor.GREEN, 1, PowerPlantNumber(50), 0, 20
            ),
        ])

        self.assertEqual(
            ordering.reorder(),
            [
                PlayerColor.BLUE,
                PlayerColor.YELLOW,
                PlayerColor.RED,
                PlayerColor.GREEN,
            ],
        )
