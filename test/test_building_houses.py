# pylint: disable=too-many-public-methods
from __future__ import annotations

import json
import unittest
from collections.abc import Sequence

from power_grid.building_houses import BuildingHouses
from power_grid.interfaces import (
    InterfacePlayerBoardBuildingHouses,
    InterfacePowerPlantMarketBuildingHouses,
    InterfaceTownsBuildingHouses,
)
from power_grid.simple_types import PhaseStatus, PlayerColor, RequestError


class PlayerBoardFake(InterfacePlayerBoardBuildingHouses):
    def __init__(self, money: int) -> None:
        self.money = money
        self.spent_history: list[int] = []

    def outstanding_money(self) -> int:
        return self.money

    def spend_money(self, amount: int) -> None:
        self.money -= amount
        self.spent_history.append(amount)


class PowerPlantMarketFake(InterfacePowerPlantMarketBuildingHouses):
    def __init__(self) -> None:
        self.removed_thresholds: list[int] = []

    def remove_power_plants_cheaper_than(self, value: int) -> None:
        self.removed_thresholds.append(value)


class TownsFake(InterfaceTownsBuildingHouses):
    def __init__(self, cost_per_town: int = 10) -> None:
        self.cost_per_town = cost_per_town
        self.house_counts: dict[PlayerColor, int] = {}
        self.calls: list[tuple[PlayerColor, list[str], int]] = []
        self.next_error: RequestError | None = None
        self.override_cost: int | None = None

    def buy_houses(
        self,
        player: PlayerColor,
        town_names: Sequence[str],
        max_money: int,
    ) -> int | RequestError:
        names = list(town_names)
        self.calls.append((player, names, max_money))
        if self.next_error is not None:
            error = self.next_error
            self.next_error = None
            return error

        cost = (
            self.override_cost
            if self.override_cost is not None
            else len(names) * self.cost_per_town
        )
        if cost > max_money:
            return RequestError("Not enough money")

        self.house_counts[player] = self.house_counts.get(player, 0) + len(names)
        return cost

    def get_max_number_of_houses(self) -> int:
        if not self.house_counts:
            return 0
        return max(self.house_counts.values())


