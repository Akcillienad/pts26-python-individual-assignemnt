# pylint: disable=too-many-public-methods
from __future__ import annotations

import unittest
from collections.abc import Sequence

from power_grid.power_grid_game_adapter import (
    RESOURCE_CODE_MAP,
    PowerGridGameAdapter,
)
from power_grid.power_plant import PowerPlantNumber
from power_grid.simple_types import (
    PlayerColor,
    RequestError,
    Resource,
    SerializedGameState,
)


class SpyGameController:
    def __init__(self, state: str = '{"ok": true}') -> None:
        self.calls: list[tuple[str, object]] = []
        self.next_error: RequestError | None = None
        self.state_text = state
        self.get_state_calls = 0

    def select_power_plant_to_bid(
        self,
        player: PlayerColor,
        ppn: PowerPlantNumber,
        first_bid: int,
    ) -> RequestError | None:
        self.calls.append(("select", (player, ppn.number, first_bid)))
        return self.next_error

    def do_not_want_power_plant(
        self,
        player: PlayerColor,
    ) -> RequestError | None:
        self.calls.append(("pass_select", player))
        return self.next_error

    def bid_for_current_power_plant(
        self,
        player: PlayerColor,
        bid: int,
    ) -> RequestError | None:
        self.calls.append(("bid", (player, bid)))
        return self.next_error

    def do_not_bid_for_current_power_plant(
        self,
        player: PlayerColor,
    ) -> RequestError | None:
        self.calls.append(("pass_bid", player))
        return self.next_error

    def remove_power_plant(
        self,
        player: PlayerColor,
        ppn: PowerPlantNumber,
        removed_resources: Sequence[Resource],
    ) -> RequestError | None:
        self.calls.append(
            ("remove", (player, ppn.number, list(removed_resources)))
        )
        return self.next_error

    def buy_resources(
        self,
        player: PlayerColor,
        resources: Sequence[Resource],
    ) -> RequestError | None:
        self.calls.append(("buy_resources", (player, list(resources))))
        return self.next_error

    def buy_houses(
        self,
        player: PlayerColor,
        town_names: Sequence[str],
    ) -> RequestError | None:
        if isinstance(town_names, list):
            town_names.append("MUTATED")
        self.calls.append(("buy_houses", (player, list(town_names))))
        return self.next_error

    def use_power_plants(
        self,
        player: PlayerColor,
        ppns: Sequence[PowerPlantNumber],
        resources_to_burn: Sequence[Resource],
    ) -> RequestError | None:
        self.calls.append(
            (
                "use",
                (player, [ppn.number for ppn in ppns], list(resources_to_burn)),
            )
        )
        return self.next_error

    def get_state(self) -> str:
        self.get_state_calls += 1
        return self.state_text


