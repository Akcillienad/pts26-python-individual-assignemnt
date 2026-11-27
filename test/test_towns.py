# pylint: disable=too-many-public-methods
from __future__ import annotations

import json
import unittest
from collections.abc import Mapping, Sequence
from test.blue_test_fakes import (
    FakePlayerPowerPlants,
    FakePowerPlantMarket,
    FakeResourceMarket,
    FakeResourcePool,
)

from power_grid.building_houses import BuildingHouses
from power_grid.check_and_bump_step import CheckAndBumpStep
from power_grid.connections import Connections
from power_grid.player_board_facade import (
    PlayerBoardContext,
    PlayerBoardFacade,
)
from power_grid.player_money import PlayerMoney
from power_grid.power_plant import PowerPlant, PowerPlantNumber
from power_grid.simple_types import PhaseStatus, PlayerColor, RequestError
from power_grid.towns import Towns


def _line_connections() -> Connections:
    return Connections(
        [
            ("Alpha", "Beta", 5),
            ("Beta", "Gamma", 4),
            ("Alpha", "Gamma", 20),
            ("Gamma", "Delta", 7),
        ]
    )


class TestTowns(unittest.TestCase):
    def _snapshot(
        self,
        towns: Towns,
    ) -> tuple[dict[str, list[PlayerColor]], dict[PlayerColor, int], int, int]:
        return (
            towns.houses,
            {
                color: towns.get_number_of_houses(color)
                for color in PlayerColor
            },
            towns.get_max_number_of_houses(),
            towns.step,
        )

    def _assert_atomic_error(
        self,
        towns: Towns,
        player: PlayerColor,
        targets: Sequence[str],
        max_money: int,
    ) -> RequestError:
        before = self._snapshot(towns)
        result = towns.buy_houses(player, targets, max_money)
        self.assertIsInstance(result, RequestError)
        assert isinstance(result, RequestError)
        self.assertEqual(self._snapshot(towns), before)
        return result

    def test_init_valid_steps_and_initial_houses(self) -> None:
        conn = _line_connections()
        default_towns = Towns(["Alpha", "Beta"], conn)
        self.assertEqual(default_towns.step, 1)
        self.assertEqual(default_towns.houses, {"Alpha": [], "Beta": []})
        self.assertEqual(default_towns.get_max_number_of_houses(), 0)

        step2_towns = Towns(
            ["Alpha", "Beta"],
            conn,
            initial_houses={
                "Alpha": [PlayerColor.RED, PlayerColor.BLUE],
                "Beta": [],
            },
            step=2,
        )
        self.assertEqual(step2_towns.step, 2)
        self.assertEqual(
            step2_towns.houses,
            {"Alpha": [PlayerColor.RED, PlayerColor.BLUE], "Beta": []},
        )

        step3_towns = Towns(
            ["Alpha"],
            conn,
            initial_houses={
                "Alpha": [
                    PlayerColor.RED,
                    PlayerColor.BLUE,
                    PlayerColor.GREEN,
                ]
            },
            step=3,
        )
        self.assertEqual(step3_towns.step, 3)
        self.assertEqual(step3_towns.get_number_of_houses(PlayerColor.GREEN), 1)

    def test_init_rejects_invalid_step_values(self) -> None:
        conn = Connections([])
        for invalid_step in (0, 4, -1, True, False):
            with self.subTest(step=invalid_step):
                with self.assertRaises(ValueError):
                    Towns(["Alpha"], conn, step=invalid_step)

    def test_init_rejects_invalid_town_names(self) -> None:
        conn = Connections([])
        invalid_lists: list[list[str]] = [
            [],
            [""],
            ["Alpha", ""],
            ["Alpha", "Alpha"],
            ["   "],
            ["Alpha", " \t\n "],
        ]
        for names in invalid_lists:
            with self.subTest(town_names=names):
                with self.assertRaises(ValueError):
                    Towns(names, conn)

    def test_init_rejects_invalid_initial_houses(self) -> None:
        conn = _line_connections()
        invalid_cases: list[tuple[int, Mapping[str, Sequence[PlayerColor]]]] = [
            (1, {"Unknown": [PlayerColor.RED]}),
            (1, {"Alpha": [PlayerColor.RED, PlayerColor.BLUE]}),
            (2, {"Alpha": [PlayerColor.RED, PlayerColor.RED]}),
            (
                2,
                {
                    "Alpha": [
                        PlayerColor.RED,
                        PlayerColor.BLUE,
                        PlayerColor.GREEN,
                    ]
                },
            ),
            (
                3,
                {
                    "Alpha": [
                        PlayerColor.RED,
                        PlayerColor.BLUE,
                        PlayerColor.GREEN,
                        PlayerColor.YELLOW,
                    ]
                },
            ),
            (3, {"Alpha": [PlayerColor.BLUE, PlayerColor.RED, PlayerColor.BLUE]}),
        ]
        for step, initial in invalid_cases:
            with self.subTest(step=step, initial=initial):
                with self.assertRaises(ValueError):
                    Towns(["Alpha", "Beta"], conn, initial_houses=initial, step=step)

    def test_defensive_copies_for_inputs_and_houses_property(self) -> None:
        raw_names = ["Alpha", "Beta"]
        alpha_owners = [PlayerColor.RED]
        raw_initial: dict[str, list[PlayerColor]] = {"Alpha": alpha_owners}
        towns = Towns(raw_names, _line_connections(), initial_houses=raw_initial)

        raw_names.append("Gamma")
        alpha_owners.append(PlayerColor.BLUE)
        raw_initial["Beta"] = [PlayerColor.GREEN]
        self.assertEqual(towns.houses, {"Alpha": [PlayerColor.RED], "Beta": []})

        snapshot = towns.houses
        snapshot["Alpha"].append(PlayerColor.YELLOW)
        snapshot["Injected"] = [PlayerColor.BLACK]
        self.assertEqual(towns.houses, {"Alpha": [PlayerColor.RED], "Beta": []})

        request = ["Beta"]
        cost = towns.buy_houses(PlayerColor.RED, request, max_money=20)
        self.assertEqual(cost, 15)
        self.assertEqual(request, ["Beta"])

    def test_first_house_connecting_cost_is_zero_across_all_steps(self) -> None:
        conn = Connections([("Alpha", "Beta", 19)])
        step1 = Towns(["Alpha", "Beta"], conn, step=1)
        self.assertEqual(
            step1.buy_houses(PlayerColor.RED, ["Alpha"], max_money=10), 10
        )

        step2 = Towns(
            ["Alpha", "Beta"],
            conn,
            initial_houses={"Alpha": [PlayerColor.BLUE]},
            step=2,
        )
        self.assertEqual(
            step2.buy_houses(PlayerColor.RED, ["Alpha"], max_money=15), 15
        )

        step3 = Towns(
            ["Alpha", "Beta"],
            conn,
            initial_houses={"Alpha": [PlayerColor.BLUE, PlayerColor.GREEN]},
            step=3,
        )
        self.assertEqual(
            step3.buy_houses(PlayerColor.RED, ["Alpha"], max_money=20), 20
        )

    def test_empty_town_names_and_invalid_max_money(self) -> None:
        towns = Towns(["Alpha", "Beta"], _line_connections())

        self.assertEqual(towns.buy_houses(PlayerColor.RED, [], max_money=0), 0)
        self.assertEqual(towns.buy_houses(PlayerColor.RED, [], max_money=50), 0)
        self.assertEqual(towns.houses, {"Alpha": [], "Beta": []})

        for bad_money in (-1, -100, True, False):
            with self.subTest(max_money=bad_money, targets=[]):
                self._assert_atomic_error(
                    towns, PlayerColor.RED, [], bad_money
                )
            with self.subTest(max_money=bad_money, targets=["Alpha"]):
                self._assert_atomic_error(
                    towns, PlayerColor.RED, ["Alpha"], bad_money
                )

    def test_cheapest_indirect_path_through_opponent_occupied_active_city(
        self,
    ) -> None:
        conn = Connections(
            [
                ("Alpha", "Beta", 20),
                ("Alpha", "Mid", 3),
                ("Mid", "Beta", 4),
            ]
        )
        towns = Towns(
            ["Alpha", "Mid", "Beta"],
            conn,
            initial_houses={
                "Alpha": [PlayerColor.RED],
                "Mid": [PlayerColor.BLUE],
            },
            step=1,
        )
        # Mid is occupied by BLUE (cannot build there in Step 1),
        # but RED can still route through active city Mid for 3 + 4 = 7.
        cost = towns.buy_houses(PlayerColor.RED, ["Beta"], max_money=17)
        self.assertEqual(cost, 17)
        self.assertEqual(towns.houses["Beta"], [PlayerColor.RED])

    def test_inactive_region_cities_outside_town_names_cannot_be_traversed(
        self,
    ) -> None:
        full_board = Connections(
            [
                ("Alpha", "InactiveCity", 5),
                ("InactiveCity", "Beta", 5),
                ("Alpha", "Beta", 20),
            ]
        )
        # Active playable zone contains ONLY Alpha and Beta;
        # InactiveCity is in an unselected map region.
        towns = Towns(
            ["Alpha", "Beta"],
            full_board,
            initial_houses={"Alpha": [PlayerColor.RED]},
        )
        cost = towns.buy_houses(PlayerColor.RED, ["Beta"], max_money=50)
        self.assertEqual(cost, 30)

        # When InactiveCity is the ONLY bridge between Alpha and Beta,
        # Beta must be unreachable within active playable regions.
        bridge_only = Connections(
            [
                ("Alpha", "InactiveCity", 5),
                ("InactiveCity", "Beta", 5),
            ]
        )
        isolated = Towns(
            ["Alpha", "Beta"],
            bridge_only,
            initial_houses={"Alpha": [PlayerColor.RED]},
        )
        self._assert_atomic_error(
            isolated, PlayerColor.RED, ["Beta"], 50
        )
        # Even on first turn, buying two cities bridged only by an inactive city fails.
        self._assert_atomic_error(
            isolated, PlayerColor.BLUE, ["Alpha", "Beta"], 50
        )

    def test_active_indirect_path_chosen_while_cheaper_inactive_ignored(
        self,
    ) -> None:
        board = Connections(
            [
                ("Alpha", "InactiveShortcut", 1),
                ("InactiveShortcut", "Beta", 1),
                ("Alpha", "ActiveMid", 4),
                ("ActiveMid", "Beta", 4),
                ("Alpha", "Beta", 20),
            ]
        )
        towns = Towns(
            ["Alpha", "ActiveMid", "Beta"],
            board,
            initial_houses={
                "Alpha": [PlayerColor.RED],
                "ActiveMid": [PlayerColor.BLUE],
            },
        )
        # Must ignore InactiveShortcut (cost 2) and pick ActiveMid (cost 8)
        # over direct edge (cost 20): 10 slot + 8 connecting = 18.
        cost = towns.buy_houses(PlayerColor.RED, ["Beta"], max_money=18)
        self.assertEqual(cost, 18)

    def test_single_town_map_with_empty_connections(self) -> None:
        towns = Towns(["OnlyTown"], Connections([]), step=1)
        self.assertEqual(
            towns.buy_houses(PlayerColor.RED, ["OnlyTown"], max_money=10), 10
        )
        self._assert_atomic_error(towns, PlayerColor.BLUE, ["OnlyTown"], 50)

        towns.start_step2()
        self.assertEqual(
            towns.buy_houses(PlayerColor.BLUE, ["OnlyTown"], max_money=15), 15
        )
        towns.start_step3()
        self.assertEqual(
            towns.buy_houses(PlayerColor.GREEN, ["OnlyTown"], max_money=20), 20
        )
        self._assert_atomic_error(towns, PlayerColor.YELLOW, ["OnlyTown"], 50)

    def test_zero_cost_connection_and_multi_city_first_turn(self) -> None:
        conn = Connections(
            [
                ("Duisburg", "Essen", 0),
                ("Essen", "Dortmund", 4),
            ]
        )
        towns = Towns(["Duisburg", "Essen", "Dortmund"], conn)
        self.assertEqual(
            towns.buy_houses(PlayerColor.RED, ["Duisburg"], max_money=10), 10
        )
        # Duisburg -> Essen has 0 connecting cost, so only slot cost 10 applies.
        self.assertEqual(
            towns.buy_houses(PlayerColor.RED, ["Essen"], max_money=10), 10
        )

        fresh = Towns(["Duisburg", "Essen", "Dortmund"], conn)
        self.assertEqual(
            fresh.buy_houses(
                PlayerColor.BLUE,
                ("Dortmund", "Duisburg", "Essen"),
                max_money=34,
            ),
            34,
        )
        self.assertEqual(fresh.get_number_of_houses(PlayerColor.BLUE), 3)

    def test_multi_city_purchase_order_independence(self) -> None:
        conn = _line_connections()
        towns_bc = Towns(
            ["Alpha", "Beta", "Gamma"],
            conn,
            initial_houses={"Alpha": [PlayerColor.RED]},
        )
        towns_cb = Towns(
            ["Alpha", "Beta", "Gamma"],
            conn,
            initial_houses={"Alpha": [PlayerColor.RED]},
        )

        cost_bc = towns_bc.buy_houses(
            PlayerColor.RED, ["Beta", "Gamma"], max_money=50
        )
        cost_cb = towns_cb.buy_houses(
            PlayerColor.RED, ["Gamma", "Beta"], max_money=50
        )
        # Connecting: 5 + 4 = 9; Building: 10 + 10 = 20 -> Total = 29
        self.assertEqual(cost_bc, 29)
        self.assertEqual(cost_cb, 29)

    def test_unowned_intermediate_hub_not_shared_for_free(self) -> None:
        conn = Connections(
            [
                ("Root", "Hub", 10),
                ("Hub", "LeafB", 2),
                ("Hub", "LeafC", 2),
            ]
        )
        towns = Towns(
            ["Root", "Hub", "LeafB", "LeafC"],
            conn,
            initial_houses={"Root": [PlayerColor.RED]},
        )
        # Root->LeafB is 12, then LeafB->LeafC via Hub is 4 => connecting 16,
        # building 10 + 10 = 20 => total 36.
        cost = towns.buy_houses(
            PlayerColor.RED, ["LeafB", "LeafC"], max_money=36
        )
        self.assertEqual(cost, 36)

    def test_mixed_slot_costs_in_step2_and_step3(self) -> None:
        conn = Connections(
            [
                ("CityA", "CityB", 4),
                ("CityB", "CityC", 3),
                ("CityC", "CityD", 6),
            ]
        )
        towns = Towns(
            ["CityA", "CityB", "CityC", "CityD"],
            conn,
            initial_houses={
                "CityA": [PlayerColor.RED],
                "CityB": [PlayerColor.BLUE],
                "CityC": [PlayerColor.BLUE, PlayerColor.GREEN],
                "CityD": [],
            },
            step=3,
        )
        # RED owns CityA and buys CityB (slot 15), CityC (slot 20), CityD (slot 10).
        # Building: 15 + 20 + 10 = 45; Connecting: 4 + 3 + 6 = 13; Total: 58.
        cost = towns.buy_houses(
            PlayerColor.RED, ["CityD", "CityB", "CityC"], max_money=58
        )
        self.assertEqual(cost, 58)
        self.assertEqual(towns.get_number_of_houses(PlayerColor.RED), 4)
        self.assertEqual(
            towns.houses["CityC"],
            [PlayerColor.BLUE, PlayerColor.GREEN, PlayerColor.RED],
        )

    def test_branching_network_and_parallel_edges(self) -> None:
        conn = Connections(
            [
                ("West", "WestOutpost", 15),
                ("West", "WestOutpost", 3),
                ("East", "EastOutpost", 5),
                ("West", "East", 100),
            ]
        )
        towns = Towns(
            ["West", "East", "WestOutpost", "EastOutpost"],
            conn,
            initial_houses={
                "West": [PlayerColor.RED],
                "East": [PlayerColor.RED],
            },
        )
        # Picks cheapest parallel edge (3) from West and branch (5) from East:
        # connecting = 8, building = 20 -> total = 28.
        cost = towns.buy_houses(
            PlayerColor.RED, ["EastOutpost", "WestOutpost"], max_money=28
        )
        self.assertEqual(cost, 28)

    def test_step_slot_limits_and_progression(self) -> None:
        conn = Connections([("Solo", "Neighbor", 5)])
        towns = Towns(["Solo", "Neighbor"], conn, step=1)

        # Step 1: 1st house succeeds (10), 2nd rejected atomically
        self.assertEqual(
            towns.buy_houses(PlayerColor.RED, ["Solo"], max_money=10), 10
        )
        self._assert_atomic_error(towns, PlayerColor.BLUE, ["Solo"], 50)

        # Step 2: 2nd house succeeds (15), 3rd rejected atomically
        towns.start_step2()
        self.assertEqual(towns.step, 2)
        self.assertEqual(
            towns.buy_houses(PlayerColor.BLUE, ["Solo"], max_money=15), 15
        )
        self._assert_atomic_error(towns, PlayerColor.GREEN, ["Solo"], 50)

        # Step 3: 3rd house succeeds (20), 4th rejected atomically
        towns.start_step3()
        self.assertEqual(towns.step, 3)
        self.assertEqual(
            towns.buy_houses(PlayerColor.GREEN, ["Solo"], max_money=20), 20
        )
        self._assert_atomic_error(towns, PlayerColor.YELLOW, ["Solo"], 50)
        self.assertEqual(
            towns.houses["Solo"],
            [PlayerColor.RED, PlayerColor.BLUE, PlayerColor.GREEN],
        )

    def test_error_cases_are_strictly_atomic(self) -> None:
        conn = Connections(
            [
                ("Alpha", "Beta", 5),
                ("IslandA", "IslandB", 4),
            ]
        )
        towns = Towns(
            ["Alpha", "Beta", "IslandA", "IslandB"],
            conn,
            initial_houses={"Alpha": [PlayerColor.RED]},
            step=2,
        )

        # Unknown town (single and mixed with valid town)
        self._assert_atomic_error(towns, PlayerColor.RED, ["Unknown"], 100)
        self._assert_atomic_error(
            towns, PlayerColor.RED, ["Beta", "Unknown"], 100
        )

        # Duplicate town in same request
        self._assert_atomic_error(
            towns, PlayerColor.RED, ["Beta", "Beta"], 100
        )

        # Player already owns house in target (even in Step 2 with free slot!)
        self._assert_atomic_error(towns, PlayerColor.RED, ["Alpha"], 100)
        self._assert_atomic_error(
            towns, PlayerColor.RED, ["Beta", "Alpha"], 100
        )

        # Disconnected/unreachable town (single, mixed, and first-turn split)
        self._assert_atomic_error(towns, PlayerColor.RED, ["IslandA"], 100)
        self._assert_atomic_error(
            towns, PlayerColor.RED, ["Beta", "IslandA"], 100
        )
        self._assert_atomic_error(
            towns, PlayerColor.BLUE, ["Beta", "IslandA"], 100
        )

        # Insufficient money boundary (cost of Beta from Alpha = 10 + 5 = 15)
        self._assert_atomic_error(towns, PlayerColor.RED, ["Beta"], 14)
        self._assert_atomic_error(towns, PlayerColor.BLUE, ["Beta"], 0)

        # Exact budget succeeds after all rejected attempts
        self.assertEqual(
            towns.buy_houses(PlayerColor.RED, ["Beta"], max_money=15), 15
        )
        self.assertEqual(towns.get_number_of_houses(PlayerColor.RED), 2)

    def test_house_counts_and_max_with_ties(self) -> None:
        conn = _line_connections()
        towns = Towns(["Alpha", "Beta", "Gamma", "Delta"], conn, step=2)

        self.assertEqual(towns.get_number_of_houses(PlayerColor.RED), 0)
        self.assertEqual(towns.get_max_number_of_houses(), 0)

        self.assertEqual(
            towns.buy_houses(PlayerColor.RED, ["Alpha", "Beta"], max_money=50),
            25,
        )
        self.assertEqual(towns.get_number_of_houses(PlayerColor.RED), 2)
        self.assertEqual(towns.get_number_of_houses(PlayerColor.BLUE), 0)
        self.assertEqual(towns.get_max_number_of_houses(), 2)

        # Tie at 2 houses each
        self.assertEqual(
            towns.buy_houses(
                PlayerColor.BLUE, ["Gamma", "Delta"], max_money=50
            ),
            27,
        )
        self.assertEqual(towns.get_number_of_houses(PlayerColor.BLUE), 2)
        self.assertEqual(towns.get_max_number_of_houses(), 2)

        # BLUE takes solo lead with 3 houses (shares Beta in Step 2)
        self.assertEqual(
            towns.buy_houses(PlayerColor.BLUE, ["Beta"], max_money=50), 19
        )
        self.assertEqual(towns.get_number_of_houses(PlayerColor.BLUE), 3)
        self.assertEqual(towns.get_max_number_of_houses(), 3)

    def test_step_transition_errors_and_direct_step1_to_step3(self) -> None:
        conn = Connections([])
        towns_seq = Towns(["Alpha"], conn, step=1)
        towns_seq.start_step2()
        with self.assertRaises(ValueError):
            towns_seq.start_step2()
        self.assertEqual(towns_seq.step, 2)

        towns_seq.start_step3()
        self.assertEqual(towns_seq.step, 3)
        with self.assertRaises(ValueError):
            towns_seq.start_step2()
        with self.assertRaises(ValueError):
            towns_seq.start_step3()
        self.assertEqual(towns_seq.step, 3)

        # Direct Step 1 -> Step 3 jump
        towns_jump = Towns(["Alpha"], conn, step=1)
        towns_jump.start_step3()
        self.assertEqual(towns_jump.step, 3)
        with self.assertRaises(ValueError):
            towns_jump.start_step2()
        with self.assertRaises(ValueError):
            towns_jump.start_step3()

    def test_to_string_returns_accurate_json(self) -> None:
        towns = Towns(["Alpha", "Beta"], _line_connections())
        initial_json = json.loads(towns.to_string())
        self.assertEqual(
            initial_json,
            {"step": 1, "houses": {"Alpha": [], "Beta": []}},
        )

        self.assertEqual(
            towns.buy_houses(PlayerColor.RED, ["Alpha"], max_money=10), 10
        )
        towns.start_step2()
        self.assertEqual(
            towns.buy_houses(PlayerColor.BLUE, ["Alpha", "Beta"], max_money=30),
            30,
        )
        updated_json = json.loads(towns.to_string())
        self.assertEqual(
            updated_json,
            {
                "step": 2,
                "houses": {
                    "Alpha": ["RED", "BLUE"],
                    "Beta": ["BLUE"],
                },
            },
        )

    def test_sociable_integration_with_check_and_bump_step(self) -> None:
        names = [f"City{idx}" for idx in range(7)]
        edges = [(names[idx], names[idx + 1], 1) for idx in range(6)]
        towns = Towns(names, Connections(edges))
        stepper = CheckAndBumpStep(3, [towns])

        self.assertEqual(
            towns.buy_houses(PlayerColor.RED, names[:6], max_money=100), 65
        )
        self.assertFalse(
            stepper.check_and_bump_to_step2(
                [towns.get_number_of_houses(PlayerColor.RED)]
            )
        )
        self.assertEqual(towns.step, 1)

        self.assertEqual(
            towns.buy_houses(PlayerColor.RED, [names[6]], max_money=20), 11
        )
        self.assertTrue(
            stepper.check_and_bump_to_step2(
                [towns.get_number_of_houses(PlayerColor.RED)]
            )
        )
        self.assertEqual(towns.step, 2)
        self.assertEqual(
            towns.buy_houses(PlayerColor.BLUE, [names[0]], max_money=15), 15
        )

        # Direct Step 1 -> Step 3 jump via CheckAndBumpStep
        jump_towns = Towns(
            ["Hub"],
            Connections([]),
            initial_houses={"Hub": [PlayerColor.RED]},
        )
        jump_stepper = CheckAndBumpStep(3, [jump_towns])
        self.assertTrue(jump_stepper.check_and_bump_to_step3(True))
        self.assertEqual(jump_towns.step, 3)
        self.assertEqual(
            jump_towns.buy_houses(PlayerColor.BLUE, ["Hub"], max_money=15), 15
        )
        self.assertEqual(
            jump_towns.buy_houses(PlayerColor.GREEN, ["Hub"], max_money=20), 20
        )

    def test_sociable_integration_with_building_houses_and_player_board(
        self,
    ) -> None:
        towns = Towns(["Alpha", "Beta", "Gamma"], _line_connections())
        plant_market = FakePowerPlantMarket()
        context = PlayerBoardContext(
            FakeResourceMarket(), FakeResourcePool(), towns
        )
        red_board = PlayerBoardFacade(
            PlayerMoney(PlayerColor.RED, 50),
            FakePlayerPowerPlants(
                [PowerPlant(PowerPlantNumber(13), [], 0, 4)]
            ),
            context,
        )
        blue_board = PlayerBoardFacade(
            PlayerMoney(PlayerColor.BLUE, 50),
            FakePlayerPowerPlants(
                [PowerPlant(PowerPlantNumber(25), [], 0, 4)]
            ),
            context,
        )
        boards = {PlayerColor.RED: red_board, PlayerColor.BLUE: blue_board}
        phase = BuildingHouses(
            towns, plant_market, boards, end_game_town_count=2
        )

        # Reverse order: BLUE builds first, then RED
        phase.start_phase([PlayerColor.RED, PlayerColor.BLUE])
        self.assertEqual(
            phase.buy_houses(PlayerColor.BLUE, ["Alpha"]),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(blue_board.outstanding_money(), 40)

        # RED cannot take Alpha in Step 1 -> error, money and turn preserved
        self.assertIsInstance(
            phase.buy_houses(PlayerColor.RED, ["Alpha"]), RequestError
        )
        self.assertEqual(red_board.outstanding_money(), 50)
        self.assertEqual(phase.current_player, PlayerColor.RED)

        # RED buys Beta + Gamma (10 + 10 + 4 = 24) -> hits end_game_town_count=2
        self.assertEqual(
            phase.buy_houses(PlayerColor.RED, ["Beta", "Gamma"]),
            PhaseStatus.GAME_ENDS,
        )
        self.assertEqual(red_board.outstanding_money(), 26)
        self.assertEqual(plant_market.removed_thresholds, [1, 2])

        # PlayerBoardFacade caps Bureaucracy payout to real Towns house count:
        # RED owns 2 houses (plant cap 4) -> PAYMENT_TABLE[2] = 33
        self.assertIsNone(
            red_board.use_power_plants([PowerPlantNumber(13)], [])
        )
        self.assertEqual(red_board.outstanding_money(), 59)
        # BLUE owns 1 house (plant cap 4) -> PAYMENT_TABLE[1] = 22
        self.assertIsNone(
            blue_board.use_power_plants([PowerPlantNumber(25)], [])
        )
        self.assertEqual(blue_board.outstanding_money(), 62)
