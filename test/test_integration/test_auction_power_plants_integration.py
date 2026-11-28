# pylint: disable=too-many-public-methods
from __future__ import annotations

import json
import unittest
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from power_grid.auction_power_plants import AuctionPowerPlants
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
from power_grid.player_power_plants import PlayerPowerPlants
from power_grid.power_grid_game_adapter import PowerGridGameAdapter
from power_grid.power_plant import PowerPlant, PowerPlantNumber
from power_grid.power_plant_market import PowerPlantMarket
from power_grid.resource_market import ResourceMarket
from power_grid.resource_pool import ResourcePool
from power_grid.simple_types import (
    PlayerColor,
    RequestError,
    Resource,
    SerializedGameState,
)
from power_grid.towns import Towns


def _plant(
    number: int,
    resources: Sequence[Resource],
    amount: int,
    cities: int,
) -> PowerPlant:
    return PowerPlant(PowerPlantNumber(number), list(resources), amount, cities)


def _reverse_shuffler(cards: list[PowerPlant]) -> None:
    cards.reverse()


def _refill_pattern() -> dict[int, dict[Resource, int]]:
    rows = {
        1: (4, 2, 1, 1),
        2: (5, 3, 2, 1),
        3: (3, 4, 3, 1),
    }
    return {
        step: {
            Resource.COAL: coal,
            Resource.OIL: oil,
            Resource.GARBAGE: garbage,
            Resource.URANIUM: uranium,
        }
        for step, (coal, oil, garbage, uranium) in rows.items()
    }


@dataclass(frozen=True)
class GameConfig:
    money_by_player: Mapping[PlayerColor, int] | None = None
    default_money: int = 50
    max_plants: int = 3
    is_first_round: bool = True


@dataclass
class FullGameSetup:
    adapter: PowerGridGameAdapter
    auction: AuctionPowerPlants
    plant_market: PowerPlantMarket
    pool: ResourcePool
    towns: Towns
    boards: dict[PlayerColor, PlayerBoardFacade]


def _build_resources_and_towns() -> tuple[ResourcePool, ResourceMarket, Towns]:
    pool = ResourcePool(
        resources=(
            [Resource.COAL] * 10
            + [Resource.OIL] * 12
            + [Resource.GARBAGE] * 18
            + [Resource.URANIUM] * 10
        ),
        storage_space=[],
    )
    resource_market = ResourceMarket(
        pool=pool,
        starting_resources=(
            [Resource.COAL] * 18
            + [Resource.OIL] * 12
            + [Resource.GARBAGE] * 6
            + [Resource.URANIUM] * 2
        ),
        refilling_pattern=_refill_pattern(),
    )
    connections = Connections(
        [
            ("A", "B", 5),
            ("B", "C", 5),
            ("C", "D", 4),
            ("D", "E", 3),
            ("E", "F", 2),
        ]
    )
    towns = Towns(["A", "B", "C", "D", "E", "F"], connections)
    return pool, resource_market, towns


def _build_full_game(
    order: Sequence[PlayerColor],
    plant_market: PowerPlantMarket,
    config: GameConfig = GameConfig(),
) -> FullGameSetup:
    pool, resource_market, towns = _build_resources_and_towns()
    context = PlayerBoardContext(resource_market, pool, towns)
    money_map = config.money_by_player or {}
    boards = {
        color: PlayerBoardFacade(
            PlayerMoney(color, money_map.get(color, config.default_money)),
            PlayerPowerPlants(max_plants=config.max_plants),
            context,
        )
        for color in order
    }
    auction = AuctionPowerPlants(
        plant_market, boards, is_first_round=config.is_first_round
    )
    controller = GameController(
        order,
        boards,
        GamePhases(
            auction,
            BuyingResources(boards),
            BuildingHouses(towns, plant_market, boards),
            Bureaucracy(boards, resource_market, plant_market),
        ),
        GameBoardComponents(
            plant_market,
            resource_market,
            towns,
            CheckAndBumpStep(
                len(order), [resource_market, towns, plant_market]
            ),
        ),
    )
    adapter = PowerGridGameAdapter(
        controller, {idx + 1: color for idx, color in enumerate(order)}
    )
    return FullGameSetup(
        adapter=adapter,
        auction=auction,
        plant_market=plant_market,
        pool=pool,
        towns=towns,
        boards=boards,
    )


