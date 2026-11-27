# pylint: disable=too-many-public-methods,too-many-lines
from __future__ import annotations

import json
import unittest
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from power_grid.auction_power_plants import AuctionPowerPlants, AuctionStage
from power_grid.power_plant import PowerPlant, PowerPlantNumber
from power_grid.simple_types import (
    PhaseStatus,
    PlayerColor,
    RequestError,
    Resource,
)


def _make_plant(
    number: int,
    resources: Sequence[Resource] = (Resource.COAL,),
    amount: int = 1,
    cities: int = 1,
) -> PowerPlant:
    return PowerPlant(PowerPlantNumber(number), list(resources), amount, cities)


@dataclass
class MarketFaults:
    next_can_take_error: RequestError | None = None
    take_exception: Exception | None = None
    remove_discounted_exception: Exception | None = None
    mutate_ppn_on_can_take_to: int | None = None


class StubPowerPlantMarket:
    def __init__(
        self,
        available: Sequence[PowerPlant] = (),
        *,
        discounted_number: int | None = None,
    ) -> None:
        self.plants: dict[int, PowerPlant] = {
            plant.number.number: plant for plant in available
        }
        self.discounted_number = discounted_number
        self.can_take_calls: list[tuple[int, int]] = []
        self.take_calls: list[int] = []
        self.remove_discounted_calls: int = 0
        self.faults = MarketFaults()

    def can_take_power_plant(
        self, ppn: PowerPlantNumber, price: int
    ) -> RequestError | None:
        self.can_take_calls.append((ppn.number, price))
        if self.faults.next_can_take_error is not None:
            err = self.faults.next_can_take_error
            self.faults.next_can_take_error = None
            return err
        plant = self.plants.get(ppn.number)
        if plant is None:
            return RequestError(f"Power plant {ppn.number} not in market")
        min_price = (
            1
            if self.discounted_number == ppn.number
            else plant.number.number
        )
        if price < min_price:
            return RequestError(
                f"Price {price} below minimum {min_price} for plant {ppn.number}"
            )
        if self.faults.mutate_ppn_on_can_take_to is not None:
            ppn.number = self.faults.mutate_ppn_on_can_take_to
        return None

    def take_power_plant(self, ppn: PowerPlantNumber) -> PowerPlant:
        self.take_calls.append(ppn.number)
        exc = self.faults.take_exception
        if exc is not None:
            self.faults.take_exception = None
            raise exc
        if ppn.number not in self.plants:
            raise ValueError(f"Power plant {ppn.number} not available")
        if self.discounted_number == ppn.number:
            self.discounted_number = None
        return self.plants.pop(ppn.number)

    def remove_discounted_power_plant(self) -> None:
        self.remove_discounted_calls += 1
        exc = self.faults.remove_discounted_exception
        if exc is not None:
            self.faults.remove_discounted_exception = None
            raise exc
        if (
            self.discounted_number is not None
            and self.discounted_number in self.plants
        ):
            self.plants.pop(self.discounted_number)
        self.discounted_number = None


@dataclass
class BoardFaults:
    next_remove_error: RequestError | None = None
    receive_exception: Exception | None = None


class StubPlayerBoard:
    def __init__(
        self,
        money: int = 50,
        *,
        max_plants: int = 3,
        initial_plants: Sequence[int] = (),
    ) -> None:
        self.money = money
        self.max_plants = max_plants
        self.owned_plants: list[int] = list(initial_plants)
        self.received: list[tuple[int, int]] = []
        self.removed: list[tuple[int, list[Resource]]] = []
        self.money_checks: list[int] = []
        self.faults = BoardFaults()

    def has_enough_money(self, amount: int) -> bool:
        self.money_checks.append(amount)
        return self.money >= amount

    def receive_power_plant(self, power_plant: PowerPlant, price: int) -> bool:
        exc = self.faults.receive_exception
        if exc is not None:
            self.faults.receive_exception = None
            raise exc
        if self.money < price:
            raise ValueError("Insufficient funds")
        self.money -= price
        self.owned_plants.append(power_plant.number.number)
        self.received.append((power_plant.number.number, price))
        return len(self.owned_plants) <= self.max_plants

    def remove_power_plant(
        self, ppn: PowerPlantNumber, removed_resources: Sequence[Resource]
    ) -> RequestError | None:
        res_copy = list(removed_resources)
        self.removed.append((ppn.number, res_copy))
        if self.faults.next_remove_error is not None:
            err = self.faults.next_remove_error
            self.faults.next_remove_error = None
            return err
        if ppn.number not in self.owned_plants:
            return RequestError(f"Plant {ppn.number} not owned")
        self.owned_plants.remove(ppn.number)
        return None


def _default_market() -> StubPowerPlantMarket:
    return StubPowerPlantMarket(
        [
            _make_plant(3),
            _make_plant(4),
            _make_plant(5),
            _make_plant(6),
            _make_plant(10),
            _make_plant(12),
        ],
        discounted_number=3,
    )


def _make_boards(
    money_by_player: Mapping[PlayerColor, int],
    *,
    max_plants: int = 3,
    initial_plants: Mapping[PlayerColor, Sequence[int]] | None = None,
) -> dict[PlayerColor, StubPlayerBoard]:
    plants_map = initial_plants or {}
    return {
        color: StubPlayerBoard(
            money=amount,
            max_plants=max_plants,
            initial_plants=plants_map.get(color, ()),
        )
        for color, amount in money_by_player.items()
    }


