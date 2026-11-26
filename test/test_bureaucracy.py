# pylint: disable=too-many-public-methods
from __future__ import annotations

import json
import unittest
from collections.abc import Sequence

from power_grid.bureaucracy import Bureaucracy
from power_grid.power_plant import PowerPlantNumber
from power_grid.simple_types import (
    PhaseStatus,
    PlayerColor,
    RequestError,
    Resource,
)
from test.blue_test_fakes import (
    FakePowerPlantMarket,
    FakeResourceMarket,
    SimplePlayerBoardFake,
)


class OrderTrackingMarket:
    def __init__(self, log: list[str]) -> None:
        self._log = log

    def refill(self) -> None:
        self._log.append("refill")


class OrderTrackingPlantMarket:
    def __init__(self, log: list[str]) -> None:
        self._log = log

    def prepare_next_turn(self) -> None:
        self._log.append("prepare_next_turn")


class TestBureaucracy(unittest.TestCase):
    def _make_boards(
        self,
        colors: Sequence[PlayerColor],
    ) -> dict[PlayerColor, SimplePlayerBoardFake]:
        return {color: SimplePlayerBoardFake(color) for color in colors}

    def test_init_rejects_empty_boards(self) -> None:
        with self.assertRaises(ValueError):
            Bureaucracy({}, FakeResourceMarket(), FakePowerPlantMarket())

    def test_start_phase_preserves_forward_order_and_validates(self) -> None:
        order = [PlayerColor.RED, PlayerColor.BLUE, PlayerColor.YELLOW]
        phase = Bureaucracy(
            self._make_boards(order),
            FakeResourceMarket(),
            FakePowerPlantMarket(),
        )

        self.assertFalse(phase.is_active)
        self.assertIsNone(phase.current_player)
        self.assertEqual(phase.remaining_players, [])

        phase.start_phase(order)
        self.assertTrue(phase.is_active)
        self.assertEqual(phase.current_player, PlayerColor.RED)
        self.assertEqual(phase.remaining_players, order)

        with self.assertRaises(ValueError):
            phase.start_phase([])
        with self.assertRaises(ValueError):
            phase.start_phase([PlayerColor.RED, PlayerColor.RED, PlayerColor.BLUE])
        with self.assertRaises(ValueError):
            phase.start_phase([PlayerColor.RED, PlayerColor.BLUE])
        with self.assertRaises(ValueError):
            phase.start_phase(
                [PlayerColor.RED, PlayerColor.BLUE, PlayerColor.BLACK]
            )

    def test_use_power_plants_inactive_or_wrong_player(self) -> None:
        boards = self._make_boards([PlayerColor.RED, PlayerColor.BLUE])
        market = FakeResourceMarket()
        plant_market = FakePowerPlantMarket()
        phase = Bureaucracy(boards, market, plant_market)

        self.assertIsInstance(
            phase.use_power_plants(PlayerColor.RED, [], []), RequestError
        )

        phase.start_phase([PlayerColor.RED, PlayerColor.BLUE])
        self.assertIsInstance(
            phase.use_power_plants(PlayerColor.BLUE, [], []), RequestError
        )
        self.assertIsInstance(
            phase.use_power_plants(PlayerColor.BLACK, [], []), RequestError
        )
        self.assertEqual(phase.current_player, PlayerColor.RED)
        self.assertEqual(market.refill_calls, 0)
        self.assertEqual(plant_market.prepare_calls, 0)

    def test_empty_plants_still_invokes_board_for_zero_city_payout(
        self,
    ) -> None:
        boards = self._make_boards([PlayerColor.RED, PlayerColor.BLUE])
        market = FakeResourceMarket()
        plant_market = FakePowerPlantMarket()
        phase = Bureaucracy(boards, market, plant_market)
        phase.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        status = phase.use_power_plants(PlayerColor.RED, [], [])
        self.assertEqual(status, PhaseStatus.PHASE_CONTINUES)
        self.assertEqual(boards[PlayerColor.RED].history, [("use", ([], []))])
        self.assertEqual(market.refill_calls, 0)
        self.assertEqual(plant_market.prepare_calls, 0)

    def test_board_error_blocks_turn_advance_and_end_hooks(self) -> None:
        boards = self._make_boards([PlayerColor.RED, PlayerColor.BLUE])
        market = FakeResourceMarket()
        plant_market = FakePowerPlantMarket()
        phase = Bureaucracy(boards, market, plant_market)
        phase.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        boards[PlayerColor.RED].next_error = RequestError("Not enough fuel")
        err = phase.use_power_plants(
            PlayerColor.RED, [PowerPlantNumber(4)], [Resource.COAL]
        )
        self.assertEqual(err, RequestError("Not enough fuel"))
        self.assertEqual(phase.current_player, PlayerColor.RED)
        self.assertEqual(market.refill_calls, 0)
        self.assertEqual(plant_market.prepare_calls, 0)

        boards[PlayerColor.RED].next_error = None
        self.assertEqual(
            phase.use_power_plants(
                PlayerColor.RED, [PowerPlantNumber(4)], [Resource.COAL]
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(phase.current_player, PlayerColor.BLUE)

    def test_last_player_triggers_refill_then_prepare_next_turn(self) -> None:
        call_order: list[str] = []
        boards = self._make_boards([PlayerColor.RED, PlayerColor.BLUE])
        phase = Bureaucracy(
            boards,
            OrderTrackingMarket(call_order),
            OrderTrackingPlantMarket(call_order),
        )
        phase.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        self.assertEqual(
            phase.use_power_plants(
                PlayerColor.RED, [PowerPlantNumber(3)], [Resource.OIL]
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(call_order, [])

        self.assertEqual(
            phase.use_power_plants(PlayerColor.BLUE, [], []),
            PhaseStatus.PHASE_ENDS,
        )
        self.assertEqual(call_order, ["refill", "prepare_next_turn"])
        self.assertFalse(phase.is_active)
        self.assertIsNone(phase.current_player)
        self.assertIsInstance(
            phase.use_power_plants(PlayerColor.RED, [], []), RequestError
        )

    def test_multi_round_reuse_and_get_state_json(self) -> None:
        boards = self._make_boards([PlayerColor.RED, PlayerColor.BLUE])
        market = FakeResourceMarket()
        plant_market = FakePowerPlantMarket()
        phase = Bureaucracy(boards, market, plant_market)

        self.assertEqual(
            json.loads(phase.get_state()),
            {
                "is_active": False,
                "current_player": None,
                "remaining_players": [],
            },
        )

        phase.start_phase([PlayerColor.RED, PlayerColor.BLUE])
        self.assertEqual(
            json.loads(phase.get_state()),
            {
                "is_active": True,
                "current_player": "RED",
                "remaining_players": ["RED", "BLUE"],
            },
        )
        phase.use_power_plants(PlayerColor.RED, [], [])
        self.assertEqual(
            json.loads(phase.get_state()),
            {
                "is_active": True,
                "current_player": "BLUE",
                "remaining_players": ["BLUE"],
            },
        )
        phase.use_power_plants(PlayerColor.BLUE, [], [])
        self.assertEqual(
            json.loads(phase.get_state()),
            {
                "is_active": False,
                "current_player": None,
                "remaining_players": [],
            },
        )

        # Round 2 in reversed order
        phase.start_phase([PlayerColor.BLUE, PlayerColor.RED])
        self.assertEqual(phase.current_player, PlayerColor.BLUE)
        phase.use_power_plants(PlayerColor.BLUE, [], [])
        self.assertEqual(
            phase.use_power_plants(PlayerColor.RED, [], []),
            PhaseStatus.PHASE_ENDS,
        )
        self.assertEqual(market.refill_calls, 2)
        self.assertEqual(plant_market.prepare_calls, 2)
