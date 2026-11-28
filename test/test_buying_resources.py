# pylint: disable=too-many-public-methods
from __future__ import annotations

import json
import unittest
from collections.abc import Sequence
from test.blue_test_fakes import SimplePlayerBoardFake

from power_grid.buying_resources import BuyingResources
from power_grid.simple_types import (
    PhaseStatus,
    PlayerColor,
    RequestError,
    Resource,
)


class TestBuyingResources(unittest.TestCase):
    def _boards(
        self,
        colors: Sequence[PlayerColor],
    ) -> dict[PlayerColor, SimplePlayerBoardFake]:
        return {color: SimplePlayerBoardFake(color) for color in colors}

    def test_init_rejects_empty_player_boards(self) -> None:
        with self.assertRaises(ValueError):
            BuyingResources({})

    def test_start_phase_reverses_order_and_copies_input(self) -> None:
        order = [PlayerColor.RED, PlayerColor.BLUE, PlayerColor.GREEN]
        phase = BuyingResources(self._boards(order))

        self.assertFalse(phase.is_active)
        self.assertIsNone(phase.current_player)
        self.assertEqual(phase.remaining_players, [])

        phase.start_phase(order)
        order.reverse()
        expected_reverse = [
            PlayerColor.GREEN,
            PlayerColor.BLUE,
            PlayerColor.RED,
        ]
        self.assertEqual(phase.remaining_players, expected_reverse)
        self.assertEqual(phase.current_player, PlayerColor.GREEN)
        self.assertTrue(phase.is_active)

        rem_copy = phase.remaining_players
        rem_copy.clear()
        self.assertEqual(len(phase.remaining_players), 3)

    def test_start_phase_validation_errors(self) -> None:
        phase = BuyingResources(
            self._boards([PlayerColor.RED, PlayerColor.BLUE])
        )
        invalid_orders = [
            [],
            [PlayerColor.RED, PlayerColor.RED],
            [PlayerColor.RED],
            [PlayerColor.RED, PlayerColor.GREEN],
        ]
        for bad_order in invalid_orders:
            with self.assertRaises(ValueError):
                phase.start_phase(bad_order)

    def test_buy_resources_inactive_or_wrong_player(self) -> None:
        boards = self._boards([PlayerColor.RED, PlayerColor.BLUE])
        phase = BuyingResources(boards)

        self.assertIsInstance(
            phase.buy_resources(PlayerColor.BLUE, [Resource.COAL]),
            RequestError,
        )

        phase.start_phase([PlayerColor.RED, PlayerColor.BLUE])
        # Out-of-order registered player
        self.assertIsInstance(
            phase.buy_resources(PlayerColor.RED, [Resource.COAL]),
            RequestError,
        )
        # Unregistered player
        self.assertIsInstance(
            phase.buy_resources(PlayerColor.BLACK, [Resource.COAL]),
            RequestError,
        )
        self.assertEqual(phase.current_player, PlayerColor.BLUE)
        self.assertEqual(boards[PlayerColor.RED].history, [])
        self.assertEqual(boards[PlayerColor.BLUE].history, [])

    def test_buy_resources_empty_skips_board_and_advances(self) -> None:
        boards = self._boards([PlayerColor.RED, PlayerColor.BLUE])
        phase = BuyingResources(boards)
        phase.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        status = phase.buy_resources(PlayerColor.BLUE, [])
        self.assertEqual(status, PhaseStatus.PHASE_CONTINUES)
        self.assertEqual(boards[PlayerColor.BLUE].history, [])
        self.assertEqual(phase.current_player, PlayerColor.RED)

    def test_buy_resources_error_does_not_advance_and_allows_retry(
        self,
    ) -> None:
        boards = self._boards([PlayerColor.RED, PlayerColor.BLUE])
        phase = BuyingResources(boards)
        phase.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        boards[PlayerColor.BLUE].next_error = RequestError("Storage full")
        err = phase.buy_resources(PlayerColor.BLUE, [Resource.OIL])
        self.assertEqual(err, RequestError("Storage full"))
        self.assertEqual(phase.current_player, PlayerColor.BLUE)

        boards[PlayerColor.BLUE].next_error = None
        req = [Resource.COAL]
        status = phase.buy_resources(PlayerColor.BLUE, req)
        req.append(Resource.URANIUM)
        self.assertEqual(status, PhaseStatus.PHASE_CONTINUES)
        self.assertEqual(
            boards[PlayerColor.BLUE].history, [("buy", [Resource.COAL])]
        )
        self.assertEqual(phase.current_player, PlayerColor.RED)

    def test_full_phase_and_multi_round_reuse(self) -> None:
        order = [PlayerColor.RED, PlayerColor.BLUE, PlayerColor.YELLOW]
        boards = self._boards(order)
        phase = BuyingResources(boards)
        phase.start_phase(order)

        self.assertEqual(
            phase.buy_resources(PlayerColor.YELLOW, [Resource.COAL]),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            phase.buy_resources(PlayerColor.BLUE, []),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            phase.buy_resources(PlayerColor.RED, [Resource.OIL]),
            PhaseStatus.PHASE_ENDS,
        )
        self.assertFalse(phase.is_active)
        self.assertIsNone(phase.current_player)
        self.assertIsInstance(
            phase.buy_resources(PlayerColor.RED, []), RequestError
        )

        # Round 2 with new order
        phase.start_phase([PlayerColor.YELLOW, PlayerColor.RED, PlayerColor.BLUE])
        self.assertEqual(phase.current_player, PlayerColor.BLUE)
        self.assertEqual(
            phase.buy_resources(PlayerColor.BLUE, [Resource.GARBAGE]),
            PhaseStatus.PHASE_CONTINUES,
        )

    def test_get_state_json_lifecycle(self) -> None:
        order = [PlayerColor.RED, PlayerColor.BLUE]
        phase = BuyingResources(self._boards(order))

        inactive: dict[str, object] = {
            "is_active": False,
            "current_player": None,
            "remaining_players": [],
        }
        self.assertEqual(json.loads(phase.get_state()), inactive)

        phase.start_phase(order)
        started = json.loads(phase.get_state())
        self.assertTrue(started["is_active"])
        self.assertEqual(started["current_player"], "BLUE")
        self.assertEqual(started["remaining_players"], ["BLUE", "RED"])

        phase.buy_resources(PlayerColor.BLUE, [])
        mid = json.loads(phase.get_state())
        self.assertEqual(mid["current_player"], "RED")
        self.assertEqual(mid["remaining_players"], ["RED"])

        phase.buy_resources(PlayerColor.RED, [])
        self.assertEqual(json.loads(phase.get_state()), inactive)
