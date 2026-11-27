# pylint: disable=too-many-public-methods,too-many-lines
from __future__ import annotations

import json
import unittest
from collections.abc import Callable, Sequence
from test.blue_test_fakes import (
    FakeAuctionPhase,
    FakePlayerPowerPlants,
)
from typing import cast

from power_grid.building_houses import BuildingHouses
from power_grid.bureaucracy import Bureaucracy
from power_grid.buying_resources import BuyingResources
from power_grid.check_and_bump_step import CheckAndBumpStep
from power_grid.connections import Connections
from power_grid.game_controller import (
    GameBoardComponents,
    GameController,
    GamePhases,
)
from power_grid.player_board_facade import (
    PlayerBoardContext,
    PlayerBoardFacade,
)
from power_grid.player_money import PlayerMoney
from power_grid.power_grid_game_adapter import PowerGridGameAdapter
from power_grid.power_plant import PowerPlant, PowerPlantNumber
from power_grid.power_plant_market import DeckShuffler, PowerPlantMarket
from power_grid.resource_market import ResourceMarket
from power_grid.resource_pool import ResourcePool
from power_grid.simple_types import (
    GamePhase,
    PhaseStatus,
    PlayerColor,
    RequestError,
    Resource,
    SerializedGameState,
)
from power_grid.towns import Towns

MarketSnapshot = tuple[
    int, bool, bool, bool, list[int], list[int], list[int], list[int]
]


def _plant(
    number: int,
    resources: Sequence[Resource] = (Resource.COAL,),
    amount: int = 1,
    cities: int = 1,
) -> PowerPlant:
    return PowerPlant(PowerPlantNumber(number), list(resources), amount, cities)


def _plants(*numbers: int) -> list[PowerPlant]:
    return [_plant(number) for number in numbers]


def _numbers(plants: Sequence[PowerPlant]) -> list[int]:
    return [plant.number.number for plant in plants]


def _reverse_shuffler(cards: list[PowerPlant]) -> None:
    cards.reverse()


def _identity_shuffler(cards: list[PowerPlant]) -> None:
    del cards


def _snapshot(market: PowerPlantMarket) -> MarketSnapshot:
    return (
        market.step,
        market.is_step3,
        market.is_step3_start(),
        market.is_first_power_plant_discounted,
        _numbers(market.power_plant_selection_row1),
        _numbers(market.power_plant_selection_row2),
        _numbers(market.power_plant_deck_above_3rd_step),
        _numbers(market.power_plant_deck_below_3rd_step),
    )


def _make_refill_pattern() -> dict[int, dict[Resource, int]]:
    return {
        1: {Resource.COAL: 1, Resource.OIL: 1, Resource.GARBAGE: 1, Resource.URANIUM: 1},
        2: {Resource.COAL: 2, Resource.OIL: 1, Resource.GARBAGE: 1, Resource.URANIUM: 1},
        3: {Resource.COAL: 1, Resource.OIL: 2, Resource.GARBAGE: 1, Resource.URANIUM: 1},
    }


def _std_market(
    shuffler: DeckShuffler,
    *,
    row1: Sequence[int] = (10, 12, 14, 16),
    above: Sequence[int] = (),
    discounted: bool = True,
) -> PowerPlantMarket:
    return PowerPlantMarket(
        _plants(*row1),
        _plants(18, 20, 22, 24),
        deck_above_step3=_plants(*above),
        deck_below_step3=_plants(30, 35),
        is_first_power_plant_discounted=discounted,
        shuffler=shuffler,
    )


def _make_integration_game(
    market: PowerPlantMarket,
    town_names: Sequence[str],
    edges: Sequence[tuple[str, str, int]],
) -> tuple[
    PowerGridGameAdapter,
    GameController,
    FakeAuctionPhase,
    Towns,
    ResourceMarket,
    CheckAndBumpStep,
]:
    towns = Towns(town_names, Connections(edges))
    pool = ResourcePool(
        [Resource.COAL] * 10
        + [Resource.OIL] * 10
        + [Resource.GARBAGE] * 10
        + [Resource.URANIUM] * 6,
        [],
    )
    resource_market = ResourceMarket(
        pool,
        [Resource.COAL] * 6 + [Resource.OIL] * 4,
        _make_refill_pattern(),
    )
    stepper = CheckAndBumpStep(2, [towns, resource_market, market])
    context = PlayerBoardContext(resource_market, pool, towns)
    boards = {
        PlayerColor.RED: PlayerBoardFacade(
            PlayerMoney(PlayerColor.RED, 200),
            FakePlayerPowerPlants([_plant(40, (), 0, 10)]),
            context,
        ),
        PlayerColor.BLUE: PlayerBoardFacade(
            PlayerMoney(PlayerColor.BLUE, 200),
            FakePlayerPowerPlants([_plant(42, (), 0, 10)]),
            context,
        ),
    }
    auction = FakeAuctionPhase()
    controller = GameController(
        [PlayerColor.RED, PlayerColor.BLUE],
        boards,
        GamePhases(
            auction,
            BuyingResources(boards),
            BuildingHouses(towns, market, boards, end_game_town_count=17),
            Bureaucracy(boards, resource_market, market),
        ),
        GameBoardComponents(market, resource_market, towns, stepper),
    )
    adapter = PowerGridGameAdapter(
        controller, {1: PlayerColor.RED, 2: PlayerColor.BLUE}
    )
    return adapter, controller, auction, towns, resource_market, stepper


