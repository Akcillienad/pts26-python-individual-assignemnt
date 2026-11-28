# pylint: disable=too-many-public-methods
from __future__ import annotations

import json
import unittest
from collections.abc import Sequence
from dataclasses import dataclass
from test.blue_test_fakes import (
    FakePlayerPowerPlants,
    FakePowerPlantMarket,
    FakeTowns,
)

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
from power_grid.resource_market import ResourceMarket
from power_grid.resource_pool import ResourcePool
from power_grid.simple_types import (
    PhaseStatus,
    PlayerColor,
    RequestError,
    Resource,
    SerializedGameState,
)


class MinimalAuctionFake:
    def __init__(
        self,
        boards: dict[PlayerColor, PlayerBoardFacade],
        catalog: dict[int, PowerPlant],
    ) -> None:
        self._boards = boards
        self._catalog = catalog
        self._queue: list[PlayerColor] = []
        self._pending_removal: PlayerColor | None = None

    def start_phase(self, player_order: Sequence[PlayerColor]) -> None:
        self._queue = list(player_order)
        self._pending_removal = None

    def select_power_plant_to_bid(
        self,
        player: PlayerColor,
        ppn: PowerPlantNumber,
        first_bid: int,
    ) -> PhaseStatus | RequestError:
        if self._pending_removal is not None:
            return RequestError("Must remove excess power plant first")
        if not self._queue or self._queue[0] != player:
            return RequestError("Not player's turn in auction")
        plant = self._catalog.get(ppn.number)
        if plant is None:
            return RequestError("Power plant not in catalog")
        within_limit = self._boards[player].receive_power_plant(
            plant, first_bid
        )
        if not within_limit:
            self._pending_removal = player
            return PhaseStatus.PHASE_CONTINUES
        self._queue.pop(0)
        return (
            PhaseStatus.PHASE_CONTINUES
            if self._queue
            else PhaseStatus.PHASE_ENDS
        )

    def do_not_want_power_plant(
        self,
        player: PlayerColor,
    ) -> PhaseStatus | RequestError:
        if not self._queue or self._queue[0] != player:
            return RequestError("Not player's turn in auction")
        self._queue.pop(0)
        return (
            PhaseStatus.PHASE_CONTINUES
            if self._queue
            else PhaseStatus.PHASE_ENDS
        )

    def bid_for_current_power_plant(
        self,
        player: PlayerColor,
        bid: int,
    ) -> PhaseStatus | RequestError:
        _ = (player, bid)
        return PhaseStatus.PHASE_CONTINUES

    def do_not_bid_for_current_power_plant(
        self,
        player: PlayerColor,
    ) -> PhaseStatus | RequestError:
        _ = player
        return PhaseStatus.PHASE_CONTINUES

    def remove_power_plant(
        self,
        player: PlayerColor,
        ppn: PowerPlantNumber,
        resources: Sequence[Resource],
    ) -> PhaseStatus | RequestError:
        if self._pending_removal != player:
            return RequestError("No pending plant removal for player")
        err = self._boards[player].remove_power_plant(ppn, list(resources))
        if err is not None:
            return err
        self._pending_removal = None
        self._queue.pop(0)
        return (
            PhaseStatus.PHASE_CONTINUES
            if self._queue
            else PhaseStatus.PHASE_ENDS
        )

    def get_state(self) -> str:
        return json.dumps(
            {"queue": [color.name for color in self._queue]}
        )


@dataclass
class IntegrationSetup:
    adapter: PowerGridGameAdapter
    boards: dict[PlayerColor, PlayerBoardFacade]
    pool: ResourcePool
    market: ResourceMarket
    plant_market: FakePowerPlantMarket
    towns: FakeTowns


def _default_refill_pattern() -> dict[int, dict[Resource, int]]:
    return {
        1: {
            Resource.COAL: 4,
            Resource.OIL: 2,
            Resource.GARBAGE: 1,
            Resource.URANIUM: 1,
        },
        2: {
            Resource.COAL: 5,
            Resource.OIL: 3,
            Resource.GARBAGE: 2,
            Resource.URANIUM: 1,
        },
        3: {
            Resource.COAL: 3,
            Resource.OIL: 4,
            Resource.GARBAGE: 3,
            Resource.URANIUM: 1,
        },
    }


