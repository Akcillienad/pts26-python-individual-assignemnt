from __future__ import annotations

import json
import unittest
from collections.abc import Sequence
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
from power_grid.interfaces import PowerGridRulesGameInterface
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


def _deterministic_shuffler(cards: list[PowerPlant]) -> None:
    cards.sort(key=lambda plant: plant.number.number)


@dataclass(frozen=True)
class RealGameFixture:
    game: PowerGridRulesGameInterface
    plant_market: PowerPlantMarket
    towns: Towns
    boards: dict[PlayerColor, PlayerBoardFacade]


def _build_zero_fake_game() -> RealGameFixture:
    pool = ResourcePool(
        resources=(
            [Resource.COAL] * 3
            + [Resource.OIL] * 6
            + [Resource.GARBAGE] * 18
            + [Resource.URANIUM] * 10
        ),
        storage_space=[],
    )
    refills = {
        step: {
            Resource.COAL: coal,
            Resource.OIL: oil,
            Resource.GARBAGE: garbage,
            Resource.URANIUM: uranium,
        }
        for step, (coal, oil, garbage, uranium) in {
            1: (3, 2, 1, 1),
            2: (4, 3, 2, 1),
            3: (3, 4, 3, 2),
        }.items()
    }
    starting = (
        [Resource.COAL] * 21
        + [Resource.OIL] * 18
        + [Resource.GARBAGE] * 6
        + [Resource.URANIUM] * 2
    )
    resource_market = ResourceMarket(pool, starting, refills)
    town_names = [f"T{idx}" for idx in range(1, 10)]
    edges = [(town_names[idx], town_names[idx + 1], 2) for idx in range(8)]
    towns = Towns(town_names, Connections(edges))

    plant_market = PowerPlantMarket(
        row1=[
            _plant(3, [Resource.OIL], 2, 1),
            _plant(4, [Resource.COAL], 2, 2),
            _plant(5, [Resource.COAL, Resource.OIL], 2, 2),
            _plant(6, [Resource.GARBAGE], 1, 1),
        ],
        row2=[
            _plant(10, [Resource.COAL], 2, 3),
            _plant(13, [], 0, 4),
            _plant(16, [Resource.OIL], 2, 4),
            _plant(20, [Resource.COAL], 3, 5),
        ],
        deck_above_step3=[
            _plant(22, [], 0, 2),
            _plant(25, [Resource.COAL], 2, 5),
            _plant(27, [], 0, 3),
            _plant(30, [Resource.GARBAGE], 3, 6),
        ],
        deck_below_step3=[
            _plant(35, [Resource.OIL], 1, 5),
            _plant(40, [Resource.OIL], 2, 6),
        ],
        is_first_power_plant_discounted=True,
        shuffler=_deterministic_shuffler,
    )

    order = [PlayerColor.RED, PlayerColor.BLUE]
    context = PlayerBoardContext(resource_market, pool, towns)
    boards = {
        color: PlayerBoardFacade(
            PlayerMoney(color, 250),
            PlayerPowerPlants(max_plants=4),
            context,
        )
        for color in order
    }
    controller = GameController(
        order,
        boards,
        GamePhases(
            AuctionPowerPlants(plant_market, boards, is_first_round=True),
            BuyingResources(boards),
            BuildingHouses(
                towns, plant_market, boards, end_game_town_count=8
            ),
            Bureaucracy(boards, resource_market, plant_market),
        ),
        GameBoardComponents(
            plant_market,
            resource_market,
            towns,
            CheckAndBumpStep(2, [resource_market, towns, plant_market]),
        ),
    )
    game: PowerGridRulesGameInterface = PowerGridGameAdapter(
        controller, {1: PlayerColor.RED, 2: PlayerColor.BLUE}
    )
    return RealGameFixture(
        game=game, plant_market=plant_market, towns=towns, boards=boards
    )