class TestBuildingHouses(unittest.TestCase):
    def _make_boards(
        self,
        colors: Sequence[PlayerColor],
        money: int = 100,
    ) -> dict[PlayerColor, PlayerBoardFake]:
        return {color: PlayerBoardFake(money) for color in colors}

    def test_default_end_game_thresholds_by_player_count(self) -> None:
        expected = {2: 21, 3: 17, 4: 17, 5: 15, 6: 14}
        all_colors = list(PlayerColor)
        for count, threshold in expected.items():
            boards = self._make_boards(all_colors[:count])
            phase = BuildingHouses(TownsFake(), PowerPlantMarketFake(), boards)
            self.assertEqual(phase.end_game_town_count, threshold)

        with self.assertRaises(ValueError):
            BuildingHouses(TownsFake(), PowerPlantMarketFake(), {})

        with self.assertRaises(ValueError):
            BuildingHouses(
                TownsFake(),
                PowerPlantMarketFake(),
                self._make_boards([PlayerColor.RED]),
            )

    def test_custom_end_game_threshold_validation(self) -> None:
        boards = self._make_boards([PlayerColor.RED, PlayerColor.BLUE])
        phase = BuildingHouses(
            TownsFake(), PowerPlantMarketFake(), boards, end_game_town_count=5
        )
        self.assertEqual(phase.end_game_town_count, 5)

        with self.assertRaises(ValueError):
            BuildingHouses(
                TownsFake(), PowerPlantMarketFake(), boards, end_game_town_count=0
            )

    def test_start_phase_reverses_player_order(self) -> None:
        order = [PlayerColor.RED, PlayerColor.BLUE, PlayerColor.GREEN]
        boards = self._make_boards(order)
        phase = BuildingHouses(TownsFake(), PowerPlantMarketFake(), boards)

        phase.start_phase(order)
        self.assertTrue(phase.is_active)
        self.assertEqual(phase.current_player, PlayerColor.GREEN)
        self.assertEqual(
            phase.remaining_players,
            [PlayerColor.GREEN, PlayerColor.BLUE, PlayerColor.RED],
        )

    def test_start_phase_validation_errors(self) -> None:
        boards = self._make_boards([PlayerColor.RED, PlayerColor.BLUE])
        phase = BuildingHouses(TownsFake(), PowerPlantMarketFake(), boards)

        with self.assertRaises(ValueError):
            phase.start_phase([])
        with self.assertRaises(ValueError):
            phase.start_phase([PlayerColor.RED, PlayerColor.RED])
        with self.assertRaises(ValueError):
            phase.start_phase([PlayerColor.RED])
        with self.assertRaises(ValueError):
            phase.start_phase([PlayerColor.RED, PlayerColor.GREEN])

    def test_buy_houses_before_start_phase_returns_error(self) -> None:
        boards = self._make_boards([PlayerColor.RED, PlayerColor.BLUE])
        phase = BuildingHouses(TownsFake(), PowerPlantMarketFake(), boards)

        result = phase.buy_houses(PlayerColor.RED, ["Berlin"])
        self.assertIsInstance(result, RequestError)

    def test_buy_houses_wrong_player_returns_error_without_side_effects(self) -> None:
        towns = TownsFake()
        market = PowerPlantMarketFake()
        boards = self._make_boards([PlayerColor.RED, PlayerColor.BLUE])
        phase = BuildingHouses(towns, market, boards)
        phase.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        result = phase.buy_houses(PlayerColor.RED, ["Berlin"])
        self.assertIsInstance(result, RequestError)
        self.assertEqual(phase.current_player, PlayerColor.BLUE)
        self.assertEqual(towns.calls, [])
        self.assertEqual(market.removed_thresholds, [])
        self.assertEqual(boards[PlayerColor.RED].money, 100)

    def test_buy_houses_success_spends_money_and_updates_market(self) -> None:
        towns = TownsFake(cost_per_town=15)
        market = PowerPlantMarketFake()
        boards = self._make_boards([PlayerColor.RED, PlayerColor.BLUE], money=50)
        phase = BuildingHouses(towns, market, boards)
        phase.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        status = phase.buy_houses(PlayerColor.BLUE, ["Berlin", "Hamburg"])
        self.assertEqual(status, PhaseStatus.PHASE_CONTINUES)
        self.assertEqual(towns.calls, [(PlayerColor.BLUE, ["Berlin", "Hamburg"], 50)])
        self.assertEqual(boards[PlayerColor.BLUE].money, 20)
        self.assertEqual(boards[PlayerColor.BLUE].spent_history, [30])
        self.assertEqual(market.removed_thresholds, [2])
        self.assertEqual(phase.current_player, PlayerColor.RED)

    def test_buy_houses_empty_list_passes_turn(self) -> None:
        towns = TownsFake()
        market = PowerPlantMarketFake()
        boards = self._make_boards([PlayerColor.RED, PlayerColor.BLUE], money=50)
        phase = BuildingHouses(towns, market, boards)
        phase.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        status = phase.buy_houses(PlayerColor.BLUE, [])
        self.assertEqual(status, PhaseStatus.PHASE_CONTINUES)
        self.assertEqual(towns.calls, [])
        self.assertEqual(market.removed_thresholds, [])
        self.assertEqual(boards[PlayerColor.BLUE].money, 50)
        self.assertEqual(phase.current_player, PlayerColor.RED)

    def test_buy_houses_towns_error_does_not_spend_or_advance_turn(self) -> None:
        towns = TownsFake(cost_per_town=10)
        market = PowerPlantMarketFake()
        boards = self._make_boards([PlayerColor.RED, PlayerColor.BLUE], money=15)
        phase = BuildingHouses(towns, market, boards)
        phase.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        towns.next_error = RequestError("City already full in Step 1")
        error = phase.buy_houses(PlayerColor.BLUE, ["Berlin"])
        self.assertEqual(error, RequestError("City already full in Step 1"))
        self.assertEqual(boards[PlayerColor.BLUE].money, 15)
        self.assertEqual(market.removed_thresholds, [])
        self.assertEqual(phase.current_player, PlayerColor.BLUE)

        retry_status = phase.buy_houses(PlayerColor.BLUE, ["Hamburg"])
        self.assertEqual(retry_status, PhaseStatus.PHASE_CONTINUES)
        self.assertEqual(boards[PlayerColor.BLUE].money, 5)
        self.assertEqual(phase.current_player, PlayerColor.RED)

    def test_full_phase_ends_when_below_end_game_threshold(self) -> None:
        towns = TownsFake(cost_per_town=10)
        market = PowerPlantMarketFake()
        order = [PlayerColor.RED, PlayerColor.BLUE, PlayerColor.GREEN]
        boards = self._make_boards(order, money=100)
        phase = BuildingHouses(towns, market, boards, end_game_town_count=5)
        phase.start_phase(order)

        self.assertEqual(
            phase.buy_houses(PlayerColor.GREEN, ["A", "B"]),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            phase.buy_houses(PlayerColor.BLUE, ["C"]),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            phase.buy_houses(PlayerColor.RED, ["D", "E", "F"]),
            PhaseStatus.PHASE_ENDS,
        )
        self.assertFalse(phase.is_active)
        self.assertIsNone(phase.current_player)
        self.assertEqual(market.removed_thresholds, [2, 2, 3])
        self.assertIsInstance(
            phase.buy_houses(PlayerColor.RED, []), RequestError
        )

    def test_game_end_waits_for_all_players_to_finish_phase(self) -> None:
        towns = TownsFake(cost_per_town=10)
        market = PowerPlantMarketFake()
        order = [PlayerColor.RED, PlayerColor.BLUE, PlayerColor.GREEN]
        boards = self._make_boards(order, money=100)
        phase = BuildingHouses(towns, market, boards, end_game_town_count=3)
        phase.start_phase(order)

        # First player in reverse order reaches threshold -> phase still continues
        self.assertEqual(
            phase.buy_houses(PlayerColor.GREEN, ["A", "B", "C"]),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertTrue(phase.is_active)

        # Second player still gets their turn
        self.assertEqual(
            phase.buy_houses(PlayerColor.BLUE, ["D"]),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertTrue(phase.is_active)

        # Last player passes -> phase ends AND triggers GAME_ENDS
        self.assertEqual(
            phase.buy_houses(PlayerColor.RED, []),
            PhaseStatus.GAME_ENDS,
        )
        self.assertFalse(phase.is_active)

    def test_game_end_triggered_by_last_player_in_phase(self) -> None:
        towns = TownsFake(cost_per_town=10)
        market = PowerPlantMarketFake()
        order = [PlayerColor.RED, PlayerColor.BLUE]
        boards = self._make_boards(order, money=100)
        phase = BuildingHouses(towns, market, boards, end_game_town_count=2)
        phase.start_phase(order)

        self.assertEqual(
            phase.buy_houses(PlayerColor.BLUE, ["A"]),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            phase.buy_houses(PlayerColor.RED, ["B", "C"]),
            PhaseStatus.GAME_ENDS,
        )

    def test_multiple_rounds_reuse(self) -> None:
        towns = TownsFake(cost_per_town=10)
        market = PowerPlantMarketFake()
        boards = self._make_boards([PlayerColor.RED, PlayerColor.BLUE], money=100)
        phase = BuildingHouses(towns, market, boards, end_game_town_count=4)

        phase.start_phase([PlayerColor.RED, PlayerColor.BLUE])
        self.assertEqual(
            phase.buy_houses(PlayerColor.BLUE, ["A"]), PhaseStatus.PHASE_CONTINUES
        )
        self.assertEqual(
            phase.buy_houses(PlayerColor.RED, ["B"]), PhaseStatus.PHASE_ENDS
        )

        # Round 2 with reversed player order
        phase.start_phase([PlayerColor.BLUE, PlayerColor.RED])
        self.assertEqual(phase.current_player, PlayerColor.RED)
        self.assertEqual(
            phase.buy_houses(PlayerColor.RED, ["C", "D", "E"]),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            phase.buy_houses(PlayerColor.BLUE, ["F"]),
            PhaseStatus.GAME_ENDS,
        )

    def test_get_state_json_before_during_and_after_phase(self) -> None:
        towns = TownsFake(cost_per_town=10)
        market = PowerPlantMarketFake()
        order = [PlayerColor.RED, PlayerColor.BLUE]
        boards = self._make_boards(order, money=100)
        phase = BuildingHouses(towns, market, boards, end_game_town_count=7)

        before = json.loads(phase.get_state())
        self.assertEqual(
            before,
            {
                "is_active": False,
                "current_player": None,
                "remaining_players": [],
                "end_game_town_count": 7,
            },
        )

        phase.start_phase(order)
        during_first = json.loads(phase.get_state())
        self.assertEqual(
            during_first,
            {
                "is_active": True,
                "current_player": "BLUE",
                "remaining_players": ["BLUE", "RED"],
                "end_game_town_count": 7,
            },
        )

        phase.buy_houses(PlayerColor.BLUE, ["A"])
        during_second = json.loads(phase.get_state())
        self.assertEqual(
            during_second,
            {
                "is_active": True,
                "current_player": "RED",
                "remaining_players": ["RED"],
                "end_game_town_count": 7,
            },
        )

        phase.buy_houses(PlayerColor.RED, [])
        after = json.loads(phase.get_state())
        self.assertEqual(
            after,
            {
                "is_active": False,
                "current_player": None,
                "remaining_players": [],
                "end_game_town_count": 7,
            },
        )

    def test_negative_cost_from_towns_raises_value_error(self) -> None:
        towns = TownsFake()
        towns.override_cost = -5
        boards = self._make_boards([PlayerColor.RED, PlayerColor.BLUE], money=50)
        phase = BuildingHouses(towns, PowerPlantMarketFake(), boards)
        phase.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        with self.assertRaises(ValueError):
            phase.buy_houses(PlayerColor.BLUE, ["A"])