def _default_catalog() -> dict[int, PowerPlant]:
    return {
        3: PowerPlant(PowerPlantNumber(3), [Resource.OIL], 2, 1),
        6: PowerPlant(PowerPlantNumber(6), [Resource.GARBAGE], 1, 1),
        7: PowerPlant(PowerPlantNumber(7), [Resource.OIL], 3, 2),
        10: PowerPlant(PowerPlantNumber(10), [Resource.COAL], 2, 2),
        13: PowerPlant(PowerPlantNumber(13), [], 0, 1),
        15: PowerPlant(PowerPlantNumber(15), [Resource.COAL], 2, 3),
        20: PowerPlant(PowerPlantNumber(20), [Resource.COAL], 3, 5),
        25: PowerPlant(PowerPlantNumber(25), [], 0, 4),
    }


def _build_market_and_pool() -> tuple[ResourcePool, ResourceMarket]:
    pool = ResourcePool(
        resources=(
            [Resource.COAL] * 6
            + [Resource.OIL] * 12
            + [Resource.GARBAGE] * 18
            + [Resource.URANIUM] * 10
        ),
        storage_space=[],
    )
    market = ResourceMarket(
        pool=pool,
        starting_resources=(
            [Resource.COAL] * 18
            + [Resource.OIL] * 12
            + [Resource.GARBAGE] * 6
            + [Resource.URANIUM] * 2
        ),
        refilling_pattern=_default_refill_pattern(),
    )
    return pool, market


def _build_map_towns() -> FakeTowns:
    connections = Connections(
        [
            ("A", "B", 5),
            ("B", "C", 5),
            ("C", "D", 4),
            ("D", "E", 3),
            ("E", "F", 2),
            ("F", "G", 2),
            ("G", "H", 2),
            ("H", "I", 2),
        ]
    )
    return FakeTowns(connections=connections, house_cost=10)


def _create_integration_game(
    order: Sequence[PlayerColor],
    starting_money: int,
    max_plants: int = 3,
    end_game_town_count: int | None = None,
) -> IntegrationSetup:
    pool, market = _build_market_and_pool()
    towns = _build_map_towns()
    plant_market = FakePowerPlantMarket()
    context = PlayerBoardContext(market, pool, towns)
    boards = {
        color: PlayerBoardFacade(
            PlayerMoney(color, starting_money),
            FakePlayerPowerPlants(max_plants=max_plants),
            context,
        )
        for color in order
    }
    controller = GameController(
        order,
        boards,
        GamePhases(
            MinimalAuctionFake(boards, _default_catalog()),
            BuyingResources(boards),
            BuildingHouses(
                towns, plant_market, boards,
                end_game_town_count=end_game_town_count,
            ),
            Bureaucracy(boards, market, plant_market),
        ),
        GameBoardComponents(
            plant_market,
            market,
            towns,
            CheckAndBumpStep(len(order), [market, towns, plant_market]),
        ),
    )
    return IntegrationSetup(
        adapter=PowerGridGameAdapter(
            controller, {idx + 1: color for idx, color in enumerate(order)}
        ),
        boards=boards,
        pool=pool,
        market=market,
        plant_market=plant_market,
        towns=towns,
    )