class TestFullGameRedIntegration(unittest.TestCase):
    def _unwrap(
        self, result: SerializedGameState | RequestError
    ) -> dict[str, object]:
        self.assertIsInstance(result, SerializedGameState)
        assert isinstance(result, SerializedGameState)
        parsed: dict[str, object] = json.loads(result.state)
        return parsed

    def test_end_to_end_step1_to_step2_to_step3_to_game_end_zero_fakes(
        self,
    ) -> None:
        fixture = _build_zero_fake_game()
        game = fixture.game

        # Initial read through PowerGridRulesGameInterface.get_state()
        initial = self._unwrap(game.get_state())
        self.assertEqual(initial["game_phase"], "AUCTION_POWER_PLANTS")
        self.assertEqual(initial["step"], 1)

        # Round 1 Phase 2: RED(1) buys #4 (draws #22), BLUE(2) buys #5 (draws #25)
        # Unsold discounted #3 removed at Phase 2 end (draws #27)
        self._unwrap(game.select_power_plant_to_bid(1, 4, 4))
        self._unwrap(game.do_not_bid_for_current_power_plant(2))
        after_r1_p2 = self._unwrap(game.select_power_plant_to_bid(2, 5, 5))
        self.assertEqual(after_r1_p2["game_phase"], "BUY_RESOURCES")
        self.assertEqual(after_r1_p2["player_order"], ["BLUE", "RED"])

        # Round 1 Phase 3 (reverse: RED=1 -> BLUE=2)
        self._unwrap(game.buy_resources(1, "CC"))
        self._unwrap(game.buy_resources(2, "CO"))

        # Round 1 Phase 4 (reverse: RED=1 -> BLUE=2):
        # RED builds 7 cities (T1..T7) -> removes #6 (<= 7, draws #30, deck_above now empty!)
        # BLUE builds T8..T9 -> cannot share T1 yet in Step 1!
        self.assertIsInstance(game.buy_houses(2, ["T1"]), RequestError)
        self._unwrap(
            game.buy_houses(1, ["T1", "T2", "T3", "T4", "T5", "T6", "T7"])
        )
        # Step 2 triggers at end of Phase 4 -> removes lowest (#10) & draws Step 3 card!
        # Immediately triggers Step 3 as well -> removes lowest (#13) & enters Step 3!
        after_r1_p4 = self._unwrap(game.buy_houses(2, ["T8", "T9"]))
        self.assertEqual(after_r1_p4["game_phase"], "BUREAUCRACY")
        self.assertEqual(after_r1_p4["step"], 3)
        self.assertEqual(fixture.towns.step, 3)
        self.assertEqual(fixture.plant_market.step, 3)
        self.assertEqual(fixture.plant_market.power_plant_selection_row2, [])
        self.assertEqual(
            len(fixture.plant_market.power_plant_selection_row1), 6
        )

        # Round 1 Phase 5 (forward: BLUE=2 -> RED=1): operate plants & refill
        self._unwrap(game.use_power_plants(2, [5], "CO"))
        after_r1_p5 = self._unwrap(game.use_power_plants(1, [4], "CC"))
        self.assertEqual(after_r1_p5["game_phase"], "AUCTION_POWER_PLANTS")
        self.assertEqual(after_r1_p5["player_order"], ["RED", "BLUE"])
        self.assertTrue(fixture.plant_market.is_first_power_plant_discounted)

        # Round 2 Phase 2 (Step 3): RED buys highest visible plant (row1[5] = #35!)
        row1_r2 = [
            p.number.number
            for p in fixture.plant_market.power_plant_selection_row1
        ]
        self.assertEqual(len(row1_r2), 6)
        highest_step3 = row1_r2[-1]
        self._unwrap(
            game.select_power_plant_to_bid(1, highest_step3, highest_step3)
        )
        self._unwrap(game.do_not_bid_for_current_power_plant(2))
        # BLUE buys discounted lowest plant for 1 Elektro
        lowest_step3 = fixture.plant_market.power_plant_selection_row1[
            0
        ].number.number
        after_r2_p2 = self._unwrap(
            game.select_power_plant_to_bid(2, lowest_step3, 1)
        )
        self.assertEqual(after_r2_p2["game_phase"], "BUY_RESOURCES")

        # Round 2 Phase 3 (reverse: BLUE=2 -> RED=1): buy fuel for final scoring
        self._unwrap(game.buy_resources(2, "CCOO"))
        self._unwrap(game.buy_resources(1, "CCO"))

        # Round 2 Phase 4 (reverse: BLUE=2 -> RED=1):
        # BLUE shares T1 (Step 3 allows 2nd slot for 15E!); RED builds T8 (8th city -> GAME_END!)
        self._unwrap(game.buy_houses(2, ["T7", "T6"]))
        final_state = self._unwrap(game.buy_houses(1, ["T8"]))
        self.assertEqual(final_state["game_phase"], "GAME_END")
        self.assertIsNone(final_state["phase_state"])
        self.assertEqual(final_state["game_result"], ["RED", "BLUE"])
        self.assertIsInstance(
            game.use_power_plants(1, [], ""), RequestError
        )