class TestPowerPlantMarket(unittest.TestCase):
    def _assert_rows(
        self,
        market: PowerPlantMarket,
        row1: list[int],
        row2: list[int],
    ) -> None:
        self.assertEqual(_numbers(market.power_plant_selection_row1), row1)
        self.assertEqual(_numbers(market.power_plant_selection_row2), row2)

    def test_init_valid_steps_and_unsorted_market_normalization(self) -> None:
        market = PowerPlantMarket(
            _plants(10, 4, 8, 3),
            _plants(9, 5, 7, 6),
            _plants(15, 12),
            _plants(30, 25),
        )
        self.assertEqual(market.step, 1)
        self.assertFalse(market.is_step3)
        self.assertFalse(market.is_step3_start())
        self.assertTrue(market.is_first_power_plant_discounted)
        self._assert_rows(market, [3, 4, 5, 6], [7, 8, 9, 10])
        self.assertEqual(
            _numbers(market.power_plant_deck_above_3rd_step), [15, 12]
        )
        self.assertEqual(
            _numbers(market.power_plant_deck_below_3rd_step), [30, 25]
        )

        step2_drawn = PowerPlantMarket(
            _plants(12, 3, 9, 6),
            _plants(15, 11, 14),
            step=2,
            step3_card_drawn=True,
            is_first_power_plant_discounted=False,
        )
        self.assertEqual(step2_drawn.step, 2)
        self.assertFalse(step2_drawn.is_step3)
        self.assertTrue(step2_drawn.is_step3_start())
        self.assertFalse(step2_drawn.is_first_power_plant_discounted)
        self._assert_rows(step2_drawn, [3, 6, 9, 11], [12, 14, 15])

        step3_market = PowerPlantMarket(
            _plants(25, 10, 30, 15, 20, 12),
            deck_below_step3=_plants(40, 35),
            step=3,
        )
        self.assertEqual(step3_market.step, 3)
        self.assertTrue(step3_market.is_step3)
        self.assertFalse(step3_market.is_step3_start())
        self.assertTrue(step3_market.is_first_power_plant_discounted)
        self._assert_rows(step3_market, [10, 12, 15, 20, 25, 30], [])

        empty_default = PowerPlantMarket([])
        self.assertFalse(empty_default.is_first_power_plant_discounted)
        empty_explicit = PowerPlantMarket(
            [], is_first_power_plant_discounted=False
        )
        self.assertFalse(empty_explicit.is_first_power_plant_discounted)

    def test_init_rejects_invalid_flags_and_empty_discounted(self) -> None:
        invalid_steps: list[int] = [
            0,
            4,
            -1,
            True,
            False,
            cast(int, 1.0),
            cast(int, 2.0),
            cast(int, 3.0),
        ]
        for bad_step in invalid_steps:
            with self.subTest(step=bad_step):
                with self.assertRaises(ValueError):
                    PowerPlantMarket(_plants(3), step=bad_step)

        for bad_drawn in (1, 0, "yes", None):
            with self.subTest(step3_card_drawn=bad_drawn):
                with self.assertRaises(ValueError):
                    PowerPlantMarket(
                        _plants(3), step3_card_drawn=cast(bool, bad_drawn)
                    )

        for bad_discount in (1, 0, "yes"):
            with self.subTest(is_first_power_plant_discounted=bad_discount):
                with self.assertRaises(ValueError):
                    PowerPlantMarket(
                        _plants(3),
                        is_first_power_plant_discounted=cast(
                            bool, bad_discount
                        ),
                    )

        bad_shufflers: tuple[object, ...] = (123, "shuffle", [])
        for bad_shuffler in bad_shufflers:
            with self.subTest(shuffler=bad_shuffler):
                with self.assertRaises(ValueError):
                    PowerPlantMarket(
                        _plants(3),
                        shuffler=cast(DeckShuffler, bad_shuffler),
                    )

        with self.assertRaises(ValueError):
            PowerPlantMarket([], is_first_power_plant_discounted=True)

    def test_init_rejects_invalid_and_duplicate_plants(self) -> None:
        for bad_num in (0, -5, True, False):
            with self.subTest(bad_num=bad_num):
                with self.assertRaises(ValueError):
                    PowerPlantMarket([_plant(bad_num)])
                with self.assertRaises(ValueError):
                    PowerPlantMarket(
                        _plants(3, 4, 5, 6), row2=[_plant(bad_num)]
                    )
                with self.assertRaises(ValueError):
                    PowerPlantMarket(
                        _plants(3), deck_above_step3=[_plant(bad_num)]
                    )
                with self.assertRaises(ValueError):
                    PowerPlantMarket(
                        _plants(3), deck_below_step3=[_plant(bad_num)]
                    )

        duplicate_cases = [
            (_plants(3, 3), [], [], []),
            (_plants(3, 4, 5, 6), _plants(7, 7), [], []),
            (_plants(3), [], _plants(10, 10), []),
            (_plants(3), [], [], _plants(20, 20)),
            (_plants(3, 4, 5, 6), _plants(6, 7), [], []),
            (_plants(3, 4), [], _plants(4), []),
            (_plants(3, 4), [], [], _plants(4)),
            (_plants(3, 4, 5, 6), _plants(7), _plants(7), []),
            (_plants(3, 4, 5, 6), _plants(7), [], _plants(7)),
            (_plants(3), [], _plants(10), _plants(10)),
        ]
        for row1, row2, above, below in duplicate_cases:
            with self.subTest(r1=_numbers(row1), r2=_numbers(row2)):
                with self.assertRaises(ValueError):
                    PowerPlantMarket(row1, row2, above, below)

    def test_init_rejects_invalid_market_structure(self) -> None:
        for step in (1, 2):
            with self.subTest(case="row1_oversized", step=step):
                with self.assertRaises(ValueError):
                    PowerPlantMarket(_plants(3, 4, 5, 6, 7), step=step)

        with self.assertRaises(ValueError):
            PowerPlantMarket(_plants(3, 4, 5, 6), _plants(7, 8, 9, 10, 11))
        with self.assertRaises(ValueError):
            PowerPlantMarket(
                _plants(3, 4, 5, 6),
                _plants(7, 8, 9, 10),
                step3_card_drawn=True,
            )
        with self.assertRaises(ValueError):
            PowerPlantMarket([], _plants(7))
        with self.assertRaises(ValueError):
            PowerPlantMarket(_plants(3, 4, 5), _plants(7))
        with self.assertRaises(ValueError):
            PowerPlantMarket(
                _plants(3, 4, 5, 6),
                _plants(7, 8, 9),
                deck_above_step3=_plants(11),
                step3_card_drawn=True,
            )

        with self.assertRaises(ValueError):
            PowerPlantMarket(_plants(3, 4, 5, 6, 7, 8, 9), step=3)
        with self.assertRaises(ValueError):
            PowerPlantMarket(_plants(3, 4, 5, 6), _plants(7), step=3)
        with self.assertRaises(ValueError):
            PowerPlantMarket(_plants(3, 4), deck_above_step3=_plants(10), step=3)
        with self.assertRaises(ValueError):
            PowerPlantMarket(_plants(3, 4), step=3, step3_card_drawn=True)

    def test_defensive_copies_for_constructor_inputs_and_properties(
        self,
    ) -> None:
        raw_r1 = _plants(3, 4, 5, 6)
        raw_r2 = _plants(7, 8, 9, 10)
        raw_above = _plants(11, 12)
        raw_below = _plants(20, 21)
        market = PowerPlantMarket(raw_r1, raw_r2, raw_above, raw_below)

        raw_r1.append(_plant(99))
        raw_r2.clear()
        raw_above.pop()
        raw_below.append(_plant(88))

        expected = _snapshot(market)
        self._assert_rows(market, [3, 4, 5, 6], [7, 8, 9, 10])
        self.assertEqual(expected[6], [11, 12])
        self.assertEqual(expected[7], [20, 21])

        market.power_plant_selection_row1.clear()
        market.power_plant_selection_row2.append(_plant(77))
        market.power_plant_deck_above_3rd_step.pop()
        market.power_plant_deck_below_3rd_step.clear()
        self.assertEqual(_snapshot(market), expected)

    def test_can_take_power_plant_validation_pricing_and_purity(self) -> None:
        market = PowerPlantMarket(
            _plants(5, 8, 10, 12),
            _plants(15, 18, 20, 25),
            step=1,
            is_first_power_plant_discounted=True,
        )
        before = _snapshot(market)

        for bad_num in (0, -1, True, False, cast(int, 5.0)):
            self.assertIsInstance(
                market.can_take_power_plant(PowerPlantNumber(bad_num), 10),
                RequestError,
            )
            self.assertIsInstance(
                market.can_take_power_plant(PowerPlantNumber(5), bad_num),
                RequestError,
            )

        self.assertIsInstance(
            market.can_take_power_plant(PowerPlantNumber(15), 100), RequestError
        )
        self.assertIsInstance(
            market.can_take_power_plant(PowerPlantNumber(99), 100), RequestError
        )
        self.assertIsNone(market.can_take_power_plant(PowerPlantNumber(5), 1))
        self.assertIsNone(market.can_take_power_plant(PowerPlantNumber(5), 5))
        self.assertIsInstance(
            market.can_take_power_plant(PowerPlantNumber(8), 7), RequestError
        )
        self.assertIsNone(market.can_take_power_plant(PowerPlantNumber(8), 8))
        self.assertIsNone(market.can_take_power_plant(PowerPlantNumber(12), 15))
        self.assertEqual(_snapshot(market), before)

        no_discount = PowerPlantMarket(
            _plants(5, 8, 10, 12),
            _plants(15, 18, 20, 25),
            step=2,
            is_first_power_plant_discounted=False,
        )
        self.assertIsInstance(
            no_discount.can_take_power_plant(PowerPlantNumber(5), 1),
            RequestError,
        )
        self.assertIsInstance(
            no_discount.can_take_power_plant(PowerPlantNumber(5), 4),
            RequestError,
        )
        self.assertIsNone(
            no_discount.can_take_power_plant(PowerPlantNumber(5), 5)
        )
        self.assertIsInstance(
            no_discount.can_take_power_plant(PowerPlantNumber(15), 50),
            RequestError,
        )

        empty = PowerPlantMarket([])
        self.assertIsInstance(
            empty.can_take_power_plant(PowerPlantNumber(3), 10), RequestError
        )

        step3 = PowerPlantMarket(
            _plants(10, 12, 15, 18, 22, 26),
            step=3,
            is_first_power_plant_discounted=True,
        )
        self.assertIsNone(step3.can_take_power_plant(PowerPlantNumber(10), 1))
        self.assertIsNone(step3.can_take_power_plant(PowerPlantNumber(22), 22))
        self.assertIsInstance(
            step3.can_take_power_plant(PowerPlantNumber(26), 25), RequestError
        )
        self.assertIsNone(step3.can_take_power_plant(PowerPlantNumber(26), 26))

    def test_take_power_plant_errors_are_atomic(self) -> None:
        market = PowerPlantMarket(
            _plants(3, 4, 5, 6), _plants(7, 8, 9, 10), _plants(11)
        )
        before = _snapshot(market)
        for bad_num in (0, -1, True, False, cast(int, 3.0), 7, 10, 11, 99):
            with self.subTest(ppn=bad_num):
                with self.assertRaises(ValueError):
                    market.take_power_plant(PowerPlantNumber(bad_num))
                self.assertEqual(_snapshot(market), before)

        with self.assertRaises(ValueError):
            PowerPlantMarket([]).take_power_plant(PowerPlantNumber(3))

    def test_take_discounted_first_clears_discount_and_keeps_smaller_draw(
        self,
    ) -> None:
        plant10 = _plant(10)
        market = PowerPlantMarket(
            [plant10, _plant(12), _plant(14), _plant(16)],
            _plants(18, 20, 22, 24),
            deck_above_step3=_plants(5),
        )
        taken = market.take_power_plant(PowerPlantNumber(10))
        self.assertIs(taken, plant10)
        self.assertFalse(market.is_first_power_plant_discounted)
        self._assert_rows(market, [5, 12, 14, 16], [18, 20, 22, 24])

    def test_take_non_discounted_larger_replacement_keeps_discount(
        self,
    ) -> None:
        market = PowerPlantMarket(
            _plants(10, 12, 14, 16),
            _plants(18, 20, 22, 24),
            deck_above_step3=_plants(15),
        )
        taken = market.take_power_plant(PowerPlantNumber(14))
        self.assertEqual(taken.number.number, 14)
        self.assertTrue(market.is_first_power_plant_discounted)
        self._assert_rows(market, [10, 12, 15, 16], [18, 20, 22, 24])

    def test_take_non_discounted_smaller_replacement_edge_cases(self) -> None:
        # First draw (4) < discounted (10) -> discarded, discount cleared;
        # second draw (7) is ALSO < 10 -> MUST STAY because discount is cleared!
        market = PowerPlantMarket(
            _plants(10, 12, 14, 16),
            _plants(18, 20, 22, 24),
            deck_above_step3=_plants(4, 7, 30),
        )
        taken = market.take_power_plant(PowerPlantNumber(12))
        self.assertEqual(taken.number.number, 12)
        self.assertFalse(market.is_first_power_plant_discounted)
        self._assert_rows(market, [7, 10, 14, 16], [18, 20, 22, 24])
        self.assertEqual(_numbers(market.power_plant_deck_above_3rd_step), [30])

        # Second draw hits empty deck_above -> triggers Step 3 card!
        shuffle_calls: list[list[int]] = []

        def spy_reverse(cards: list[PowerPlant]) -> None:
            shuffle_calls.append(_numbers(cards))
            cards.reverse()

        trigger = PowerPlantMarket(
            _plants(10, 12, 14, 16),
            _plants(18, 20, 22, 24),
            deck_above_step3=_plants(6),
            deck_below_step3=_plants(30, 35),
            shuffler=spy_reverse,
        )
        trigger.take_power_plant(PowerPlantNumber(16))
        self.assertFalse(trigger.is_first_power_plant_discounted)
        self.assertTrue(trigger.is_step3_start())
        self.assertEqual(shuffle_calls, [[30, 35]])
        self._assert_rows(trigger, [10, 12, 14, 18], [20, 22, 24])
        self.assertEqual(
            _numbers(trigger.power_plant_deck_below_3rd_step), [35, 30]
        )

    def test_take_triggers_step3_keeps_discount_and_draws_from_deck_below(
        self,
    ) -> None:
        shuffle_calls = 0

        def spy_reverse(cards: list[PowerPlant]) -> None:
            nonlocal shuffle_calls
            shuffle_calls += 1
            cards.reverse()

        market = PowerPlantMarket(
            _plants(10, 12, 14, 16),
            _plants(18, 20, 22, 24),
            deck_above_step3=[],
            deck_below_step3=_plants(28, 32, 36),
            shuffler=spy_reverse,
        )
        market.take_power_plant(PowerPlantNumber(14))
        self.assertTrue(market.is_step3_start())
        self.assertTrue(market.is_first_power_plant_discounted)
        self.assertEqual(shuffle_calls, 1)
        self._assert_rows(market, [10, 12, 16, 18], [20, 22, 24])
        self.assertEqual(
            _numbers(market.power_plant_deck_below_3rd_step), [36, 32, 28]
        )

        # Second buy still in Phase 2 draws from shuffled deck_below
        market.take_power_plant(PowerPlantNumber(16))
        self.assertEqual(shuffle_calls, 1)
        self.assertTrue(market.is_first_power_plant_discounted)
        self._assert_rows(market, [10, 12, 18, 20], [22, 24, 36])
        self.assertEqual(
            _numbers(market.power_plant_deck_below_3rd_step), [32, 28]
        )

        # start_step3 must not re-shuffle
        market.start_step3()
        self.assertEqual(shuffle_calls, 1)
        self.assertTrue(market.is_step3)
        self._assert_rows(market, [12, 18, 20, 22, 24, 36], [])

    def test_take_power_plant_step3_draws_and_shrinks_when_empty(self) -> None:
        market = PowerPlantMarket(
            _plants(10, 12, 14, 16, 18, 20),
            deck_below_step3=_plants(7, 25),
            step=3,
            is_first_power_plant_discounted=True,
        )
        taken = market.take_power_plant(PowerPlantNumber(20))
        self.assertEqual(taken.number.number, 20)
        self.assertFalse(market.is_first_power_plant_discounted)
        self._assert_rows(market, [10, 12, 14, 16, 18, 25], [])
        self.assertEqual(market.power_plant_deck_below_3rd_step, [])

        for number in (10, 12, 14, 16, 18, 25):
            market.take_power_plant(PowerPlantNumber(number))
        self._assert_rows(market, [], [])
        self.assertFalse(market.is_first_power_plant_discounted)

    def test_remove_discounted_power_plant_idempotency_and_step3(self) -> None:
        market = PowerPlantMarket(
            _plants(3, 4, 5, 6),
            _plants(7, 8, 9, 10),
            deck_above_step3=_plants(11),
        )
        market.remove_discounted_power_plant()
        self.assertFalse(market.is_first_power_plant_discounted)
        self._assert_rows(market, [4, 5, 6, 7], [8, 9, 10, 11])

        after_first = _snapshot(market)
        market.remove_discounted_power_plant()
        self.assertEqual(_snapshot(market), after_first)

        empty = PowerPlantMarket([])
        empty.remove_discounted_power_plant()
        self.assertFalse(empty.is_first_power_plant_discounted)

        trigger = PowerPlantMarket(
            _plants(3, 4, 5, 6),
            _plants(7, 8, 9, 10),
            deck_above_step3=[],
            deck_below_step3=_plants(20, 25),
            shuffler=_reverse_shuffler,
        )
        trigger.remove_discounted_power_plant()
        self.assertFalse(trigger.is_first_power_plant_discounted)
        self.assertTrue(trigger.is_step3_start())
        self._assert_rows(trigger, [4, 5, 6, 7], [8, 9, 10])
        self.assertEqual(
            _numbers(trigger.power_plant_deck_below_3rd_step), [25, 20]
        )

        single = PowerPlantMarket(
            _plants(3), step=3, is_first_power_plant_discounted=True
        )
        single.remove_discounted_power_plant()
        self._assert_rows(single, [], [])
        self.assertFalse(single.is_first_power_plant_discounted)

    def test_remove_power_plants_cheaper_than_validation_and_boundaries(
        self,
    ) -> None:
        market = PowerPlantMarket(
            _plants(4, 6, 8, 10),
            _plants(12, 14, 16, 18),
            deck_above_step3=_plants(20),
        )
        before = _snapshot(market)
        for bad_value in (-1, -50, True, False, cast(int, 5.0)):
            with self.subTest(value=bad_value):
                with self.assertRaises(ValueError):
                    market.remove_power_plants_cheaper_than(bad_value)
                self.assertEqual(_snapshot(market), before)

        market.remove_power_plants_cheaper_than(0)
        market.remove_power_plants_cheaper_than(3)
        self.assertEqual(_snapshot(market), before)
        self.assertTrue(market.is_first_power_plant_discounted)

        market.remove_power_plants_cheaper_than(4)
        self.assertFalse(market.is_first_power_plant_discounted)
        self._assert_rows(market, [6, 8, 10, 12], [14, 16, 18, 20])

    def test_remove_cheaper_than_chain_row2_step3_and_exhaustion(self) -> None:
        shuffle_calls = 0

        def spy_reverse(cards: list[PowerPlant]) -> None:
            nonlocal shuffle_calls
            shuffle_calls += 1
            cards.reverse()

        market = PowerPlantMarket(
            _plants(3, 4, 6, 10),
            _plants(9, 11, 14, 16),
            deck_above_step3=_plants(5, 8),
            deck_below_step3=_plants(12, 7),
            shuffler=spy_reverse,
        )
        market.remove_power_plants_cheaper_than(9)
        self.assertEqual(shuffle_calls, 1)
        self.assertTrue(market.is_step3_start())
        self.assertFalse(market.is_first_power_plant_discounted)
        self._assert_rows(market, [10, 11, 12, 14], [16])
        self.assertEqual(market.power_plant_deck_below_3rd_step, [])

        step3 = PowerPlantMarket(
            _plants(5, 7, 9), deck_below_step3=_plants(6, 8), step=3
        )
        step3.remove_power_plants_cheaper_than(10)
        self._assert_rows(step3, [], [])
        self.assertEqual(step3.power_plant_deck_below_3rd_step, [])
        self.assertFalse(step3.is_first_power_plant_discounted)

    def test_prepare_next_turn_steps_1_2_and_step3_trigger(self) -> None:
        market = PowerPlantMarket(
            _plants(3, 4, 5, 6),
            _plants(7, 8, 9, 10),
            deck_above_step3=_plants(11, 12),
            deck_below_step3=_plants(20),
            is_first_power_plant_discounted=False,
        )
        market.prepare_next_turn()
        self.assertTrue(market.is_first_power_plant_discounted)
        self._assert_rows(market, [3, 4, 5, 6], [7, 8, 9, 11])
        self.assertEqual(_numbers(market.power_plant_deck_above_3rd_step), [12])
        self.assertEqual(
            _numbers(market.power_plant_deck_below_3rd_step), [20, 10]
        )

        # Row 2 empty -> highest plant in row 1 moves to deck_below
        row1_only = PowerPlantMarket(
            _plants(3, 5, 9),
            deck_above_step3=_plants(7),
            deck_below_step3=_plants(30),
            is_first_power_plant_discounted=False,
        )
        row1_only.prepare_next_turn()
        self._assert_rows(row1_only, [3, 5, 7], [])
        self.assertEqual(
            _numbers(row1_only.power_plant_deck_below_3rd_step), [30, 9]
        )
        self.assertTrue(row1_only.is_first_power_plant_discounted)

        # Empty deck_above: highest plant (10) appended BEFORE shuffle!
        shuffled_inputs: list[list[int]] = []

        def spy_reverse(cards: list[PowerPlant]) -> None:
            shuffled_inputs.append(_numbers(cards))
            cards.reverse()

        trigger = PowerPlantMarket(
            _plants(3, 4, 5, 6),
            _plants(7, 8, 9, 10),
            deck_above_step3=[],
            deck_below_step3=_plants(20, 25),
            step=2,
            is_first_power_plant_discounted=False,
            shuffler=spy_reverse,
        )
        trigger.prepare_next_turn()
        self.assertEqual(shuffled_inputs, [[20, 25, 10]])
        self.assertTrue(trigger.is_step3_start())
        self.assertTrue(trigger.is_first_power_plant_discounted)
        self._assert_rows(trigger, [3, 4, 5, 6], [7, 8, 9])
        self.assertEqual(
            _numbers(trigger.power_plant_deck_below_3rd_step), [10, 25, 20]
        )

        # Step 1/2 when step3_card_drawn is ALREADY True
        already_drawn = PowerPlantMarket(
            _plants(3, 4, 5, 6),
            _plants(7, 8, 9),
            deck_below_step3=_plants(20, 21),
            step=2,
            step3_card_drawn=True,
            is_first_power_plant_discounted=False,
        )
        already_drawn.prepare_next_turn()
        self.assertTrue(already_drawn.is_step3_start())
        self.assertTrue(already_drawn.is_first_power_plant_discounted)
        self._assert_rows(already_drawn, [3, 4, 5, 6], [7, 8, 20])
        self.assertEqual(
            _numbers(already_drawn.power_plant_deck_below_3rd_step), [21, 9]
        )

        empty = PowerPlantMarket([])
        empty.prepare_next_turn()
        self.assertFalse(empty.is_first_power_plant_discounted)

    def test_prepare_next_turn_step3_removes_lowest_and_handles_exhaustion(
        self,
    ) -> None:
        market = PowerPlantMarket(
            _plants(10, 12, 14, 16, 18, 20),
            deck_below_step3=_plants(25),
            step=3,
            is_first_power_plant_discounted=False,
        )
        market.prepare_next_turn()
        self.assertTrue(market.is_first_power_plant_discounted)
        self._assert_rows(market, [12, 14, 16, 18, 20, 25], [])
        self.assertEqual(market.power_plant_deck_below_3rd_step, [])

        single = PowerPlantMarket(
            _plants(30), step=3, is_first_power_plant_discounted=False
        )
        single.prepare_next_turn()
        self._assert_rows(single, [], [])
        self.assertFalse(single.is_first_power_plant_discounted)

    def test_start_step2_transitions_trigger_and_no_double_removal(
        self,
    ) -> None:
        market = PowerPlantMarket(
            _plants(3, 4, 5, 6),
            _plants(7, 8, 9, 10),
            deck_above_step3=_plants(11),
        )
        market.start_step2()
        self.assertEqual(market.step, 2)
        self.assertFalse(market.is_first_power_plant_discounted)
        self._assert_rows(market, [4, 5, 6, 7], [8, 9, 10, 11])

        before_step2 = _snapshot(market)
        with self.assertRaises(ValueError):
            market.start_step2()
        self.assertEqual(_snapshot(market), before_step2)

        step3_market = PowerPlantMarket(_plants(10, 12), step=3)
        before_step3 = _snapshot(step3_market)
        with self.assertRaises(ValueError):
            step3_market.start_step2()
        self.assertEqual(_snapshot(step3_market), before_step3)

        # Drawing Step 3 card during start_step2
        trigger = PowerPlantMarket(
            _plants(3, 4, 5, 6),
            _plants(7, 8, 9, 10),
            deck_above_step3=[],
            deck_below_step3=_plants(20, 25),
            shuffler=_reverse_shuffler,
        )
        trigger.start_step2()
        self.assertEqual(trigger.step, 2)
        self.assertTrue(trigger.is_step3_start())
        self._assert_rows(trigger, [4, 5, 6, 7], [8, 9, 10])
        self.assertEqual(
            _numbers(trigger.power_plant_deck_below_3rd_step), [25, 20]
        )

        # When step3_card_drawn is ALREADY True, no double removal
        already_drawn = PowerPlantMarket(
            _plants(3, 4, 5, 6),
            _plants(7, 8, 9),
            deck_below_step3=_plants(20),
            step=1,
            step3_card_drawn=True,
            is_first_power_plant_discounted=True,
        )
        already_drawn.start_step2()
        self.assertEqual(already_drawn.step, 2)
        self.assertTrue(already_drawn.is_step3_start())
        self.assertTrue(already_drawn.is_first_power_plant_discounted)
        self._assert_rows(already_drawn, [3, 4, 5, 6], [7, 8, 9])

        empty = PowerPlantMarket([])
        empty.start_step2()
        self.assertEqual(empty.step, 2)

    def test_start_step3_after_card_drawn_vs_manual_and_discount(self) -> None:
        already_step3 = PowerPlantMarket(_plants(10, 12), step=3)
        before = _snapshot(already_step3)
        with self.assertRaises(ValueError):
            already_step3.start_step3()
        self.assertEqual(_snapshot(already_step3), before)

        shuffle_calls = 0

        def spy_reverse(cards: list[PowerPlant]) -> None:
            nonlocal shuffle_calls
            shuffle_calls += 1
            cards.reverse()

        after_drawn = PowerPlantMarket(
            _plants(3, 4, 5, 6),
            _plants(7, 8, 9),
            deck_below_step3=_plants(20, 21),
            step=2,
            step3_card_drawn=True,
            is_first_power_plant_discounted=True,
            shuffler=spy_reverse,
        )
        after_drawn.start_step3()
        self.assertEqual(shuffle_calls, 0)
        self.assertTrue(after_drawn.is_step3)
        self.assertFalse(after_drawn.is_step3_start())
        self.assertTrue(after_drawn.is_first_power_plant_discounted)
        self._assert_rows(after_drawn, [4, 5, 6, 7, 8, 9], [])

        # Manual start_step3 with 8 plants
        manual_inputs: list[list[int]] = []

        def spy_manual(cards: list[PowerPlant]) -> None:
            manual_inputs.append(_numbers(cards))
            cards.reverse()

        manual8 = PowerPlantMarket(
            _plants(3, 4, 5, 6),
            _plants(7, 8, 9, 10),
            deck_above_step3=_plants(11, 12),
            deck_below_step3=_plants(20),
            step=1,
            shuffler=spy_manual,
        )
        manual8.start_step3()
        self.assertEqual(manual_inputs, [[20, 11, 12, 10]])
        self.assertTrue(manual8.is_step3)
        self._assert_rows(manual8, [4, 5, 6, 7, 8, 9], [])
        self.assertEqual(manual8.power_plant_deck_above_3rd_step, [])
        self.assertEqual(
            _numbers(manual8.power_plant_deck_below_3rd_step), [10, 12, 11, 20]
        )

        # Manual start_step3 with 7, 4, 1, and 0 plants
        manual7 = PowerPlantMarket(
            _plants(3, 4, 5, 6),
            _plants(7, 8, 9),
            deck_above_step3=_plants(11),
            step=2,
            shuffler=_identity_shuffler,
        )
        manual7.start_step3()
        self._assert_rows(manual7, [4, 5, 6, 7, 8, 9], [])
        self.assertEqual(_numbers(manual7.power_plant_deck_below_3rd_step), [11])

        manual4 = PowerPlantMarket(
            _plants(3, 4, 5, 6), step=2, shuffler=_identity_shuffler
        )
        manual4.start_step3()
        self._assert_rows(manual4, [4, 5, 6], [])

        manual1 = PowerPlantMarket(
            _plants(3),
            step=2,
            is_first_power_plant_discounted=True,
            shuffler=_identity_shuffler,
        )
        manual1.start_step3()
        self._assert_rows(manual1, [], [])
        self.assertFalse(manual1.is_first_power_plant_discounted)

        manual0 = PowerPlantMarket([], step=2, shuffler=_identity_shuffler)
        manual0.start_step3()
        self._assert_rows(manual0, [], [])
        self.assertFalse(manual0.is_first_power_plant_discounted)

    def test_adversarial_corrupting_shufflers_raise_and_preserve_atomicity(
        self,
    ) -> None:
        def drop_card(cards: list[PowerPlant]) -> None:
            if cards:
                cards.pop()

        def duplicate_card(cards: list[PowerPlant]) -> None:
            if len(cards) >= 2:
                cards[-1] = cards[0]
            elif cards:
                cards.append(cards[0])

        def replace_with_same_number(cards: list[PowerPlant]) -> None:
            if cards:
                original = cards[0]
                cards[0] = PowerPlant(
                    PowerPlantNumber(original.number.number),
                    list(original.accepted_resources),
                    original.resource_amount,
                    original.number_of_cities,
                )

        def explode(cards: list[PowerPlant]) -> None:
            del cards
            raise RuntimeError("shuffler exploded")

        bad_shufflers: list[tuple[str, DeckShuffler, type[Exception]]] = [
            ("drop", drop_card, ValueError),
            ("duplicate", duplicate_card, ValueError),
            ("replace_same_number", replace_with_same_number, ValueError),
            ("runtime_error", explode, RuntimeError),
        ]

        scenarios: list[
            tuple[
                str,
                Callable[[DeckShuffler], PowerPlantMarket],
                Callable[[PowerPlantMarket], object],
            ]
        ] = [
            (
                "take_power_plant_empty_above",
                _std_market,
                lambda m: m.take_power_plant(PowerPlantNumber(14)),
            ),
            (
                "take_power_plant_double_draw_discount",
                lambda s: _std_market(s, above=(5,)),
                lambda m: m.take_power_plant(PowerPlantNumber(14)),
            ),
            (
                "remove_discounted_power_plant",
                _std_market,
                lambda m: m.remove_discounted_power_plant(),
            ),
            (
                "remove_power_plants_cheaper_than",
                lambda s: _std_market(s, row1=(3, 5, 14, 16), above=(4,)),
                lambda m: m.remove_power_plants_cheaper_than(6),
            ),
            (
                "prepare_next_turn",
                lambda s: _std_market(s, discounted=False),
                lambda m: m.prepare_next_turn(),
            ),
            ("start_step2", _std_market, lambda m: m.start_step2()),
            (
                "start_step3_manual",
                lambda s: _std_market(s, above=(26,)),
                lambda m: m.start_step3(),
            ),
        ]

        for shuffler_name, shuffler, exc_type in bad_shufflers:
            for scenario_name, factory, action in scenarios:
                with self.subTest(
                    shuffler=shuffler_name, scenario=scenario_name
                ):
                    market = factory(shuffler)
                    before = _snapshot(market)
                    with self.assertRaises(exc_type):
                        action(market)
                    self.assertEqual(_snapshot(market), before)

    def test_flaky_shuffler_recovery_after_transient_failure(self) -> None:
        def make_flaky_reverse() -> DeckShuffler:
            failed_once = False

            def shuffler(cards: list[PowerPlant]) -> None:
                nonlocal failed_once
                if not failed_once:
                    failed_once = True
                    raise RuntimeError("transient shuffler failure")
                cards.reverse()

            return shuffler

        # 1) Recovery on take_power_plant double-draw discount case
        m_take = _std_market(make_flaky_reverse(), above=(5,))
        before_take = _snapshot(m_take)
        with self.assertRaises(RuntimeError):
            m_take.take_power_plant(PowerPlantNumber(14))
        self.assertEqual(_snapshot(m_take), before_take)
        taken = m_take.take_power_plant(PowerPlantNumber(14))
        self.assertEqual(taken.number.number, 14)
        self.assertFalse(m_take.is_first_power_plant_discounted)
        self.assertTrue(m_take.is_step3_start())
        self._assert_rows(m_take, [10, 12, 16, 18], [20, 22, 24])
        self.assertEqual(
            _numbers(m_take.power_plant_deck_below_3rd_step), [35, 30]
        )

        # 2) Recovery on manual start_step3
        m_step3 = _std_market(make_flaky_reverse(), above=(26,))
        before_s3 = _snapshot(m_step3)
        with self.assertRaises(RuntimeError):
            m_step3.start_step3()
        self.assertEqual(_snapshot(m_step3), before_s3)
        m_step3.start_step3()
        self.assertTrue(m_step3.is_step3)
        self._assert_rows(m_step3, [12, 14, 16, 18, 20, 22], [])
        self.assertEqual(m_step3.power_plant_deck_above_3rd_step, [])
        self.assertEqual(
            _numbers(m_step3.power_plant_deck_below_3rd_step), [24, 26, 35, 30]
        )

        # 3) Recovery on start_step2 & prepare_next_turn
        m_step2 = _std_market(make_flaky_reverse())
        with self.assertRaises(RuntimeError):
            m_step2.start_step2()
        self.assertEqual(m_step2.step, 1)
        m_step2.start_step2()
        self.assertEqual(m_step2.step, 2)
        self.assertTrue(m_step2.is_step3_start())
        self._assert_rows(m_step2, [12, 14, 16, 18], [20, 22, 24])

        m_prep = _std_market(make_flaky_reverse(), discounted=False)
        before_prep = _snapshot(m_prep)
        with self.assertRaises(RuntimeError):
            m_prep.prepare_next_turn()
        self.assertEqual(_snapshot(m_prep), before_prep)
        m_prep.prepare_next_turn()
        self.assertTrue(m_prep.is_step3_start())
        self.assertTrue(m_prep.is_first_power_plant_discounted)
        self._assert_rows(m_prep, [10, 12, 14, 16], [18, 20, 22])
        self.assertEqual(
            _numbers(m_prep.power_plant_deck_below_3rd_step), [24, 35, 30]
        )

    def test_small_market_prepare_next_turn_and_step1_to_step3(self) -> None:
        # prepare_next_turn on small Step 1/2 market (empty row2 & deck_above)
        small_two = PowerPlantMarket(
            _plants(5, 9),
            deck_below_step3=_plants(20),
            is_first_power_plant_discounted=False,
            shuffler=_reverse_shuffler,
        )
        small_two.prepare_next_turn()
        self.assertTrue(small_two.is_step3_start())
        self.assertTrue(small_two.is_first_power_plant_discounted)
        self._assert_rows(small_two, [5], [])
        self.assertEqual(
            _numbers(small_two.power_plant_deck_below_3rd_step), [9, 20]
        )

        small_one = PowerPlantMarket(
            _plants(5),
            step=2,
            is_first_power_plant_discounted=False,
            shuffler=_reverse_shuffler,
        )
        small_one.prepare_next_turn()
        self.assertTrue(small_one.is_step3_start())
        self.assertFalse(small_one.is_first_power_plant_discounted)
        self._assert_rows(small_one, [], [])
        self.assertEqual(_numbers(small_one.power_plant_deck_below_3rd_step), [5])

        # Direct start_step3() from Step 1 with step3_card_drawn=True vs False
        calls_drawn = 0

        def spy_drawn(cards: list[PowerPlant]) -> None:
            nonlocal calls_drawn
            calls_drawn += 1
            cards.reverse()

        step1_drawn = PowerPlantMarket(
            _plants(3, 4, 5, 6),
            _plants(7, 8, 9),
            deck_below_step3=_plants(20, 25),
            step=1,
            step3_card_drawn=True,
            shuffler=spy_drawn,
        )
        step1_drawn.start_step3()
        self.assertEqual(calls_drawn, 0)
        self.assertTrue(step1_drawn.is_step3)
        self._assert_rows(step1_drawn, [4, 5, 6, 7, 8, 9], [])

        calls_manual = 0

        def spy_manual(cards: list[PowerPlant]) -> None:
            nonlocal calls_manual
            calls_manual += 1
            cards.reverse()

        step1_manual = PowerPlantMarket(
            _plants(3, 4, 5, 6),
            _plants(7, 8, 9, 10),
            deck_above_step3=_plants(11),
            deck_below_step3=_plants(20),
            step=1,
            step3_card_drawn=False,
            shuffler=spy_manual,
        )
        step1_manual.start_step3()
        self.assertEqual(calls_manual, 1)
        self.assertTrue(step1_manual.is_step3)
        self._assert_rows(step1_manual, [4, 5, 6, 7, 8, 9], [])
        self.assertEqual(
            _numbers(step1_manual.power_plant_deck_below_3rd_step), [10, 11, 20]
        )

    def test_to_string_across_full_lifecycle(self) -> None:
        market = PowerPlantMarket(
            _plants(3, 4, 5, 6),
            _plants(7, 8, 9, 10),
            deck_above_step3=[],
            deck_below_step3=_plants(20, 25),
            shuffler=_reverse_shuffler,
        )
        self.assertEqual(
            json.loads(market.to_string()),
            {
                "step": 1,
                "is_step3": False,
                "is_step3_start": False,
                "is_first_power_plant_discounted": True,
                "row1": [3, 4, 5, 6],
                "row2": [7, 8, 9, 10],
                "deck_above_step3_count": 0,
                "deck_below_step3_count": 2,
            },
        )

        market.take_power_plant(PowerPlantNumber(4))
        self.assertEqual(
            json.loads(market.to_string()),
            {
                "step": 1,
                "is_step3": False,
                "is_step3_start": True,
                "is_first_power_plant_discounted": True,
                "row1": [3, 5, 6, 7],
                "row2": [8, 9, 10],
                "deck_above_step3_count": 0,
                "deck_below_step3_count": 2,
            },
        )

        market.start_step3()
        self.assertEqual(
            json.loads(market.to_string()),
            {
                "step": 3,
                "is_step3": True,
                "is_step3_start": False,
                "is_first_power_plant_discounted": True,
                "row1": [5, 6, 7, 8, 9, 10],
                "row2": [],
                "deck_above_step3_count": 0,
                "deck_below_step3_count": 2,
            },
        )

    def test_integration_building_houses_step2_draws_step3_in_controller(
        self,
    ) -> None:
        town_names = [f"T{idx}" for idx in range(7)]
        edges = [(town_names[idx], town_names[idx + 1], 1) for idx in range(6)]
        market = PowerPlantMarket(
            _plants(3, 5, 8, 10),
            _plants(12, 14, 16, 18),
            deck_above_step3=_plants(20, 22),
            deck_below_step3=_plants(30, 35),
            shuffler=_reverse_shuffler,
        )
        adapter, controller, auction, towns, resource_market, stepper = (
            _make_integration_game(market, town_names, edges)
        )

        auction.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsInstance(
            adapter.do_not_want_power_plant(1), SerializedGameState
        )
        self.assertIsInstance(adapter.buy_resources(1, ""), SerializedGameState)
        self.assertIsInstance(adapter.buy_resources(2, ""), SerializedGameState)
        self.assertEqual(controller.game_phase, GamePhase.BUY_HOUSES)

        # RED buys 7 cities -> remove_power_plants_cheaper_than(7) removes 3, 5
        self.assertIsInstance(
            adapter.buy_houses(1, town_names), SerializedGameState
        )
        self._assert_rows(market, [8, 10, 12, 14], [16, 18, 20, 22])
        self.assertEqual(market.power_plant_deck_above_3rd_step, [])

        # End of Phase 4: start_step2 removes 8 & draws Step 3 card ->
        # GameController immediately transitions to Step 3!
        self.assertIsInstance(adapter.buy_houses(2, []), SerializedGameState)
        self.assertEqual(controller.game_phase, GamePhase.BUREAUCRACY)
        self.assertEqual(stepper.get_step(), 3)
        self.assertEqual(towns.step, 3)
        self.assertTrue(market.is_step3)
        self.assertFalse(market.is_step3_start())
        self._assert_rows(market, [12, 14, 16, 18, 20, 22], [])
        self.assertEqual(
            _numbers(market.power_plant_deck_below_3rd_step), [35, 30]
        )
        self.assertEqual(json.loads(resource_market.to_string())["coal"], 6)

    def test_integration_direct_step1_to_step3_jump_no_double_removal(
        self,
    ) -> None:
        towns = Towns(["Alpha", "Beta"], Connections([("Alpha", "Beta", 5)]))
        pool = ResourcePool([Resource.COAL] * 10, [])
        resource_market = ResourceMarket(
            pool, [Resource.COAL] * 3, _make_refill_pattern()
        )
        shuffle_calls = 0

        def spy_reverse(cards: list[PowerPlant]) -> None:
            nonlocal shuffle_calls
            shuffle_calls += 1
            cards.reverse()

        market = PowerPlantMarket(
            _plants(3, 4, 5, 6),
            _plants(7, 8, 9, 10),
            deck_above_step3=[],
            deck_below_step3=_plants(20, 25),
            shuffler=spy_reverse,
        )
        stepper = CheckAndBumpStep(3, [towns, resource_market, market])

        market.take_power_plant(PowerPlantNumber(4))
        self.assertTrue(market.is_step3_start())
        self.assertEqual(shuffle_calls, 1)

        self.assertTrue(stepper.check_and_bump_to_step3(market.is_step3_start()))
        self.assertEqual(stepper.get_step(), 3)
        self.assertEqual(towns.step, 3)
        self.assertTrue(market.is_step3)
        self.assertEqual(shuffle_calls, 1)
        self._assert_rows(market, [5, 6, 7, 8, 9, 10], [])

    def test_integration_bureaucracy_triggers_step3_with_discount_active(
        self,
    ) -> None:
        shuffled_inputs: list[list[int]] = []

        def spy_reverse(cards: list[PowerPlant]) -> None:
            shuffled_inputs.append(_numbers(cards))
            cards.reverse()

        market = PowerPlantMarket(
            _plants(3, 4, 5, 6),
            _plants(7, 8, 9, 10),
            deck_above_step3=[],
            deck_below_step3=_plants(20, 25),
            shuffler=spy_reverse,
        )
        adapter, controller, auction, towns, _res_market, stepper = (
            _make_integration_game(
                market, ["Alpha", "Beta"], [("Alpha", "Beta", 5)]
            )
        )

        auction.next_result = PhaseStatus.PHASE_ENDS
        self.assertIsInstance(
            adapter.do_not_want_power_plant(1), SerializedGameState
        )
        self.assertIsInstance(adapter.buy_resources(1, ""), SerializedGameState)
        self.assertIsInstance(adapter.buy_resources(2, ""), SerializedGameState)
        self.assertIsInstance(adapter.buy_houses(1, []), SerializedGameState)
        self.assertIsInstance(adapter.buy_houses(2, []), SerializedGameState)
        self.assertEqual(controller.game_phase, GamePhase.BUREAUCRACY)

        self.assertIsInstance(
            adapter.use_power_plants(2, [], ""), SerializedGameState
        )
        self.assertIsInstance(
            adapter.use_power_plants(1, [], ""), SerializedGameState
        )

        self.assertEqual(controller.game_phase, GamePhase.AUCTION_POWER_PLANTS)
        self.assertEqual(stepper.get_step(), 3)
        self.assertEqual(towns.step, 3)
        self.assertTrue(market.is_step3)
        self.assertFalse(market.is_step3_start())
        self.assertEqual(shuffled_inputs, [[20, 25, 10]])
        self._assert_rows(market, [4, 5, 6, 7, 8, 9], [])
        self.assertEqual(
            _numbers(market.power_plant_deck_below_3rd_step), [10, 25, 20]
        )
        self.assertTrue(market.is_first_power_plant_discounted)
        self.assertIsNone(market.can_take_power_plant(PowerPlantNumber(4), 1))
        self.assertIsNone(market.can_take_power_plant(PowerPlantNumber(9), 9))


if __name__ == "__main__":
    unittest.main()