class TestPowerGridGameAdapter(unittest.TestCase):
    def test_resource_code_map_and_init_validation(self) -> None:
        self.assertEqual(
            RESOURCE_CODE_MAP,
            {
                "C": Resource.COAL,
                "O": Resource.OIL,
                "G": Resource.GARBAGE,
                "U": Resource.URANIUM,
            },
        )
        spy = SpyGameController()
        with self.assertRaises(ValueError):
            PowerGridGameAdapter(spy, {})
        with self.assertRaises(ValueError):
            PowerGridGameAdapter(
                spy, {1: PlayerColor.RED, 2: PlayerColor.RED}
            )

        custom = {10: PlayerColor.GREEN, 20: PlayerColor.PURPLE}
        adapter = PowerGridGameAdapter(spy, custom)
        custom[30] = PlayerColor.BLACK
        self.assertIsInstance(
            adapter.do_not_want_power_plant(30), RequestError
        )
        self.assertIsInstance(
            adapter.do_not_want_power_plant(10), SerializedGameState
        )
        self.assertEqual(spy.calls, [("pass_select", PlayerColor.GREEN)])

    def test_all_eight_methods_wrap_serialized_state_on_success(self) -> None:
        spy = SpyGameController('{"turn": 1}')
        adapter = PowerGridGameAdapter(spy)

        res1 = adapter.select_power_plant_to_bid(1, 4, 5)
        res2 = adapter.do_not_want_power_plant(2)
        res3 = adapter.bid_for_current_power_plant(3, 6)
        res4 = adapter.do_not_bid_for_current_power_plant(4)
        res5 = adapter.remove_power_plant(5, 7, "CO")
        res6 = adapter.buy_resources(6, "GUCC")
        towns_input = ["Berlin", "Hamburg"]
        res7 = adapter.buy_houses(1, towns_input)
        ppns_input = [3, 13]
        res8 = adapter.use_power_plants(2, ppns_input, "COGU")

        expected_state = SerializedGameState('{"turn": 1}')
        for result in (res1, res2, res3, res4, res5, res6, res7, res8):
            self.assertEqual(result, expected_state)
        self.assertEqual(spy.get_state_calls, 8)
        # Input lists must not be mutated
        self.assertEqual(towns_input, ["Berlin", "Hamburg"])
        self.assertEqual(ppns_input, [3, 13])

        self.assertEqual(spy.calls[0], ("select", (PlayerColor.RED, 4, 5)))
        self.assertEqual(spy.calls[1], ("pass_select", PlayerColor.YELLOW))
        self.assertEqual(spy.calls[2], ("bid", (PlayerColor.BLUE, 6)))
        self.assertEqual(spy.calls[3], ("pass_bid", PlayerColor.GREEN))
        self.assertEqual(
            spy.calls[4],
            ("remove", (PlayerColor.PURPLE, 7, [Resource.COAL, Resource.OIL])),
        )
        self.assertEqual(
            spy.calls[5],
            (
                "buy_resources",
                (
                    PlayerColor.BLACK,
                    [
                        Resource.GARBAGE,
                        Resource.URANIUM,
                        Resource.COAL,
                        Resource.COAL,
                    ],
                ),
            ),
        )
        self.assertEqual(
            spy.calls[7],
            (
                "use",
                (
                    PlayerColor.YELLOW,
                    [3, 13],
                    [
                        Resource.COAL,
                        Resource.OIL,
                        Resource.GARBAGE,
                        Resource.URANIUM,
                    ],
                ),
            ),
        )

    def test_empty_resource_strings_and_empty_sequences_allowed(self) -> None:
        spy = SpyGameController()
        adapter = PowerGridGameAdapter(spy)

        self.assertIsInstance(
            adapter.remove_power_plant(1, 3, ""), SerializedGameState
        )
        self.assertIsInstance(
            adapter.buy_resources(1, ""), SerializedGameState
        )
        self.assertIsInstance(adapter.buy_houses(1, []), SerializedGameState)
        self.assertIsInstance(
            adapter.use_power_plants(1, [], ""), SerializedGameState
        )
        self.assertEqual(spy.calls[0], ("remove", (PlayerColor.RED, 3, [])))
        self.assertEqual(spy.calls[1], ("buy_resources", (PlayerColor.RED, [])))
        self.assertEqual(spy.calls[3], ("use", (PlayerColor.RED, [], [])))

    def test_controller_error_propagates_without_get_state(self) -> None:
        spy = SpyGameController()
        spy.next_error = RequestError("Wrong phase")
        adapter = PowerGridGameAdapter(spy)

        result = adapter.buy_resources(1, "C")
        self.assertEqual(result, RequestError("Wrong phase"))
        self.assertEqual(spy.get_state_calls, 0)

    def test_invalid_resource_codes_rejected(self) -> None:
        spy = SpyGameController()
        adapter = PowerGridGameAdapter(spy)

        bad_codes = ["c", "o", "g", "u", " ", " C", "C ", "C O", "X", "C1", "\n"]
        for bad in bad_codes:
            self.assertIsInstance(
                adapter.buy_resources(1, bad), RequestError, f"code={bad!r}"
            )
            self.assertIsInstance(
                adapter.remove_power_plant(1, 3, bad), RequestError
            )
            self.assertIsInstance(
                adapter.use_power_plants(1, [3], bad), RequestError
            )
        self.assertEqual(spy.calls, [])
        self.assertEqual(spy.get_state_calls, 0)

    def test_unknown_player_id_rejected_on_all_methods(self) -> None:
        spy = SpyGameController()
        adapter = PowerGridGameAdapter(spy)

        for bad_id in (0, -1, 7, 99):
            self.assertIsInstance(
                adapter.select_power_plant_to_bid(bad_id, 3, 3), RequestError
            )
            self.assertIsInstance(
                adapter.do_not_want_power_plant(bad_id), RequestError
            )
            self.assertIsInstance(
                adapter.bid_for_current_power_plant(bad_id, 4), RequestError
            )
            self.assertIsInstance(
                adapter.do_not_bid_for_current_power_plant(bad_id),
                RequestError,
            )
            self.assertIsInstance(
                adapter.remove_power_plant(bad_id, 3, ""), RequestError
            )
            self.assertIsInstance(
                adapter.buy_resources(bad_id, ""), RequestError
            )
            self.assertIsInstance(adapter.buy_houses(bad_id, []), RequestError)
            self.assertIsInstance(
                adapter.use_power_plants(bad_id, [], ""), RequestError
            )
        self.assertEqual(spy.calls, [])

    def test_non_positive_power_plant_numbers_rejected(self) -> None:
        spy = SpyGameController()
        adapter = PowerGridGameAdapter(spy)

        for bad_num in (0, -1, -10):
            self.assertIsInstance(
                adapter.select_power_plant_to_bid(1, bad_num, 5), RequestError
            )
            self.assertIsInstance(
                adapter.remove_power_plant(1, bad_num, ""), RequestError
            )
            self.assertIsInstance(
                adapter.use_power_plants(1, [3, bad_num, 7], ""), RequestError
            )
        self.assertEqual(spy.calls, [])

    def test_non_positive_bids_rejected(self) -> None:
        # D3: Zero or negative bids must be rejected with RequestError
        spy = SpyGameController()
        adapter = PowerGridGameAdapter(spy)

        self.assertIsInstance(
            adapter.select_power_plant_to_bid(1, 3, 0), RequestError
        )
        self.assertIsInstance(
            adapter.select_power_plant_to_bid(1, 3, -5), RequestError
        )
        self.assertIsInstance(
            adapter.bid_for_current_power_plant(1, 0), RequestError
        )
        self.assertIsInstance(
            adapter.bid_for_current_power_plant(1, -2), RequestError
        )
        self.assertEqual(spy.calls, [])

    def test_boolean_rejected_for_player_id_and_plant_number(self) -> None:
        # D6: bool subclasses int in Python; True/False must not act as IDs
        spy = SpyGameController()
        adapter = PowerGridGameAdapter(
            spy, {0: PlayerColor.RED, 1: PlayerColor.BLUE}
        )

        self.assertIsInstance(
            adapter.do_not_want_power_plant(True), RequestError
        )
        self.assertIsInstance(
            adapter.do_not_want_power_plant(False), RequestError
        )
        self.assertIsInstance(
            adapter.select_power_plant_to_bid(1, True, 5), RequestError
        )
        self.assertIsInstance(
            adapter.remove_power_plant(1, True, ""), RequestError
        )
        self.assertIsInstance(
            adapter.remove_power_plant(1, False, ""), RequestError
        )
        self.assertIsInstance(
            adapter.use_power_plants(1, [True], ""), RequestError
        )
        self.assertIsInstance(
            adapter.use_power_plants(1, [3, False, 7], ""), RequestError
        )
        self.assertEqual(spy.calls, [])

    def test_boolean_bids_rejected_and_min_valid_bid_accepted(self) -> None:
        spy = SpyGameController()
        adapter = PowerGridGameAdapter(spy)

        for bool_bid in (True, False):
            self.assertIsInstance(
                adapter.select_power_plant_to_bid(1, 3, bool_bid),
                RequestError,
            )
            self.assertIsInstance(
                adapter.bid_for_current_power_plant(1, bool_bid),
                RequestError,
            )
        self.assertEqual(spy.calls, [])

        # Discounted minimum bid of 1 must be accepted
        self.assertIsInstance(
            adapter.select_power_plant_to_bid(1, 3, 1), SerializedGameState
        )
        self.assertIsInstance(
            adapter.bid_for_current_power_plant(1, 1), SerializedGameState
        )
        self.assertEqual(
            spy.calls,
            [
                ("select", (PlayerColor.RED, 3, 1)),
                ("bid", (PlayerColor.RED, 1)),
            ],
        )

    def test_zero_key_mapping_and_combined_invalid_inputs(self) -> None:
        spy = SpyGameController()
        adapter = PowerGridGameAdapter(
            spy, {0: PlayerColor.RED, 1: PlayerColor.BLUE}
        )

        # Integer 0 succeeds while bool False fails
        self.assertIsInstance(
            adapter.do_not_want_power_plant(0), SerializedGameState
        )
        self.assertIsInstance(
            adapter.buy_houses(0, []), SerializedGameState
        )
        self.assertIsInstance(
            adapter.do_not_want_power_plant(False), RequestError
        )
        self.assertEqual(
            spy.calls,
            [
                ("pass_select", PlayerColor.RED),
                ("buy_houses", (PlayerColor.RED, ["MUTATED"])),
            ],
        )

        # Unknown player_id combined with invalid resource code
        calls_before = len(spy.calls)
        err_rm = adapter.remove_power_plant(99, 3, "X")
        err_buy = adapter.buy_resources(99, "bad")
        err_use = adapter.use_power_plants(99, [3], "z")
        for err in (err_rm, err_buy, err_use):
            self.assertIsInstance(err, RequestError)
            assert isinstance(err, RequestError)
            self.assertIn("99", err.description)
        self.assertEqual(len(spy.calls), calls_before)
