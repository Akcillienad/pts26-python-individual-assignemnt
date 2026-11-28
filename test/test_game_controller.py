# pylint: disable=too-many-public-methods
from __future__ import annotations

import json
import unittest
from collections.abc import Sequence
from dataclasses import dataclass
from test.blue_test_fakes import (
    FakeAuctionPhase,
    FakePowerPlantMarket,
    FakeResourceMarket,
    FakeTowns,
    SimplePlayerBoardFake,
)

from power_grid.check_and_bump_step import CheckAndBumpStep
from power_grid.game_controller import (
    GameBoardComponents,
    GameController,
    GamePhases,
)
from power_grid.power_plant import PowerPlantNumber
from power_grid.simple_types import (
    GamePhase,
    PhaseStatus,
    PlayerColor,
    RequestError,
    Resource,
)


class StubBuyingPhase:
    def __init__(self, state_str: str = '{"phase": "buy_res"}') -> None:
        self.started_orders: list[list[PlayerColor]] = []
        self.calls: list[tuple[PlayerColor, list[Resource]]] = []
        self.next_result: PhaseStatus | RequestError = (
            PhaseStatus.PHASE_CONTINUES
        )
        self.state_str = state_str

    def start_phase(self, player_order: Sequence[PlayerColor]) -> None:
        self.started_orders.append(list(player_order))

    def buy_resources(
        self,
        player: PlayerColor,
        resources: Sequence[Resource],
    ) -> PhaseStatus | RequestError:
        self.calls.append((player, list(resources)))
        return self.next_result

    def get_state(self) -> str:
        return self.state_str


class StubHousesPhase:
    def __init__(self, state_str: str = '{"phase": "houses"}') -> None:
        self.started_orders: list[list[PlayerColor]] = []
        self.calls: list[tuple[PlayerColor, list[str]]] = []
        self.next_result: PhaseStatus | RequestError = (
            PhaseStatus.PHASE_CONTINUES
        )
        self.state_str = state_str

    def start_phase(self, player_order: Sequence[PlayerColor]) -> None:
        self.started_orders.append(list(player_order))

    def buy_houses(
        self,
        player: PlayerColor,
        town_names: Sequence[str],
    ) -> PhaseStatus | RequestError:
        self.calls.append((player, list(town_names)))
        return self.next_result

    def get_state(self) -> str:
        return self.state_str


class StubBureaucracyPhase:
    def __init__(self, state_str: str = '{"phase": "bureaucracy"}') -> None:
        self.started_orders: list[list[PlayerColor]] = []
        self.calls: list[tuple[PlayerColor, list[int], list[Resource]]] = []
        self.next_result: PhaseStatus | RequestError = (
            PhaseStatus.PHASE_CONTINUES
        )
        self.state_str = state_str

    def start_phase(self, player_order: Sequence[PlayerColor]) -> None:
        self.started_orders.append(list(player_order))

    def use_power_plants(
        self,
        player: PlayerColor,
        ppns: Sequence[PowerPlantNumber],
        resources_to_burn: Sequence[Resource],
    ) -> PhaseStatus | RequestError:
        self.calls.append(
            (player, [ppn.number for ppn in ppns], list(resources_to_burn))
        )
        return self.next_result

    def get_state(self) -> str:
        return self.state_str


@dataclass
class PhaseStubs:
    auction: FakeAuctionPhase
    buying: StubBuyingPhase
    houses: StubHousesPhase
    bureaucracy: StubBureaucracyPhase


@dataclass
class BoardStubs:
    plant_market: FakePowerPlantMarket
    resource_market: FakeResourceMarket
    towns: FakeTowns
    step_bumper: CheckAndBumpStep


@dataclass
class ControllerHarness:
    controller: GameController
    boards: dict[PlayerColor, SimplePlayerBoardFake]
    phases: PhaseStubs
    board: BoardStubs