def _standard_two_round_market() -> PowerPlantMarket:
    return PowerPlantMarket(
        row1=[
            _plant(3, [Resource.OIL], 2, 1),
            _plant(4, [Resource.COAL], 2, 1),
            _plant(5, [Resource.COAL, Resource.OIL], 2, 1),
            _plant(6, [Resource.GARBAGE], 1, 1),
        ],
        row2=[
            _plant(7, [Resource.OIL], 3, 2),
            _plant(8, [Resource.COAL], 3, 2),
            _plant(9, [Resource.OIL], 1, 1),
            _plant(10, [Resource.COAL], 2, 2),
        ],
        deck_above_step3=[
            _plant(11, [Resource.URANIUM], 1, 2),
            _plant(12, [Resource.COAL, Resource.OIL], 2, 2),
            _plant(13, [], 0, 1),
            _plant(14, [Resource.GARBAGE], 2, 2),
            _plant(15, [Resource.COAL], 2, 3),
            _plant(16, [Resource.OIL], 2, 3),
            _plant(17, [Resource.URANIUM], 1, 2),
        ],
        deck_below_step3=[_plant(25, [Resource.COAL], 2, 5)],
        is_first_power_plant_discounted=True,
        shuffler=_reverse_shuffler,
    )


class TestAuctionPowerPlantsIntegration(unittest.TestCase):
    def _unwrap(
        self, result: SerializedGameState | RequestError
    ) -> dict[str, object]:
        self.assertIsInstance(result, SerializedGameState)
        assert isinstance(result, SerializedGameState)
        parsed: dict[str, object] = json.loads(result.state)
        return parsed

    def _finish_round_one_phases_3_to_5(
        self, adapter: PowerGridGameAdapter
    ) -> dict[str, object]:
        # Phase 3 (reverse: BLUE=3 -> RED=1 -> YELLOW=2)
        self._unwrap(adapter.buy_resources(3, "OO"))
        self._unwrap(adapter.buy_resources(1, "CC"))
        self._unwrap(adapter.buy_resources(2, "CC"))
        # Phase 4 (reverse: BLUE=3 -> RED=1 -> YELLOW=2)
        self._unwrap(adapter.buy_houses(3, ["A"]))
        self._unwrap(adapter.buy_houses(1, ["B"]))
        self._unwrap(adapter.buy_houses(2, ["C"]))
        # Phase 5 (forward: YELLOW=2 -> RED=1 -> BLUE=3)
        # YELLOW keeps CC (powers 0 cities -> +10 Elektro) for replacement test
        self._unwrap(adapter.use_power_plants(2, [], ""))
        self._unwrap(adapter.use_power_plants(1, [4], "CC"))
        return self._unwrap(adapter.use_power_plants(3, [3], "OO"))

    def test_full_two_round_auction_bidding_discount_replacement_and_unsold_removal(
        self,
    ) -> None:
        plant_market = _standard_two_round_market()
        order = [PlayerColor.RED, PlayerColor.YELLOW, PlayerColor.BLUE]
        setup = _build_full_game(
            order,
            plant_market,
            GameConfig(default_money=50, max_plants=1),
        )
        adapter = setup.adapter

        # Round 1 forbids passing selection & rejects future-market plant #7
        self.assertIsInstance(
            adapter.do_not_want_power_plant(1), RequestError
        )
        self.assertIsInstance(
            adapter.select_power_plant_to_bid(1, 7, 7), RequestError
        )

        # Bidding war on #4: RED(4)->YELLOW(5)->BLUE passes->RED(6)->YELLOW passes
        self._unwrap(adapter.select_power_plant_to_bid(1, 4, 4))
        self._unwrap(adapter.bid_for_current_power_plant(2, 5))
        self._unwrap(adapter.do_not_bid_for_current_power_plant(3))
        self._unwrap(adapter.bid_for_current_power_plant(1, 6))
        self._unwrap(adapter.do_not_bid_for_current_power_plant(2))
        self.assertEqual(setup.boards[PlayerColor.RED].outstanding_money(), 44)

        # YELLOW selects discounted #3 at 1; non-selector BLUE wins at 2
        self._unwrap(adapter.select_power_plant_to_bid(2, 3, 1))
        self._unwrap(adapter.bid_for_current_power_plant(3, 2))
        self._unwrap(adapter.do_not_bid_for_current_power_plant(2))
        self.assertFalse(plant_market.is_first_power_plant_discounted)
        self.assertEqual(setup.boards[PlayerColor.BLUE].outstanding_money(), 48)

        # Original selector YELLOW re-selects #5 (last eligible -> immediate win)
        after_r1_p2 = self._unwrap(adapter.select_power_plant_to_bid(2, 5, 5))
        self.assertEqual(after_r1_p2["game_phase"], "BUY_RESOURCES")
        self.assertEqual(after_r1_p2["is_first_turn"], False)
        self.assertEqual(
            after_r1_p2["player_order"], ["YELLOW", "RED", "BLUE"]
        )

        # Complete Round 1 Phases 3-5 -> Bureaucracy prepares next turn
        after_r1_p5 = self._finish_round_one_phases_3_to_5(adapter)
        self.assertEqual(after_r1_p5["game_phase"], "AUCTION_POWER_PLANTS")
        self.assertTrue(plant_market.is_first_power_plant_discounted)
        lowest_r2 = plant_market.power_plant_selection_row1[0].number.number
        second_r2 = plant_market.power_plant_selection_row1[1].number.number
        self.assertEqual(second_r2, 7)

        # Round 2 Phase 2: YELLOW wins #7 (OIL) over max_plants=1
        coal_before = setup.pool.resources.count(Resource.COAL)
        self._unwrap(adapter.select_power_plant_to_bid(2, second_r2, second_r2))
        self._unwrap(adapter.do_not_bid_for_current_power_plant(1))
        self._unwrap(adapter.do_not_bid_for_current_power_plant(3))

        # Cannot discard newly bought #7, nor keep CC when discarding #5
        self.assertIsInstance(
            adapter.remove_power_plant(2, second_r2, "CC"), RequestError
        )
        self.assertIsInstance(
            adapter.remove_power_plant(2, 5, ""), RequestError
        )
        self._unwrap(adapter.remove_power_plant(2, 5, "CC"))
        self.assertEqual(
            setup.pool.resources.count(Resource.COAL), coal_before + 2
        )

        # RED and BLUE pass -> Phase 2 ends & removes unsold discounted plant
        self.assertTrue(plant_market.is_first_power_plant_discounted)
        self._unwrap(adapter.do_not_want_power_plant(1))
        after_r2_p2 = self._unwrap(adapter.do_not_want_power_plant(3))
        self.assertEqual(after_r2_p2["game_phase"], "BUY_RESOURCES")
        self.assertEqual(
            after_r2_p2["player_order"], ["YELLOW", "RED", "BLUE"]
        )
        self.assertFalse(plant_market.is_first_power_plant_discounted)
        row1_nums = [
            p.number.number for p in plant_market.power_plant_selection_row1
        ]
        self.assertNotIn(lowest_r2, row1_nums)

    def test_step3_card_drawn_mid_auction_triggers_step3_at_phase2_end(
        self,
    ) -> None:
        plant_market = PowerPlantMarket(
            row1=[
                _plant(3, [Resource.OIL], 2, 1),
                _plant(4, [Resource.COAL], 2, 1),
                _plant(5, [Resource.COAL, Resource.OIL], 2, 1),
                _plant(6, [Resource.GARBAGE], 1, 1),
            ],
            row2=[
                _plant(7, [Resource.OIL], 3, 2),
                _plant(8, [Resource.COAL], 3, 2),
                _plant(9, [Resource.OIL], 1, 1),
                _plant(10, [Resource.COAL], 2, 2),
            ],
            deck_above_step3=[],
            deck_below_step3=[
                _plant(20, [Resource.COAL], 3, 5),
                _plant(25, [], 0, 4),
            ],
            is_first_power_plant_discounted=True,
            shuffler=_reverse_shuffler,
        )
        order = [PlayerColor.RED, PlayerColor.BLUE]
        setup = _build_full_game(
            order,
            plant_market,
            GameConfig(default_money=50, is_first_round=False),
        )
        adapter = setup.adapter

        # RED buys #4 (not discounted) -> replacement draws Step 3 card
        self._unwrap(adapter.select_power_plant_to_bid(1, 4, 4))
        mid = self._unwrap(adapter.do_not_bid_for_current_power_plant(2))
        self.assertTrue(plant_market.is_step3_start())
        self.assertEqual(mid["step"], 1)
        self.assertEqual(setup.towns.step, 1)
        self.assertEqual(setup.plant_market.step, 1)

        # BLUE passes -> Phase 2 ends: removes unsold discounted #3 (draws #25
        # from shuffled deck_below), then GameController bumps to Step 3!
        after_p2 = self._unwrap(adapter.do_not_want_power_plant(2))
        self.assertEqual(after_p2["game_phase"], "BUY_RESOURCES")
        self.assertEqual(after_p2["step"], 3)
        self.assertEqual(setup.towns.step, 3)
        self.assertEqual(setup.plant_market.step, 3)
        self.assertFalse(setup.plant_market.is_step3_start())
        self.assertEqual(setup.plant_market.power_plant_selection_row2, [])
        self.assertEqual(
            [
                p.number.number
                for p in setup.plant_market.power_plant_selection_row1
            ],
            [6, 7, 8, 9, 10, 25],
        )

    def test_auto_pruning_by_money_and_non_selector_win_then_selector_passes(
        self,
    ) -> None:
        plant_market = PowerPlantMarket(
            row1=[
                _plant(3, [Resource.OIL], 2, 1),
                _plant(12, [Resource.COAL], 2, 2),
                _plant(14, [Resource.GARBAGE], 2, 2),
                _plant(16, [Resource.OIL], 2, 3),
            ],
            row2=[
                _plant(18, [], 0, 2),
                _plant(20, [Resource.COAL], 3, 5),
                _plant(22, [], 0, 2),
                _plant(24, [Resource.GARBAGE], 2, 4),
            ],
            deck_above_step3=[
                _plant(26, [Resource.OIL], 2, 5),
                _plant(28, [Resource.URANIUM], 1, 4),
            ],
            is_first_power_plant_discounted=True,
            shuffler=_reverse_shuffler,
        )
        order = [PlayerColor.RED, PlayerColor.YELLOW, PlayerColor.BLUE]
        setup = _build_full_game(
            order,
            plant_market,
            GameConfig(
                money_by_player={
                    PlayerColor.RED: 20,
                    PlayerColor.YELLOW: 12,
                    PlayerColor.BLUE: 25,
                },
                is_first_round=False,
            ),
        )
        adapter = setup.adapter

        # RED(20E) selects #12 at 12: YELLOW(12E) auto-pruned; BLUE(25E) bids
        self._unwrap(adapter.select_power_plant_to_bid(1, 12, 12))
        self.assertEqual(setup.auction.current_player, PlayerColor.BLUE)
        self.assertEqual(
            setup.auction.active_bidders, [PlayerColor.BLUE, PlayerColor.RED]
        )

        # BLUE bids 20 -> RED(20E) auto-pruned -> BLUE wins immediately
        self._unwrap(adapter.bid_for_current_power_plant(3, 20))
        self.assertEqual(setup.boards[PlayerColor.BLUE].outstanding_money(), 5)
        self.assertEqual(
            [
                p.number.number
                for p in setup.boards[PlayerColor.BLUE].power_plants
            ],
            [12],
        )

        # Non-selector BLUE won -> original selector RED selects again & passes
        self.assertEqual(setup.auction.current_player, PlayerColor.RED)
        self._unwrap(adapter.do_not_want_power_plant(1))

        # YELLOW (pruned earlier, still eligible!) buys discounted #3 for 1E
        self.assertEqual(setup.auction.current_player, PlayerColor.YELLOW)
        after_p2 = self._unwrap(adapter.select_power_plant_to_bid(2, 3, 1))
        self.assertEqual(after_p2["game_phase"], "BUY_RESOURCES")
        self.assertEqual(
            setup.boards[PlayerColor.YELLOW].outstanding_money(), 11
        )
        self.assertEqual(
            [
                p.number.number
                for p in setup.boards[PlayerColor.YELLOW].power_plants
            ],
            [3],
        )

    def test_step3_six_plant_market_and_deck_exhaustion_auction(self) -> None:
        plant_market = PowerPlantMarket(
            row1=[
                _plant(10, [Resource.COAL], 2, 2),
                _plant(12, [Resource.OIL], 2, 2),
                _plant(14, [Resource.GARBAGE], 2, 2),
                _plant(16, [Resource.OIL], 2, 3),
                _plant(18, [], 0, 2),
                _plant(20, [Resource.COAL], 3, 5),
            ],
            row2=[],
            deck_above_step3=[],
            deck_below_step3=[_plant(30, [Resource.GARBAGE], 3, 6)],
            is_first_power_plant_discounted=True,
            step=3,
            shuffler=_reverse_shuffler,
        )
        order = [PlayerColor.RED, PlayerColor.BLUE]
        setup = _build_full_game(
            order,
            plant_market,
            GameConfig(default_money=60, is_first_round=False),
        )
        adapter = setup.adapter

        # In Step 3 all 6 plants in row1 are directly auctionable (including #20!)
        self._unwrap(adapter.select_power_plant_to_bid(1, 20, 20))
        self._unwrap(adapter.do_not_bid_for_current_power_plant(2))
        # Replacement #30 drawn from deck_below; deck_below is now empty
        self.assertEqual(
            [
                p.number.number
                for p in plant_market.power_plant_selection_row1
            ],
            [10, 12, 14, 16, 18, 30],
        )
        self.assertEqual(plant_market.power_plant_deck_below_3rd_step, [])

        # BLUE buys #30 (immediate win, deck exhausted -> row1 shrinks to 5),
        # and unsold discounted #10 is removed at Phase 2 end -> row1 shrinks to 4!
        after_p2 = self._unwrap(adapter.select_power_plant_to_bid(2, 30, 30))
        self.assertEqual(after_p2["game_phase"], "BUY_RESOURCES")
        self.assertFalse(plant_market.is_first_power_plant_discounted)
        self.assertEqual(
            [
                p.number.number
                for p in plant_market.power_plant_selection_row1
            ],
            [12, 14, 16, 18],
        )


if __name__ == "__main__":
    unittest.main()