def _snapshot(auction: AuctionPowerPlants) -> dict[str, object]:
    parsed: dict[str, object] = json.loads(auction.get_state())
    return parsed


class TestAuctionPowerPlants(unittest.TestCase):
    def test_init_validation_and_initial_state(self) -> None:
        market = _default_market()
        with self.assertRaises(ValueError):
            AuctionPowerPlants(market, {})

        boards = _make_boards({PlayerColor.RED: 50, PlayerColor.BLUE: 50})
        for invalid_flag in (0, 1, "True", None):
            with self.assertRaises(ValueError):
                AuctionPowerPlants(
                    market,
                    boards,
                    is_first_round=cast(bool, invalid_flag),
                )

        auction = AuctionPowerPlants(market, boards)
        self.assertTrue(auction.is_first_round)
        self.assertFalse(auction.is_active)
        self.assertEqual(auction.stage, AuctionStage.INACTIVE)
        self.assertIsNone(auction.current_player)
        self.assertEqual(auction.eligible_players, [])
        self.assertEqual(auction.active_bidders, [])
        self.assertIsNone(auction.current_plant)
        self.assertIsNone(auction.current_bid)
        self.assertIsNone(auction.highest_bidder)

        # Mutating caller mapping does not affect internal registry
        boards[PlayerColor.BLACK] = StubPlayerBoard(50)
        with self.assertRaises(ValueError):
            auction.start_phase(
                [PlayerColor.RED, PlayerColor.BLUE, PlayerColor.BLACK]
            )

        second_round_auction = AuctionPowerPlants(
            market,
            {PlayerColor.RED: StubPlayerBoard(50)},
            is_first_round=False,
        )
        self.assertFalse(second_round_auction.is_first_round)

    def test_start_phase_validation_defensive_copy_and_atomicity(self) -> None:
        market = _default_market()
        boards = _make_boards(
            {
                PlayerColor.RED: 50,
                PlayerColor.BLUE: 50,
                PlayerColor.YELLOW: 50,
            }
        )
        auction = AuctionPowerPlants(market, boards)

        for invalid_order in (
            [],
            [PlayerColor.RED, PlayerColor.RED, PlayerColor.BLUE],
            [PlayerColor.RED, PlayerColor.BLUE],
            [
                PlayerColor.RED,
                PlayerColor.BLUE,
                PlayerColor.YELLOW,
                PlayerColor.GREEN,
            ],
            [PlayerColor.RED, PlayerColor.BLUE, PlayerColor.BLACK],
        ):
            with self.assertRaises(ValueError):
                auction.start_phase(invalid_order)
            self.assertEqual(auction.stage, AuctionStage.INACTIVE)

        caller_order = [
            PlayerColor.YELLOW,
            PlayerColor.RED,
            PlayerColor.BLUE,
        ]
        auction.start_phase(caller_order)
        caller_order.reverse()
        caller_order.append(PlayerColor.BLACK)

        self.assertTrue(auction.is_active)
        self.assertEqual(auction.stage, AuctionStage.SELECTING)
        self.assertEqual(auction.current_player, PlayerColor.YELLOW)
        self.assertEqual(
            auction.eligible_players,
            [PlayerColor.YELLOW, PlayerColor.RED, PlayerColor.BLUE],
        )

        # Failed start_phase while active must not corrupt ongoing bidding
        self.assertEqual(
            auction.select_power_plant_to_bid(
                PlayerColor.YELLOW, PowerPlantNumber(4), 4
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        before = _snapshot(auction)
        with self.assertRaises(ValueError):
            auction.start_phase([PlayerColor.YELLOW, PlayerColor.RED])
        self.assertEqual(_snapshot(auction), before)

        # Accepts tuple Sequence
        auction.start_phase(
            (PlayerColor.BLUE, PlayerColor.YELLOW, PlayerColor.RED)
        )
        self.assertEqual(auction.stage, AuctionStage.SELECTING)
        self.assertEqual(auction.current_player, PlayerColor.BLUE)
        self.assertIsNone(auction.current_plant)

    def test_inactive_phase_rejects_all_actions_atomically(self) -> None:
        market = _default_market()
        boards = _make_boards({PlayerColor.RED: 50, PlayerColor.BLUE: 50})
        auction = AuctionPowerPlants(market, boards)
        before = _snapshot(auction)

        self.assertIsInstance(
            auction.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(4), 4
            ),
            RequestError,
        )
        self.assertIsInstance(
            auction.do_not_want_power_plant(PlayerColor.RED), RequestError
        )
        self.assertIsInstance(
            auction.bid_for_current_power_plant(PlayerColor.RED, 5),
            RequestError,
        )
        self.assertIsInstance(
            auction.do_not_bid_for_current_power_plant(PlayerColor.RED),
            RequestError,
        )
        self.assertIsInstance(
            auction.remove_power_plant(
                PlayerColor.RED, PowerPlantNumber(3), []
            ),
            RequestError,
        )
        self.assertEqual(_snapshot(auction), before)
        self.assertEqual(market.can_take_calls, [])
        self.assertEqual(market.take_calls, [])
        self.assertEqual(market.remove_discounted_calls, 0)

    def test_wrong_stage_and_wrong_player_rejections_are_atomic(self) -> None:
        market = _default_market()
        boards = _make_boards(
            {PlayerColor.RED: 50, PlayerColor.BLUE: 50},
            max_plants=1,
            initial_plants={PlayerColor.RED: [1], PlayerColor.BLUE: [2]},
        )
        auction = AuctionPowerPlants(market, boards, is_first_round=False)
        auction.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        # SELECTING stage rejections
        selecting_snap = _snapshot(auction)
        for result in (
            auction.select_power_plant_to_bid(
                PlayerColor.BLUE, PowerPlantNumber(4), 4
            ),
            auction.select_power_plant_to_bid(
                PlayerColor.BLACK, PowerPlantNumber(4), 4
            ),
            auction.do_not_want_power_plant(PlayerColor.BLUE),
            auction.do_not_want_power_plant(PlayerColor.BLACK),
            auction.bid_for_current_power_plant(PlayerColor.RED, 5),
            auction.do_not_bid_for_current_power_plant(PlayerColor.RED),
            auction.remove_power_plant(
                PlayerColor.RED, PowerPlantNumber(1), []
            ),
        ):
            self.assertIsInstance(result, RequestError)
        self.assertEqual(_snapshot(auction), selecting_snap)

        # Enter BIDDING
        self.assertEqual(
            auction.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(4), 4
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        bidding_snap = _snapshot(auction)
        for result in (
            auction.select_power_plant_to_bid(
                PlayerColor.BLUE, PowerPlantNumber(5), 5
            ),
            auction.do_not_want_power_plant(PlayerColor.BLUE),
            auction.bid_for_current_power_plant(PlayerColor.RED, 5),
            auction.bid_for_current_power_plant(PlayerColor.BLACK, 5),
            auction.do_not_bid_for_current_power_plant(PlayerColor.RED),
            auction.do_not_bid_for_current_power_plant(PlayerColor.BLACK),
            auction.remove_power_plant(
                PlayerColor.RED, PowerPlantNumber(1), []
            ),
        ):
            self.assertIsInstance(result, RequestError)
        self.assertEqual(_snapshot(auction), bidding_snap)

        # Enter REMOVING_PLANT (BLUE passes -> RED wins #4 over limit 1)
        self.assertEqual(
            auction.do_not_bid_for_current_power_plant(PlayerColor.BLUE),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(auction.stage, AuctionStage.REMOVING_PLANT)
        removing_snap = _snapshot(auction)
        for result in (
            auction.select_power_plant_to_bid(
                PlayerColor.BLUE, PowerPlantNumber(5), 5
            ),
            auction.do_not_want_power_plant(PlayerColor.BLUE),
            auction.bid_for_current_power_plant(PlayerColor.RED, 5),
            auction.do_not_bid_for_current_power_plant(PlayerColor.RED),
            auction.remove_power_plant(
                PlayerColor.BLUE, PowerPlantNumber(2), []
            ),
            auction.remove_power_plant(
                PlayerColor.BLACK, PowerPlantNumber(1), []
            ),
        ):
            self.assertIsInstance(result, RequestError)
        self.assertEqual(_snapshot(auction), removing_snap)

    def test_invalid_runtime_numeric_inputs_rejected_atomically(self) -> None:
        market = _default_market()
        boards = _make_boards(
            {PlayerColor.RED: 50, PlayerColor.BLUE: 50},
            max_plants=1,
            initial_plants={PlayerColor.RED: [1]},
        )
        auction = AuctionPowerPlants(market, boards)
        auction.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        bad_ints: tuple[object, ...] = (0, -1, -100, True, False, 1.0, 3.5)
        selecting_snap = _snapshot(auction)
        for bad in bad_ints:
            self.assertIsInstance(
                auction.select_power_plant_to_bid(
                    PlayerColor.RED,
                    PowerPlantNumber(cast(int, bad)),
                    4,
                ),
                RequestError,
            )
            self.assertIsInstance(
                auction.select_power_plant_to_bid(
                    PlayerColor.RED,
                    PowerPlantNumber(4),
                    cast(int, bad),
                ),
                RequestError,
            )
        self.assertEqual(_snapshot(auction), selecting_snap)
        self.assertEqual(market.can_take_calls, [])

        # Enter BIDDING and test invalid bid values
        self.assertEqual(
            auction.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(4), 4
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        bidding_snap = _snapshot(auction)
        for bad in bad_ints:
            self.assertIsInstance(
                auction.bid_for_current_power_plant(
                    PlayerColor.BLUE, cast(int, bad)
                ),
                RequestError,
            )
        self.assertEqual(_snapshot(auction), bidding_snap)

        # Enter REMOVING_PLANT and test invalid ppn values
        self.assertEqual(
            auction.do_not_bid_for_current_power_plant(PlayerColor.BLUE),
            PhaseStatus.PHASE_CONTINUES,
        )
        removing_snap = _snapshot(auction)
        for bad in bad_ints:
            self.assertIsInstance(
                auction.remove_power_plant(
                    PlayerColor.RED,
                    PowerPlantNumber(cast(int, bad)),
                    [],
                ),
                RequestError,
            )
        self.assertEqual(_snapshot(auction), removing_snap)
        self.assertEqual(boards[PlayerColor.RED].removed, [])

    def test_mutability_and_aliasing_isolation(self) -> None:
        market = _default_market()
        boards = _make_boards(
            {PlayerColor.RED: 50, PlayerColor.BLUE: 50},
            max_plants=1,
            initial_plants={PlayerColor.RED: [2]},
        )
        auction = AuctionPowerPlants(market, boards)
        auction.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        caller_ppn = PowerPlantNumber(4)
        self.assertEqual(
            auction.select_power_plant_to_bid(
                PlayerColor.RED, caller_ppn, 4
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        # Mutate caller ppn and returned property objects
        caller_ppn.number = 999
        plant_prop = auction.current_plant
        assert plant_prop is not None
        plant_prop.number = 888

        elig = auction.eligible_players
        elig.clear()
        bidders = auction.active_bidders
        bidders.clear()

        self.assertEqual(auction.current_plant.number, 4)  # type: ignore[union-attr]
        self.assertEqual(
            auction.eligible_players, [PlayerColor.RED, PlayerColor.BLUE]
        )
        self.assertEqual(
            auction.active_bidders, [PlayerColor.BLUE, PlayerColor.RED]
        )

        # BLUE passes -> RED wins #4 and enters REMOVING_PLANT
        self.assertEqual(
            auction.do_not_bid_for_current_power_plant(PlayerColor.BLUE),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(market.take_calls, [4])

        # Mutating caller resources list after passing does not affect recorded copy
        caller_resources = [Resource.COAL]
        self.assertEqual(
            auction.remove_power_plant(
                PlayerColor.RED, PowerPlantNumber(2), caller_resources
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        caller_resources.append(Resource.URANIUM)
        self.assertEqual(
            boards[PlayerColor.RED].removed, [(2, [Resource.COAL])]
        )

    def test_market_mutating_ppn_in_can_take_does_not_corrupt_plant(
        self,
    ) -> None:
        market = _default_market()
        market.faults.mutate_ppn_on_can_take_to = 999
        boards = _make_boards({PlayerColor.RED: 50, PlayerColor.BLUE: 50})
        auction = AuctionPowerPlants(market, boards)
        auction.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        self.assertEqual(
            auction.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(4), 4
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertIsNotNone(auction.current_plant)
        assert auction.current_plant is not None
        self.assertEqual(auction.current_plant.number, 4)

    def test_first_round_rules_and_transition_to_second_round(self) -> None:
        market = _default_market()
        boards = _make_boards(
            {PlayerColor.RED: 50, PlayerColor.BLUE: 50},
            max_plants=0,
        )
        auction = AuctionPowerPlants(market, boards, is_first_round=True)
        auction.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        # Cannot pass selection in Round 1
        err = auction.do_not_want_power_plant(PlayerColor.RED)
        self.assertIsInstance(err, RequestError)
        self.assertTrue(auction.is_first_round)
        self.assertEqual(auction.current_player, PlayerColor.RED)

        # RED selects #4; BLUE CAN pass bidding in Round 1
        self.assertEqual(
            auction.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(4), 4
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        # Wait: make RED within limit for first win, BLUE over limit for last win
        boards[PlayerColor.RED].max_plants = 2
        boards[PlayerColor.BLUE].max_plants = 1
        boards[PlayerColor.BLUE].owned_plants = [1]

        self.assertEqual(
            auction.do_not_bid_for_current_power_plant(PlayerColor.BLUE),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertTrue(auction.is_first_round)
        self.assertEqual(auction.current_player, PlayerColor.BLUE)

        # BLUE still cannot pass selection in Round 1
        self.assertIsInstance(
            auction.do_not_want_power_plant(PlayerColor.BLUE), RequestError
        )
        # BLUE selects #5 -> immediate win, enters REMOVING_PLANT
        self.assertEqual(
            auction.select_power_plant_to_bid(
                PlayerColor.BLUE, PowerPlantNumber(5), 5
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(auction.stage, AuctionStage.REMOVING_PLANT)
        # Still Round 1 until removal completes!
        self.assertTrue(auction.is_first_round)
        self.assertEqual(market.remove_discounted_calls, 0)

        # BLUE completes removal -> Round 1 finishes, is_first_round flips False
        self.assertEqual(
            auction.remove_power_plant(
                PlayerColor.BLUE, PowerPlantNumber(1), []
            ),
            PhaseStatus.PHASE_ENDS,
        )
        self.assertFalse(auction.is_first_round)
        self.assertEqual(auction.stage, AuctionStage.INACTIVE)
        self.assertEqual(market.remove_discounted_calls, 1)

        # Round 2: both players can pass selection
        auction.start_phase([PlayerColor.BLUE, PlayerColor.RED])
        self.assertFalse(auction.is_first_round)
        self.assertEqual(
            auction.do_not_want_power_plant(PlayerColor.BLUE),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            auction.do_not_want_power_plant(PlayerColor.RED),
            PhaseStatus.PHASE_ENDS,
        )
        self.assertEqual(market.remove_discounted_calls, 2)

    def test_selection_market_error_insufficient_money_and_discount_bid(
        self,
    ) -> None:
        market = _default_market()
        boards = _make_boards({PlayerColor.RED: 5, PlayerColor.BLUE: 5})
        auction = AuctionPowerPlants(market, boards)
        auction.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        # Market error (bid below face value for non-discounted #6)
        err = auction.select_power_plant_to_bid(
            PlayerColor.RED, PowerPlantNumber(6), 5
        )
        self.assertIsInstance(err, RequestError)
        self.assertEqual(auction.stage, AuctionStage.SELECTING)
        self.assertEqual(boards[PlayerColor.RED].money_checks, [])

        # Market custom error
        market.faults.next_can_take_error = RequestError("Future market")
        err2 = auction.select_power_plant_to_bid(
            PlayerColor.RED, PowerPlantNumber(3), 1
        )
        self.assertEqual(err2, RequestError("Future market"))
        self.assertEqual(auction.stage, AuctionStage.SELECTING)

        # Market allows #6 at 6, but RED only has 5 Elektro
        err3 = auction.select_power_plant_to_bid(
            PlayerColor.RED, PowerPlantNumber(6), 6
        )
        self.assertIsInstance(err3, RequestError)
        self.assertEqual(auction.stage, AuctionStage.SELECTING)
        self.assertEqual(market.take_calls, [])

        # Discounted #3 allows first_bid=1!
        self.assertEqual(
            auction.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(3), 1
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(auction.stage, AuctionStage.BIDDING)
        self.assertEqual(auction.current_bid, 1)
        self.assertEqual(auction.highest_bidder, PlayerColor.RED)
        self.assertEqual(auction.current_player, PlayerColor.BLUE)

    def test_immediate_win_when_last_player_or_no_contender_can_outbid(
        self,
    ) -> None:
        # Case 1: Single player immediate win
        market1 = _default_market()
        boards1 = _make_boards({PlayerColor.RED: 20})
        auction1 = AuctionPowerPlants(market1, boards1)
        auction1.start_phase([PlayerColor.RED])
        self.assertEqual(
            auction1.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(4), 4
            ),
            PhaseStatus.PHASE_ENDS,
        )
        self.assertEqual(boards1[PlayerColor.RED].received, [(4, 4)])
        self.assertEqual(market1.remove_discounted_calls, 1)

        # Case 2: Exact boundary — contender has == first_bid (cannot pay +1)
        market2 = _default_market()
        boards2 = _make_boards({PlayerColor.RED: 20, PlayerColor.BLUE: 10})
        auction2 = AuctionPowerPlants(market2, boards2)
        auction2.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        self.assertEqual(
            auction2.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(10), 10
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        # RED won immediately, BLUE stays eligible to select next!
        self.assertEqual(auction2.stage, AuctionStage.SELECTING)
        self.assertEqual(auction2.current_player, PlayerColor.BLUE)
        self.assertEqual(boards2[PlayerColor.RED].received, [(10, 10)])
        self.assertEqual(boards2[PlayerColor.RED].money, 10)
        self.assertEqual(market2.remove_discounted_calls, 0)

        # Case 3: Contender has == first_bid + 1 -> enters BIDDING!
        market3 = _default_market()
        boards3 = _make_boards({PlayerColor.RED: 20, PlayerColor.BLUE: 11})
        auction3 = AuctionPowerPlants(market3, boards3)
        auction3.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        self.assertEqual(
            auction3.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(10), 10
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(auction3.stage, AuctionStage.BIDDING)
        self.assertEqual(auction3.current_player, PlayerColor.BLUE)
        self.assertEqual(
            auction3.active_bidders, [PlayerColor.BLUE, PlayerColor.RED]
        )

    def test_four_player_cyclic_bidding_and_invalid_bid_rejections(
        self,
    ) -> None:
        market = _default_market()
        boards = _make_boards(
            {
                PlayerColor.RED: 30,
                PlayerColor.BLUE: 30,
                PlayerColor.YELLOW: 30,
                PlayerColor.GREEN: 30,
            }
        )
        auction = AuctionPowerPlants(market, boards)
        auction.start_phase(
            [
                PlayerColor.RED,
                PlayerColor.BLUE,
                PlayerColor.YELLOW,
                PlayerColor.GREEN,
            ]
        )

        # RED opens #10 at 10 -> [BLUE, YELLOW, GREEN, RED]
        self.assertEqual(
            auction.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(10), 10
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            auction.active_bidders,
            [
                PlayerColor.BLUE,
                PlayerColor.YELLOW,
                PlayerColor.GREEN,
                PlayerColor.RED,
            ],
        )

        # Equal, lower, and unaffordable bids rejected atomically
        before = _snapshot(auction)
        self.assertIsInstance(
            auction.bid_for_current_power_plant(PlayerColor.BLUE, 10),
            RequestError,
        )
        self.assertIsInstance(
            auction.bid_for_current_power_plant(PlayerColor.BLUE, 9),
            RequestError,
        )
        self.assertIsInstance(
            auction.bid_for_current_power_plant(PlayerColor.BLUE, 31),
            RequestError,
        )
        self.assertEqual(_snapshot(auction), before)

        # BLUE bids 11 -> [YELLOW, GREEN, RED, BLUE]
        self.assertEqual(
            auction.bid_for_current_power_plant(PlayerColor.BLUE, 11),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            auction.active_bidders,
            [
                PlayerColor.YELLOW,
                PlayerColor.GREEN,
                PlayerColor.RED,
                PlayerColor.BLUE,
            ],
        )

        # YELLOW passes -> [GREEN, RED, BLUE]
        self.assertEqual(
            auction.do_not_bid_for_current_power_plant(PlayerColor.YELLOW),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            auction.active_bidders,
            [PlayerColor.GREEN, PlayerColor.RED, PlayerColor.BLUE],
        )

        # GREEN bids 12 -> [RED, BLUE, GREEN]
        self.assertEqual(
            auction.bid_for_current_power_plant(PlayerColor.GREEN, 12),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            auction.active_bidders,
            [PlayerColor.RED, PlayerColor.BLUE, PlayerColor.GREEN],
        )

        # RED bids 13 -> [BLUE, GREEN, RED]
        self.assertEqual(
            auction.bid_for_current_power_plant(PlayerColor.RED, 13),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            auction.active_bidders,
            [PlayerColor.BLUE, PlayerColor.GREEN, PlayerColor.RED],
        )

        # BLUE passes, GREEN passes -> RED (selector) wins at 13!
        self.assertEqual(
            auction.do_not_bid_for_current_power_plant(PlayerColor.BLUE),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            auction.do_not_bid_for_current_power_plant(PlayerColor.GREEN),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(boards[PlayerColor.RED].received, [(10, 13)])
        # Selector won -> next eligible player is BLUE; YELLOW & GREEN still eligible
        self.assertEqual(auction.stage, AuctionStage.SELECTING)
        self.assertEqual(auction.current_player, PlayerColor.BLUE)
        self.assertEqual(
            auction.eligible_players,
            [PlayerColor.BLUE, PlayerColor.YELLOW, PlayerColor.GREEN],
        )

    def test_auto_pruning_middle_and_immediate_win_on_bid(self) -> None:
        market = _default_market()
        boards = _make_boards(
            {
                PlayerColor.RED: 15,
                PlayerColor.BLUE: 10,
                PlayerColor.YELLOW: 12,
                PlayerColor.GREEN: 20,
            }
        )
        auction = AuctionPowerPlants(market, boards)
        auction.start_phase(
            [
                PlayerColor.RED,
                PlayerColor.BLUE,
                PlayerColor.YELLOW,
                PlayerColor.GREEN,
            ]
        )

        # RED opens #10 at 10 -> BLUE (10) pruned on select! [YELLOW, GREEN, RED]
        self.assertEqual(
            auction.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(10), 10
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            auction.active_bidders,
            [PlayerColor.YELLOW, PlayerColor.GREEN, PlayerColor.RED],
        )
        # BLUE is still eligible for later auctions!
        self.assertIn(PlayerColor.BLUE, auction.eligible_players)

        # YELLOW bids 11 -> GREEN (20) & RED (15) can both afford 12
        self.assertEqual(
            auction.bid_for_current_power_plant(PlayerColor.YELLOW, 11),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            auction.active_bidders,
            [PlayerColor.GREEN, PlayerColor.RED, PlayerColor.YELLOW],
        )

        # GREEN bids 12 -> YELLOW (12) cannot afford 13 -> pruned! [RED, GREEN]
        self.assertEqual(
            auction.bid_for_current_power_plant(PlayerColor.GREEN, 12),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            auction.active_bidders, [PlayerColor.RED, PlayerColor.GREEN]
        )

        # RED bids 15 -> GREEN (20) can afford 16 -> [GREEN, RED]
        self.assertEqual(
            auction.bid_for_current_power_plant(PlayerColor.RED, 15),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            auction.active_bidders, [PlayerColor.GREEN, PlayerColor.RED]
        )

        # GREEN bids 16 -> RED (15) cannot afford 17 -> GREEN wins immediately!
        self.assertEqual(
            auction.bid_for_current_power_plant(PlayerColor.GREEN, 16),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(boards[PlayerColor.GREEN].received, [(10, 16)])
        self.assertEqual(auction.stage, AuctionStage.SELECTING)
        # Non-selector GREEN won -> original selector RED chooses again!
        self.assertEqual(auction.current_player, PlayerColor.RED)
        self.assertEqual(
            auction.eligible_players,
            [PlayerColor.RED, PlayerColor.BLUE, PlayerColor.YELLOW],
        )

    def test_pass_selection_drops_from_phase_while_pass_bid_keeps_eligible(
        self,
    ) -> None:
        market = _default_market()
        boards = _make_boards(
            {
                PlayerColor.RED: 30,
                PlayerColor.BLUE: 30,
                PlayerColor.YELLOW: 30,
            }
        )
        auction = AuctionPowerPlants(market, boards, is_first_round=False)
        auction.start_phase(
            [PlayerColor.RED, PlayerColor.BLUE, PlayerColor.YELLOW]
        )

        # RED passes selection -> dropped from entire Phase 2
        self.assertEqual(
            auction.do_not_want_power_plant(PlayerColor.RED),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            auction.eligible_players, [PlayerColor.BLUE, PlayerColor.YELLOW]
        )

        # BLUE selects #4 at 4 -> RED must NOT be in active_bidders!
        self.assertEqual(
            auction.select_power_plant_to_bid(
                PlayerColor.BLUE, PowerPlantNumber(4), 4
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            auction.active_bidders, [PlayerColor.YELLOW, PlayerColor.BLUE]
        )
        self.assertIsInstance(
            auction.bid_for_current_power_plant(PlayerColor.RED, 5),
            RequestError,
        )

        # YELLOW bids 5, BLUE passes bidding -> YELLOW wins, BLUE stays eligible
        self.assertEqual(
            auction.bid_for_current_power_plant(PlayerColor.YELLOW, 5),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            auction.do_not_bid_for_current_power_plant(PlayerColor.BLUE),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(boards[PlayerColor.YELLOW].received, [(4, 5)])
        self.assertEqual(auction.stage, AuctionStage.SELECTING)
        self.assertEqual(auction.current_player, PlayerColor.BLUE)

        # Original selector BLUE may now pass in Round 2+!
        self.assertEqual(
            auction.do_not_want_power_plant(PlayerColor.BLUE),
            PhaseStatus.PHASE_ENDS,
        )
        self.assertEqual(auction.stage, AuctionStage.INACTIVE)
        self.assertEqual(market.remove_discounted_calls, 1)

    def test_removing_plant_rules_retry_newly_bought_rejection_and_selector_preserved(
        self,
    ) -> None:
        market = _default_market()
        boards = _make_boards(
            {PlayerColor.RED: 30, PlayerColor.BLUE: 30},
            max_plants=1,
            initial_plants={PlayerColor.RED: [1], PlayerColor.BLUE: [2]},
        )
        auction = AuctionPowerPlants(market, boards, is_first_round=False)
        auction.start_phase([PlayerColor.RED, PlayerColor.BLUE])

        # RED selects #4, BLUE bids 5, RED passes -> BLUE (non-selector) wins over limit!
        self.assertEqual(
            auction.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(4), 4
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            auction.bid_for_current_power_plant(PlayerColor.BLUE, 5),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(
            auction.do_not_bid_for_current_power_plant(PlayerColor.RED),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(auction.stage, AuctionStage.REMOVING_PLANT)
        self.assertEqual(auction.current_player, PlayerColor.BLUE)

        # Cannot remove newly purchased plant #4 (board not even called)
        self.assertIsInstance(
            auction.remove_power_plant(
                PlayerColor.BLUE, PowerPlantNumber(4), ()
            ),
            RequestError,
        )
        self.assertEqual(boards[PlayerColor.BLUE].removed, [])

        # Board error (e.g. resources don't fit) keeps stage in REMOVING_PLANT
        boards[PlayerColor.BLUE].faults.next_remove_error = RequestError(
            "Resources do not fit"
        )
        self.assertEqual(
            auction.remove_power_plant(
                PlayerColor.BLUE, PowerPlantNumber(2), ()
            ),
            RequestError("Resources do not fit"),
        )
        self.assertEqual(auction.stage, AuctionStage.REMOVING_PLANT)
        self.assertEqual(auction.current_player, PlayerColor.BLUE)

        # Retry succeeds with tuple resources -> returns to SELECTING with RED!
        self.assertEqual(
            auction.remove_power_plant(
                PlayerColor.BLUE,
                PowerPlantNumber(2),
                (Resource.COAL, Resource.COAL),
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(auction.stage, AuctionStage.SELECTING)
        self.assertEqual(auction.current_player, PlayerColor.RED)
        self.assertEqual(boards[PlayerColor.BLUE].owned_plants, [4])
        self.assertEqual(market.remove_discounted_calls, 0)

        # Last player RED buys #5 -> enters REMOVING_PLANT, still PHASE_CONTINUES
        self.assertEqual(
            auction.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(5), 5
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(auction.stage, AuctionStage.REMOVING_PLANT)
        self.assertEqual(auction.current_player, PlayerColor.RED)
        self.assertEqual(market.remove_discounted_calls, 0)

        # RED removes old plant #1 -> PHASE_ENDS + remove_discounted called once
        self.assertEqual(
            auction.remove_power_plant(
                PlayerColor.RED, PowerPlantNumber(1), ()
            ),
            PhaseStatus.PHASE_ENDS,
        )
        self.assertEqual(auction.stage, AuctionStage.INACTIVE)
        self.assertEqual(market.remove_discounted_calls, 1)

    def test_get_state_json_accuracy_across_all_four_stages(self) -> None:
        market = _default_market()
        boards = _make_boards(
            {PlayerColor.RED: 30, PlayerColor.BLUE: 30},
            max_plants=1,
            initial_plants={PlayerColor.RED: [1], PlayerColor.BLUE: [2]},
        )
        auction = AuctionPowerPlants(market, boards, is_first_round=True)

        self.assertEqual(
            _snapshot(auction),
            {
                "is_active": False,
                "is_first_round": True,
                "stage": "INACTIVE",
                "current_player": None,
                "eligible_players": [],
                "current_plant": None,
                "current_bid": None,
                "highest_bidder": None,
                "active_bidders": [],
                "pending_removal_player": None,
                "pending_removal_bought_plant": None,
            },
        )

        auction.start_phase([PlayerColor.RED, PlayerColor.BLUE])
        self.assertEqual(
            _snapshot(auction),
            {
                "is_active": True,
                "is_first_round": True,
                "stage": "SELECTING",
                "current_player": "RED",
                "eligible_players": ["RED", "BLUE"],
                "current_plant": None,
                "current_bid": None,
                "highest_bidder": None,
                "active_bidders": [],
                "pending_removal_player": None,
                "pending_removal_bought_plant": None,
            },
        )

        auction.select_power_plant_to_bid(
            PlayerColor.RED, PowerPlantNumber(4), 4
        )
        self.assertEqual(
            _snapshot(auction),
            {
                "is_active": True,
                "is_first_round": True,
                "stage": "BIDDING",
                "current_player": "BLUE",
                "eligible_players": ["RED", "BLUE"],
                "current_plant": 4,
                "current_bid": 4,
                "highest_bidder": "RED",
                "active_bidders": ["BLUE", "RED"],
                "pending_removal_player": None,
                "pending_removal_bought_plant": None,
            },
        )

        auction.do_not_bid_for_current_power_plant(PlayerColor.BLUE)
        self.assertEqual(
            _snapshot(auction),
            {
                "is_active": True,
                "is_first_round": True,
                "stage": "REMOVING_PLANT",
                "current_player": "RED",
                "eligible_players": ["BLUE"],
                "current_plant": None,
                "current_bid": None,
                "highest_bidder": None,
                "active_bidders": [],
                "pending_removal_player": "RED",
                "pending_removal_bought_plant": 4,
            },
        )

    def test_exception_in_select_immediate_win_leaves_selecting_atomic(
        self,
    ) -> None:
        market = _default_market()
        market.faults.take_exception = RuntimeError("market failure")
        boards = _make_boards({PlayerColor.RED: 20})
        auction = AuctionPowerPlants(market, boards)
        auction.start_phase([PlayerColor.RED])
        snap = _snapshot(auction)
        with self.assertRaises(RuntimeError):
            auction.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(4), 4
            )
        self.assertEqual(_snapshot(auction), snap)

    def test_exception_in_bid_conclusion_leaves_bidding_state_atomic(
        self,
    ) -> None:
        market = _default_market()
        boards = _make_boards({PlayerColor.RED: 10, PlayerColor.BLUE: 15})
        auction = AuctionPowerPlants(market, boards)
        auction.start_phase([PlayerColor.RED, PlayerColor.BLUE])
        self.assertEqual(
            auction.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(4), 4
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        snap = _snapshot(auction)
        market.faults.take_exception = RuntimeError("market take failed")
        with self.assertRaises(RuntimeError):
            # BLUE bids 10 -> RED (10) cannot afford 11 -> immediate conclusion
            auction.bid_for_current_power_plant(PlayerColor.BLUE, 10)
        self.assertEqual(_snapshot(auction), snap)

        # Retry succeeds cleanly once market recovers
        self.assertEqual(
            auction.bid_for_current_power_plant(PlayerColor.BLUE, 10),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(boards[PlayerColor.BLUE].received, [(4, 10)])
        self.assertEqual(auction.stage, AuctionStage.SELECTING)
        self.assertEqual(auction.current_player, PlayerColor.RED)

    def test_exception_in_pass_bid_conclusion_leaves_bidding_state_atomic(
        self,
    ) -> None:
        market = _default_market()
        boards = _make_boards({PlayerColor.RED: 20, PlayerColor.BLUE: 20})
        auction = AuctionPowerPlants(market, boards)
        auction.start_phase([PlayerColor.RED, PlayerColor.BLUE])
        self.assertEqual(
            auction.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(4), 4
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        snap = _snapshot(auction)
        boards[PlayerColor.RED].faults.receive_exception = RuntimeError(
            "board failed"
        )
        with self.assertRaises(RuntimeError):
            auction.do_not_bid_for_current_power_plant(PlayerColor.BLUE)
        self.assertEqual(_snapshot(auction), snap)

        # Restore plant #4 into stub market (since take ran before receive) & retry
        market.plants[4] = _make_plant(4)
        self.assertEqual(
            auction.do_not_bid_for_current_power_plant(PlayerColor.BLUE),
            PhaseStatus.PHASE_CONTINUES,
        )
        self.assertEqual(boards[PlayerColor.RED].received, [(4, 4)])
        self.assertEqual(auction.stage, AuctionStage.SELECTING)
        self.assertEqual(auction.current_player, PlayerColor.BLUE)

    def test_exception_in_remove_discounted_on_pass_leaves_selecting_atomic(
        self,
    ) -> None:
        market = _default_market()
        boards = _make_boards({PlayerColor.RED: 20})
        auction = AuctionPowerPlants(market, boards, is_first_round=False)
        auction.start_phase([PlayerColor.RED])
        snap = _snapshot(auction)
        market.faults.remove_discounted_exception = RuntimeError(
            "shuffler failed"
        )
        with self.assertRaises(RuntimeError):
            auction.do_not_want_power_plant(PlayerColor.RED)
        self.assertEqual(_snapshot(auction), snap)
        # Retry succeeds cleanly once shuffler recovers
        self.assertEqual(
            auction.do_not_want_power_plant(PlayerColor.RED),
            PhaseStatus.PHASE_ENDS,
        )

    def test_exception_in_remove_discounted_after_win_or_removal_never_zombies(
        self,
    ) -> None:
        # 1. Last player winning in _conclude_auction
        market1 = _default_market()
        boards1 = _make_boards({PlayerColor.RED: 20})
        auction1 = AuctionPowerPlants(market1, boards1)
        auction1.start_phase([PlayerColor.RED])
        market1.faults.remove_discounted_exception = RuntimeError(
            "shuffler failed"
        )
        with self.assertRaises(RuntimeError):
            auction1.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(4), 4
            )
        self.assertEqual(auction1.stage, AuctionStage.INACTIVE)
        self.assertFalse(auction1.is_active)
        self.assertFalse(auction1.is_first_round)

        # 2. Last player finishing remove_power_plant
        market2 = _default_market()
        boards2 = _make_boards(
            {PlayerColor.RED: 20},
            max_plants=1,
            initial_plants={PlayerColor.RED: [1]},
        )
        auction2 = AuctionPowerPlants(market2, boards2)
        auction2.start_phase([PlayerColor.RED])
        self.assertEqual(
            auction2.select_power_plant_to_bid(
                PlayerColor.RED, PowerPlantNumber(4), 4
            ),
            PhaseStatus.PHASE_CONTINUES,
        )
        market2.faults.remove_discounted_exception = RuntimeError(
            "shuffler failed"
        )
        with self.assertRaises(RuntimeError):
            auction2.remove_power_plant(
                PlayerColor.RED, PowerPlantNumber(1), ()
            )
        self.assertEqual(auction2.stage, AuctionStage.INACTIVE)
        self.assertFalse(auction2.is_active)
        self.assertFalse(auction2.is_first_round)


if __name__ == "__main__":
    unittest.main()