def _build_harness(
    order: Sequence[PlayerColor] = (PlayerColor.RED, PlayerColor.BLUE),
    auction: FakeAuctionPhase | None = None,
) -> ControllerHarness:
    boards = {color: SimplePlayerBoardFake(color) for color in order}
    phase_stubs = PhaseStubs(
        auction=auction if auction is not None else FakeAuctionPhase(),
        buying=StubBuyingPhase(),
        houses=StubHousesPhase(),
        bureaucracy=StubBureaucracyPhase(),
    )
    plant_market = FakePowerPlantMarket()
    towns = FakeTowns()
    board_stubs = BoardStubs(
        plant_market=plant_market,
        resource_market=FakeResourceMarket(),
        towns=towns,
        step_bumper=CheckAndBumpStep(len(order), [plant_market, towns]),
    )
    controller = GameController(
        order,
        boards,
        GamePhases(
            phase_stubs.auction,
            phase_stubs.buying,
            phase_stubs.houses,
            phase_stubs.bureaucracy,
        ),
        GameBoardComponents(
            board_stubs.plant_market,
            board_stubs.resource_market,
            board_stubs.towns,
            board_stubs.step_bumper,
        ),
    )
    return ControllerHarness(
        controller=controller,
        boards=boards,
        phases=phase_stubs,
        board=board_stubs,
    )


