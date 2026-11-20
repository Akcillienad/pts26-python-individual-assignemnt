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

    def test_reorder_preserves_input_order_for_complete_ties(self) -> None:
        ordering = DeterminePlayerOrder([
            PlayerOrderData(
                PlayerColor.RED, 4, PowerPlantNumber(15), 0, 20
            ),
            PlayerOrderData(
                PlayerColor.BLUE, 4, PowerPlantNumber(15), 0, 20
            ),
        ])

        self.assertEqual(
            ordering.reorder(),
            [PlayerColor.RED, PlayerColor.BLUE],
        )

    def test_game_result_uses_powered_cities_first(self) -> None:
        ordering = DeterminePlayerOrder([
            PlayerOrderData(
                PlayerColor.RED, 8, PowerPlantNumber(30), 4, 50
            ),
            PlayerOrderData(
                PlayerColor.BLUE, 5, PowerPlantNumber(20), 5, 10
            ),
            PlayerOrderData(
                PlayerColor.YELLOW, 6, PowerPlantNumber(25), 5, 30
            ),
        ])

        self.assertEqual(
            ordering.game_result(),
            [PlayerColor.YELLOW, PlayerColor.BLUE, PlayerColor.RED],
        )

    def test_game_result_uses_connected_cities_as_final_tiebreaker(self) -> None:
        ordering = DeterminePlayerOrder([
            PlayerOrderData(
                PlayerColor.RED, 7, PowerPlantNumber(25), 5, 40
            ),
            PlayerOrderData(
                PlayerColor.BLUE, 8, PowerPlantNumber(20), 5, 40
            ),
        ])

        self.assertEqual(
            ordering.game_result(),
            [PlayerColor.BLUE, PlayerColor.RED],
        )

    def test_game_result_preserves_order_when_all_tiebreakers_tie(self) -> None:
        ordering = DeterminePlayerOrder([
            PlayerOrderData(
                PlayerColor.RED, 6, PowerPlantNumber(25), 5, 40
            ),
            PlayerOrderData(
                PlayerColor.BLUE, 6, PowerPlantNumber(25), 5, 40
            ),
        ])

        self.assertEqual(
            ordering.game_result(),
            [PlayerColor.RED, PlayerColor.BLUE],
        )

    def test_duplicate_player_colors_are_rejected(self) -> None:
        player = PlayerOrderData(
            PlayerColor.RED, 0, PowerPlantNumber(3), 0, 50
        )

        with self.assertRaises(ValueError):
            DeterminePlayerOrder([player, player])

    def test_negative_player_statistics_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PlayerOrderData(
                PlayerColor.RED, -1, PowerPlantNumber(3), 0, 50
            )

    def test_game_result_uses_money_before_connected_cities(self) -> None:
        ordering = DeterminePlayerOrder([
            PlayerOrderData(
                PlayerColor.RED, 9, PowerPlantNumber(20), 5, 20
            ),
            PlayerOrderData(
                PlayerColor.BLUE, 4, PowerPlantNumber(25), 5, 30
            ),
        ])

        self.assertEqual(
            ordering.game_result(),
            [PlayerColor.BLUE, PlayerColor.RED],
        )