class TestBlueComponentsIntegration(unittest.TestCase):
    def _unwrap_state(
        self,
        result: SerializedGameState | RequestError,
    ) -> dict[str, object]:
        self.assertIsInstance(result, SerializedGameState)
        assert isinstance(result, SerializedGameState)
        parsed: dict[str, object] = json.loads(result.state)
        return parsed

    def test_full_two_round_flow_with_plant_replacement_and_refill(
        self,
    ) -> None:
        order = [PlayerColor.RED, PlayerColor.YELLOW, PlayerColor.BLUE]
        setup = _create_integration_game(
            order, starting_money=50, max_plants=1
        )
        adapter = setup.adapter

        # Round 1 Phase 2: RED(1)->#6, YELLOW(2)->#3, BLUE(3)->#10
        self._unwrap_state(adapter.select_power_plant_to_bid(1, 6, 6))
        self._unwrap_state(adapter.select_power_plant_to_bid(2, 3, 3))
        after_p2 = self._unwrap_state(
            adapter.select_power_plant_to_bid(3, 10, 10)
        )
        # Round 1 special reorder: BLUE(#10), RED(#6), YELLOW(#3)
        self.assertEqual(after_p2["game_phase"], "BUY_RESOURCES")
        self.assertEqual(after_p2["is_first_turn"], False)
        self.assertEqual(after_p2["player_order"], ["BLUE", "RED", "YELLOW"])

        # Round 1 Phase 3 (reverse: YELLOW=2 -> RED=1 -> BLUE=3)
        self.assertIsInstance(adapter.buy_resources(3, "CC"), RequestError)
        self._unwrap_state(adapter.buy_resources(2, "OO"))
        self._unwrap_state(adapter.buy_resources(1, "GG"))
        # Storage full error -> retry succeeds
        self.assertIsInstance(adapter.buy_resources(3, "CCCCC"), RequestError)
        after_p3 = self._unwrap_state(adapter.buy_resources(3, "CC"))
        self.assertEqual(after_p3["game_phase"], "BUY_HOUSES")

        # Round 1 Phase 4 (reverse: YELLOW=2 -> RED=1 -> BLUE=3)
        self._unwrap_state(adapter.buy_houses(2, ["A"]))
        self._unwrap_state(adapter.buy_houses(1, ["B", "C"]))
        after_p4 = self._unwrap_state(adapter.buy_houses(3, ["D"]))
        self.assertEqual(after_p4["game_phase"], "BUREAUCRACY")
        self.assertEqual(setup.plant_market.removed_thresholds, [1, 2, 2])

        # Round 1 Phase 5 (forward: BLUE=3 -> RED=1 -> YELLOW=2)
        # BLUE powers #10 (cap 2, owns 1 house -> +22); 2 COAL return to pool
        self._unwrap_state(adapter.use_power_plants(3, [10], "CC"))
        # RED powers 0 cities -> +10 Elektro; keeps 2 GARBAGE
        self._unwrap_state(adapter.use_power_plants(1, [], ""))
        # YELLOW powers #3 (1 city -> +22); 2 OIL return to pool; refills run
        after_p5 = self._unwrap_state(adapter.use_power_plants(2, [3], "OO"))

        self.assertEqual(after_p5["game_phase"], "AUCTION_POWER_PLANTS")
        self.assertEqual(after_p5["player_order"], ["RED", "BLUE", "YELLOW"])
        self.assertEqual(setup.boards[PlayerColor.BLUE].outstanding_money(), 46)
        self.assertEqual(setup.boards[PlayerColor.RED].outstanding_money(), 15)
        self.assertEqual(
            setup.boards[PlayerColor.YELLOW].outstanding_money(), 49
        )
        self.assertEqual(setup.plant_market.prepare_calls, 1)
        market_snapshot = json.loads(setup.market.to_string())
        self.assertEqual(market_snapshot["coal"], 20)
        self.assertEqual(market_snapshot["oil"], 12)
        self.assertEqual(market_snapshot["garbage"], 5)
        self.assertEqual(market_snapshot["uranium"], 3)

        # Round 2 Phase 2: RED buys #13 (above max_plants=1) & discards #6 + GG
        garbage_before = setup.pool.resources.count(Resource.GARBAGE)
        self._unwrap_state(adapter.select_power_plant_to_bid(1, 13, 13))
        self.assertIsInstance(
            adapter.remove_power_plant(1, 6, ""), RequestError
        )
        self._unwrap_state(adapter.remove_power_plant(1, 6, "GG"))
        self.assertEqual(
            setup.pool.resources.count(Resource.GARBAGE), garbage_before + 2
        )
        self._unwrap_state(adapter.select_power_plant_to_bid(3, 20, 20))
        self._unwrap_state(adapter.remove_power_plant(3, 10, ""))
        after_r2_p2 = self._unwrap_state(adapter.do_not_want_power_plant(2))
        # Round 2 must NOT reorder after Phase 2 even though BLUE has #20
        self.assertEqual(after_r2_p2["game_phase"], "BUY_RESOURCES")
        self.assertEqual(
            after_r2_p2["player_order"], ["RED", "BLUE", "YELLOW"]
        )

    def test_step_transitions_and_game_end_tie_breakers(self) -> None:
        order = [PlayerColor.RED, PlayerColor.BLUE]
        setup = _create_integration_game(
            order, starting_money=300, max_plants=3, end_game_town_count=8
        )
        adapter = setup.adapter

        # Round 1 Phase 2: both get wind plant / high capacity (no fuel needed)
        self._unwrap_state(adapter.select_power_plant_to_bid(1, 25, 25))
        self._unwrap_state(adapter.select_power_plant_to_bid(2, 13, 13))
        # Order after R1 Phase 2: RED(#25), BLUE(#13)
        # Round 1 Phase 3 (reverse: BLUE=2 -> RED=1)
        self._unwrap_state(adapter.buy_resources(2, ""))
        self._unwrap_state(adapter.buy_resources(1, ""))

        # Round 1 Phase 4 (reverse: BLUE=2 -> RED=1): RED hits 7 -> Step 2!
        self._unwrap_state(adapter.buy_houses(2, ["A", "B", "C"]))
        after_r1_p4 = self._unwrap_state(
            adapter.buy_houses(1, ["A", "B", "C", "D", "E", "F", "G"])
        )
        self.assertEqual(after_r1_p4["step"], 2)
        self.assertEqual(setup.towns.step, 2)

        # Round 1 Phase 5: trigger Step 3 via plant_market before turn ends
        setup.plant_market.step3_ready = True
        self._unwrap_state(adapter.use_power_plants(1, [25], ""))
        after_r1_p5 = self._unwrap_state(adapter.use_power_plants(2, [13], ""))
        self.assertEqual(after_r1_p5["step"], 3)
        self.assertEqual(setup.towns.step, 3)

        # Round 2 Phase 2: BLUE buys #15 (3 cities, 2 coal) -> can power 1+3=4
        self._unwrap_state(adapter.do_not_want_power_plant(1))
        self._unwrap_state(adapter.select_power_plant_to_bid(2, 15, 15))
        # Round 2 Phase 3 (reverse: BLUE=2 -> RED=1): BLUE buys 2 coal
        self._unwrap_state(adapter.buy_resources(2, "CC"))
        self._unwrap_state(adapter.buy_resources(1, ""))

        # Round 2 Phase 4 (reverse: BLUE=2 -> RED=1):
        # BLUE expands to 8 houses (hits end_game_town_count=8), waits for RED!
        mid_r2_p4 = self._unwrap_state(
            adapter.buy_houses(2, ["D", "E", "F", "G", "H"])
        )
        self.assertEqual(mid_r2_p4["game_phase"], "BUY_HOUSES")
        # RED passes -> GAME_ENDS! Both power 4 cities; RED has more money!
        prepare_before = setup.plant_market.prepare_calls
        final_state = self._unwrap_state(adapter.buy_houses(1, []))

        self.assertEqual(final_state["game_phase"], "GAME_END")
        self.assertIsNone(final_state["phase_state"])
        self.assertEqual(final_state["game_result"], ["RED", "BLUE"])
        # Bureaucracy skipped -> prepare_next_turn not called again
        self.assertEqual(setup.plant_market.prepare_calls, prepare_before)
        self.assertGreater(
            setup.boards[PlayerColor.RED].outstanding_money(),
            setup.boards[PlayerColor.BLUE].outstanding_money(),
        )
        # No actions allowed after GAME_END
        self.assertIsInstance(
            adapter.use_power_plants(1, [], ""), RequestError
        )