class TestGameController(unittest.TestCase):
    def test_init_validation_and_starting_state(self) -> None:
        harness = _build_harness([PlayerColor.RED, PlayerColor.BLUE])
        ctrl = harness.controller
        self.assertTrue(ctrl.is_first_turn)
        self.assertEqual(ctrl.game_phase, GamePhase.AUCTION_POWER_PLANTS)
        self.assertEqual(
            ctrl.player_order, [PlayerColor.RED, PlayerColor.BLUE]
        )
        self.assertEqual(ctrl.game_result, [])
        self.assertEqual(
            harness.phases.auction.started_orders,
            [[PlayerColor.RED, PlayerColor.BLUE]],
        )

        # Invalid player counts and mismatched mappings
        phases = GamePhases(
            FakeAuctionPhase(),
            StubBuyingPhase(),
            StubHousesPhase(),
            StubBureaucracyPhase(),
        )
        board = GameBoardComponents(
            FakePowerPlantMarket(),
            FakeResourceMarket(),
            FakeTowns(),
            CheckAndBumpStep(2),
        )
        with self.assertRaises(ValueError):
            GameController(
                [PlayerColor.RED],
                {PlayerColor.RED: SimplePlayerBoardFake(PlayerColor.RED)},
                phases,
                board,
            )
        with self.assertRaises(ValueError):
            GameController(
                [PlayerColor.RED, PlayerColor.RED],
                {PlayerColor.RED: SimplePlayerBoardFake(PlayerColor.RED)},
                phases,
                board,
            )
        with self.assertRaises(ValueError):
            GameController(
                [PlayerColor.RED, PlayerColor.BLUE],
                {
                    PlayerColor.RED: SimplePlayerBoardFake(PlayerColor.RED),
                    PlayerColor.GREEN: SimplePlayerBoardFake(PlayerColor.GREEN),
                },
                phases,
                board,
            )

    def test_wrong_phase_actions_rejected_in_every_phase(self) -> None:
        harness = _build_harness()
        ctrl = harness.controller

        # During AUCTION_POWER_PLANTS
        self.assertIsInstance(
            ctrl.buy_resources(PlayerColor.RED, []), RequestError
        )
        self.assertIsInstance(
            ctrl.buy_houses(PlayerColor.RED, []), RequestError
        )
        self.assertIsInstance(
            ctrl.use_power_plants(PlayerColor.RED, [], []), RequestError
        )

        # Advance to BUY_RESOURCES
        harness.phases.auction.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsNone(ctrl.do_not_want_power_plant(PlayerColor.RED))
        self.assertEqual(ctrl.game_phase, GamePhase.BUY_RESOURCES)
        self.assertIsInstance(
            ctrl.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(3), 3
            ),
            RequestError,
        )
        self.assertIsInstance(
            ctrl.do_not_want_power_plant(PlayerColor.RED), RequestError
        )
        self.assertIsInstance(
            ctrl.bid_for_current_power_plant(PlayerColor.RED, 4), RequestError
        )
        self.assertIsInstance(
            ctrl.do_not_bid_for_current_power_plant(PlayerColor.RED),
            RequestError,
        )
        self.assertIsInstance(
            ctrl.remove_power_plant(PlayerColor.RED, PowerPlantNumber(3), []),
            RequestError,
        )
        self.assertIsInstance(
            ctrl.buy_houses(PlayerColor.RED, []), RequestError
        )
        self.assertIsInstance(
            ctrl.use_power_plants(PlayerColor.RED, [], []), RequestError
        )

    def test_all_five_auction_actions_delegate_and_propagate_errors(
        self,
    ) -> None:
        harness = _build_harness()
        ctrl = harness.controller

        harness.phases.auction.next_result = RequestError("Invalid auction move")
        self.assertEqual(
            ctrl.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(4), 4
            ),
            RequestError("Invalid auction move"),
        )
        self.assertEqual(ctrl.game_phase, GamePhase.AUCTION_POWER_PLANTS)

        harness.phases.auction.next_result = PhaseStatus.PHASE_CONTINUES
        self.assertIsNone(
            ctrl.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(4), 4
            )
        )
        self.assertIsNone(ctrl.bid_for_current_power_plant(PlayerColor.BLUE, 5))
        self.assertIsNone(
            ctrl.do_not_bid_for_current_power_plant(PlayerColor.RED)
        )
        self.assertIsNone(
            ctrl.remove_power_plant(
                PlayerColor.BLUE, PowerPlantNumber(3), [Resource.COAL]
            )
        )
        self.assertIsNone(ctrl.do_not_want_power_plant(PlayerColor.RED))
        self.assertEqual(len(harness.phases.auction.calls), 6)

    def test_round_one_reorders_after_auction_but_round_two_does_not(
        self,
    ) -> None:
        harness = _build_harness(
            [PlayerColor.RED, PlayerColor.YELLOW, PlayerColor.BLUE]
        )
        ctrl = harness.controller
        harness.boards[PlayerColor.RED].best_plant = 5
        harness.boards[PlayerColor.YELLOW].best_plant = 10
        harness.boards[PlayerColor.BLUE].best_plant = 7

        # End Round 1 Auction -> must reorder by largest plant (YELLOW, BLUE, RED)
        harness.phases.auction.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsNone(ctrl.do_not_want_power_plant(PlayerColor.RED))
        self.assertFalse(ctrl.is_first_turn)
        self.assertEqual(
            ctrl.player_order,
            [PlayerColor.YELLOW, PlayerColor.BLUE, PlayerColor.RED],
        )
        self.assertEqual(
            harness.phases.buying.started_orders,
            [[PlayerColor.YELLOW, PlayerColor.BLUE, PlayerColor.RED]],
        )

        # Complete Round 1 Phases 3, 4, 5 -> Phase 1 reorders for Round 2
        harness.phases.buying.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsNone(ctrl.buy_resources(PlayerColor.RED, []))
        harness.board.towns.set_house_count(PlayerColor.RED, 3)
        harness.board.towns.set_house_count(PlayerColor.BLUE, 1)
        harness.board.towns.set_house_count(PlayerColor.YELLOW, 1)
        harness.phases.houses.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsNone(ctrl.buy_houses(PlayerColor.RED, []))
        harness.phases.bureaucracy.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsNone(ctrl.use_power_plants(PlayerColor.YELLOW, [], []))

        # Round 2 order: RED(3) > YELLOW(1, plant 10) > BLUE(1, plant 7)
        round2_order = [PlayerColor.RED, PlayerColor.YELLOW, PlayerColor.BLUE]
        self.assertEqual(ctrl.player_order, round2_order)
        self.assertEqual(ctrl.game_phase, GamePhase.AUCTION_POWER_PLANTS)

        # Give BLUE plant 50 during Round 2 auction -> must NOT reorder after Phase 2!
        harness.boards[PlayerColor.BLUE].best_plant = 50
        harness.phases.auction.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsNone(ctrl.do_not_want_power_plant(PlayerColor.RED))
        self.assertEqual(ctrl.player_order, round2_order)

    def test_step2_and_step3_transitions_across_phases(self) -> None:
        harness = _build_harness([PlayerColor.RED, PlayerColor.BLUE])
        ctrl = harness.controller

        # Phase 2 -> Phase 3 (no step 3 yet)
        harness.phases.auction.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsNone(ctrl.do_not_want_power_plant(PlayerColor.RED))
        self.assertEqual(harness.board.step_bumper.get_step(), 1)

        # Phase 3 -> Phase 4
        harness.phases.buying.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsNone(ctrl.buy_resources(PlayerColor.BLUE, []))

        # Phase 4 ends with 7 houses -> triggers Step 2!
        harness.board.towns.set_house_count(PlayerColor.RED, 7)
        harness.phases.houses.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsNone(ctrl.buy_houses(PlayerColor.RED, []))
        self.assertEqual(harness.board.step_bumper.get_step(), 2)
        self.assertEqual(harness.board.towns.step_events, ["step2"])

        # Phase 5 ends with step3 card drawn during prepare_next_turn -> Step 3!
        harness.board.plant_market.step3_ready = True
        harness.phases.bureaucracy.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsNone(ctrl.use_power_plants(PlayerColor.RED, [], []))
        self.assertEqual(harness.board.step_bumper.get_step(), 3)
        self.assertEqual(harness.board.towns.step_events, ["step2", "step3"])

    def test_step3_checked_at_end_of_phase2_and_phase4(self) -> None:
        # Case 1: Step 3 card drawn in Phase 2
        harness_p2 = _build_harness([PlayerColor.RED, PlayerColor.BLUE])
        harness_p2.board.plant_market.step3_ready = True
        harness_p2.phases.auction.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsNone(
            harness_p2.controller.do_not_want_power_plant(PlayerColor.RED)
        )
        self.assertEqual(harness_p2.board.step_bumper.get_step(), 3)

        # Case 2: Step 3 card drawn in Phase 4
        harness_p4 = _build_harness([PlayerColor.RED, PlayerColor.BLUE])
        harness_p4.phases.auction.next_result = PhaseStatus.PHASE_ENDS
        harness_p4.controller.do_not_want_power_plant(PlayerColor.RED)
        harness_p4.phases.buying.next_result = PhaseStatus.PHASE_ENDS
        harness_p4.controller.buy_resources(PlayerColor.BLUE, [])
        harness_p4.board.plant_market.step3_ready = True
        harness_p4.phases.houses.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsNone(
            harness_p4.controller.buy_houses(PlayerColor.RED, [])
        )
        self.assertEqual(harness_p4.board.step_bumper.get_step(), 3)

    def test_game_end_skips_bureaucracy_and_applies_tie_breakers(self) -> None:
        order = [
            PlayerColor.RED,
            PlayerColor.YELLOW,
            PlayerColor.BLUE,
            PlayerColor.GREEN,
        ]
        harness = _build_harness(order)
        ctrl = harness.controller

        # RED: 5 houses, 8 connectable -> powered=5, money=20
        # YELLOW: 4 houses, 4 connectable -> powered=4, money=90
        # BLUE: 6 houses, 5 connectable -> powered=5, money=20 (more houses than RED!)
        # GREEN: 5 houses, 5 connectable -> powered=5, money=35 (more money than BLUE!)
        harness.board.towns.set_house_count(PlayerColor.RED, 5)
        harness.board.towns.set_house_count(PlayerColor.YELLOW, 4)
        harness.board.towns.set_house_count(PlayerColor.BLUE, 6)
        harness.board.towns.set_house_count(PlayerColor.GREEN, 5)

        harness.boards[PlayerColor.RED].connectable = 8
        harness.boards[PlayerColor.RED].money = 20
        harness.boards[PlayerColor.YELLOW].connectable = 4
        harness.boards[PlayerColor.YELLOW].money = 90
        harness.boards[PlayerColor.BLUE].connectable = 5
        harness.boards[PlayerColor.BLUE].money = 20
        harness.boards[PlayerColor.GREEN].connectable = 5
        harness.boards[PlayerColor.GREEN].money = 35

        harness.phases.auction.next_result = PhaseStatus.PHASE_ENDS
        ctrl.do_not_want_power_plant(PlayerColor.RED)
        harness.phases.buying.next_result = PhaseStatus.PHASE_ENDS
        ctrl.buy_resources(PlayerColor.RED, [])
        harness.phases.houses.next_result = PhaseStatus.GAME_ENDS
        self.assertIsNone(ctrl.buy_houses(PlayerColor.RED, []))

        self.assertEqual(ctrl.game_phase, GamePhase.GAME_END)
        self.assertEqual(harness.phases.bureaucracy.started_orders, [])
        self.assertEqual(
            ctrl.game_result,
            [
                PlayerColor.GREEN,
                PlayerColor.BLUE,
                PlayerColor.RED,
                PlayerColor.YELLOW,
            ],
        )

        # Every action rejected after GAME_END
        self.assertIsInstance(
            ctrl.do_not_want_power_plant(PlayerColor.RED), RequestError
        )
        self.assertIsInstance(
            ctrl.buy_resources(PlayerColor.RED, []), RequestError
        )
        self.assertIsInstance(
            ctrl.buy_houses(PlayerColor.RED, []), RequestError
        )
        self.assertIsInstance(
            ctrl.use_power_plants(PlayerColor.RED, [], []), RequestError
        )

        parsed = json.loads(ctrl.get_state())
        self.assertEqual(parsed["game_phase"], "GAME_END")
        self.assertIsNone(parsed["phase_state"])
        self.assertEqual(
            parsed["game_result"], ["GREEN", "BLUE", "RED", "YELLOW"]
        )

    def test_get_state_handles_json_and_non_json_collaborator_strings(
        self,
    ) -> None:
        harness = _build_harness([PlayerColor.RED, PlayerColor.BLUE])
        harness.phases.auction.state_str = "non-json-auction-state"
        harness.board.resource_market.raw_state = "raw-market"
        harness.boards[PlayerColor.RED].raw_state = "raw-red-board"

        parsed = json.loads(harness.controller.get_state())
        self.assertEqual(parsed["phase_state"], "non-json-auction-state")
        self.assertEqual(parsed["resource_market"], "raw-market")
        self.assertEqual(parsed["players"]["RED"], "raw-red-board")
        self.assertEqual(
            parsed["players"]["BLUE"], {"color": "BLUE", "money": 50}
        )

    def test_unknown_player_rejected_without_calling_phase(self) -> None:
        # D1: Unknown player must be rejected at controller boundary
        harness = _build_harness([PlayerColor.RED, PlayerColor.BLUE])
        ctrl = harness.controller

        err = ctrl.select_power_plant_to_bid(
            PlayerColor.BLACK, PowerPlantNumber(3), 3
        )
        self.assertIsInstance(err, RequestError)
        self.assertEqual(harness.phases.auction.calls, [])

        err2 = ctrl.do_not_want_power_plant(PlayerColor.BLACK)
        self.assertIsInstance(err2, RequestError)
        self.assertEqual(harness.phases.auction.calls, [])

    def test_unexpected_game_ends_outside_building_houses_raises(
        self,
    ) -> None:
        # D2: GAME_ENDS from Auction, BuyingResources, or Bureaucracy must raise
        harness_a = _build_harness()
        harness_a.phases.auction.next_result = PhaseStatus.GAME_ENDS
        with self.assertRaises(ValueError):
            harness_a.controller.do_not_want_power_plant(PlayerColor.RED)

        harness_b = _build_harness()
        harness_b.phases.auction.next_result = PhaseStatus.PHASE_ENDS
        harness_b.controller.do_not_want_power_plant(PlayerColor.RED)
        harness_b.phases.buying.next_result = PhaseStatus.GAME_ENDS
        with self.assertRaises(ValueError):
            harness_b.controller.buy_resources(PlayerColor.BLUE, [])

        harness_c = _build_harness()
        harness_c.phases.auction.next_result = PhaseStatus.PHASE_ENDS
        harness_c.controller.do_not_want_power_plant(PlayerColor.RED)
        harness_c.phases.buying.next_result = PhaseStatus.PHASE_ENDS
        harness_c.controller.buy_resources(PlayerColor.BLUE, [])
        harness_c.phases.houses.next_result = PhaseStatus.PHASE_ENDS
        harness_c.controller.buy_houses(PlayerColor.RED, [])
        harness_c.phases.bureaucracy.next_result = PhaseStatus.GAME_ENDS
        with self.assertRaises(ValueError):
            harness_c.controller.use_power_plants(PlayerColor.RED, [], [])

    def test_invalid_bids_and_plant_numbers_rejected(self) -> None:
        # D3: Non-positive bids / plant numbers must return RequestError
        harness = _build_harness()
        ctrl = harness.controller

        self.assertIsInstance(
            ctrl.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(3), 0
            ),
            RequestError,
        )
        self.assertIsInstance(
            ctrl.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(3), -5
            ),
            RequestError,
        )
        self.assertIsInstance(
            ctrl.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(0), 5
            ),
            RequestError,
        )
        self.assertIsInstance(
            ctrl.bid_for_current_power_plant(PlayerColor.RED, 0),
            RequestError,
        )
        self.assertIsInstance(
            ctrl.bid_for_current_power_plant(PlayerColor.RED, -1),
            RequestError,
        )
        self.assertEqual(harness.phases.auction.calls, [])

    def test_start_phase_mutation_cannot_corrupt_player_order(self) -> None:
        # D5: Mutating player_order passed into start_phase must not alias
        def mutator(order: Sequence[PlayerColor]) -> None:
            if isinstance(order, list):
                order.clear()

        mutating_auction = FakeAuctionPhase(on_start=mutator)
        harness = _build_harness(
            [PlayerColor.RED, PlayerColor.BLUE], auction=mutating_auction
        )
        self.assertEqual(
            harness.controller.player_order,
            [PlayerColor.RED, PlayerColor.BLUE],
        )

    def test_unregistered_player_rejected_across_all_four_active_phases(
        self,
    ) -> None:
        harness = _build_harness([PlayerColor.RED, PlayerColor.BLUE])
        ctrl = harness.controller

        # Phase 2: AUCTION_POWER_PLANTS (all 5 auction actions)
        self.assertIsInstance(
            ctrl.select_power_plant_to_bid(
                PlayerColor.BLACK, PowerPlantNumber(3), 3
            ),
            RequestError,
        )
        self.assertIsInstance(
            ctrl.do_not_want_power_plant(PlayerColor.BLACK), RequestError
        )
        self.assertIsInstance(
            ctrl.bid_for_current_power_plant(PlayerColor.BLACK, 4),
            RequestError,
        )
        self.assertIsInstance(
            ctrl.do_not_bid_for_current_power_plant(PlayerColor.BLACK),
            RequestError,
        )
        self.assertIsInstance(
            ctrl.remove_power_plant(
                PlayerColor.BLACK, PowerPlantNumber(3), []
            ),
            RequestError,
        )
        self.assertEqual(harness.phases.auction.calls, [])

        # Phase 3: BUY_RESOURCES
        harness.phases.auction.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsNone(ctrl.do_not_want_power_plant(PlayerColor.RED))
        self.assertIsInstance(
            ctrl.buy_resources(PlayerColor.BLACK, [Resource.COAL]),
            RequestError,
        )
        self.assertEqual(harness.phases.buying.calls, [])

        # Phase 4: BUY_HOUSES
        harness.phases.buying.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsNone(ctrl.buy_resources(PlayerColor.BLUE, []))
        self.assertIsInstance(
            ctrl.buy_houses(PlayerColor.BLACK, ["Berlin"]), RequestError
        )
        self.assertEqual(harness.phases.houses.calls, [])

        # Phase 5: BUREAUCRACY
        harness.phases.houses.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsNone(ctrl.buy_houses(PlayerColor.RED, []))
        self.assertIsInstance(
            ctrl.use_power_plants(PlayerColor.BLACK, [], []), RequestError
        )
        self.assertEqual(harness.phases.bureaucracy.calls, [])

    def test_bool_and_non_positive_inputs_across_auction_and_bureaucracy(
        self,
    ) -> None:
        harness = _build_harness([PlayerColor.RED, PlayerColor.BLUE])
        ctrl = harness.controller

        for bad_num in (0, -4, True, False):
            self.assertIsInstance(
                ctrl.select_power_plant_to_bid(
                    PlayerColor.RED, PowerPlantNumber(bad_num), 5
                ),
                RequestError,
            )
            self.assertIsInstance(
                ctrl.remove_power_plant(
                    PlayerColor.RED, PowerPlantNumber(bad_num), []
                ),
                RequestError,
            )
        for bad_bid in (True, False):
            self.assertIsInstance(
                ctrl.select_power_plant_to_bid(
                    PlayerColor.RED, PowerPlantNumber(4), bad_bid
                ),
                RequestError,
            )
            self.assertIsInstance(
                ctrl.bid_for_current_power_plant(PlayerColor.RED, bad_bid),
                RequestError,
            )
        self.assertEqual(harness.phases.auction.calls, [])

        # Advance to BUREAUCRACY and check invalid plant numbers in ppns list
        harness.phases.auction.next_result = PhaseStatus.PHASE_ENDS
        ctrl.do_not_want_power_plant(PlayerColor.RED)
        harness.phases.buying.next_result = PhaseStatus.PHASE_ENDS
        ctrl.buy_resources(PlayerColor.BLUE, [])
        harness.phases.houses.next_result = PhaseStatus.PHASE_ENDS
        ctrl.buy_houses(PlayerColor.RED, [])

        for bad_num in (0, -2, True, False):
            self.assertIsInstance(
                ctrl.use_power_plants(
                    PlayerColor.RED,
                    [PowerPlantNumber(4), PowerPlantNumber(bad_num)],
                    [],
                ),
                RequestError,
            )
        self.assertEqual(harness.phases.bureaucracy.calls, [])

    def test_step3_during_turn_one_auction_followed_by_turn_one_reorder(
        self,
    ) -> None:
        harness = _build_harness(
            [PlayerColor.RED, PlayerColor.YELLOW, PlayerColor.BLUE]
        )
        ctrl = harness.controller
        harness.boards[PlayerColor.RED].best_plant = 4
        harness.boards[PlayerColor.YELLOW].best_plant = 12
        harness.boards[PlayerColor.BLUE].best_plant = 8
        harness.board.plant_market.step3_ready = True
        harness.phases.auction.next_result = PhaseStatus.PHASE_ENDS

        self.assertIsNone(ctrl.do_not_want_power_plant(PlayerColor.RED))
        self.assertEqual(harness.board.step_bumper.get_step(), 3)
        self.assertFalse(ctrl.is_first_turn)
        self.assertEqual(ctrl.game_phase, GamePhase.BUY_RESOURCES)
        self.assertEqual(
            ctrl.player_order,
            [PlayerColor.YELLOW, PlayerColor.BLUE, PlayerColor.RED],
        )
        self.assertEqual(
            harness.phases.buying.started_orders,
            [[PlayerColor.YELLOW, PlayerColor.BLUE, PlayerColor.RED]],
        )

    def test_remove_power_plant_defensively_copies_removed_resources(
        self,
    ) -> None:
        class MutatingRemoveAuction(FakeAuctionPhase):
            def __init__(self) -> None:
                super().__init__()
                self.received_list = False

            def remove_power_plant(
                self, player: PlayerColor, ppn: PowerPlantNumber,
                resources: Sequence[Resource],
            ) -> PhaseStatus | RequestError:
                self.received_list = isinstance(resources, list)
                status = super().remove_power_plant(player, ppn, resources)
                if isinstance(resources, list):
                    resources.clear()
                return status

        auction = MutatingRemoveAuction()
        harness = _build_harness(
            [PlayerColor.RED, PlayerColor.BLUE], auction=auction
        )
        caller_resources = [Resource.COAL, Resource.OIL]
        self.assertIsNone(
            harness.controller.remove_power_plant(
                PlayerColor.RED, PowerPlantNumber(3), caller_resources
            )
        )
        self.assertTrue(auction.received_list)
        self.assertEqual(caller_resources, [Resource.COAL, Resource.OIL])

    def test_get_state_includes_power_plant_market_and_towns(self) -> None:
        harness = _build_harness([PlayerColor.RED, PlayerColor.BLUE])
        harness.board.towns.set_house_count(PlayerColor.RED, 2)
        parsed = json.loads(harness.controller.get_state())

        self.assertIn("power_plant_market", parsed)
        self.assertIn("towns", parsed)
        self.assertEqual(parsed["towns"]["step"], 1)
        self.assertEqual(
            parsed["towns"]["houses"]["RED"], ["RED_0", "RED_1"]
        )
