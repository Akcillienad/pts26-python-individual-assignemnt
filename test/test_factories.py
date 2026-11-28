# pylint: disable=too-many-public-methods
from __future__ import annotations

import json
import unittest

from power_grid.connections import Connections
from power_grid.factories import create_standard_game
from power_grid.power_plant import PowerPlant
from power_grid.resource_market import ResourceMarket
from power_grid.simple_types import RequestError, Resource, SerializedGameState


class TestFactories(unittest.TestCase):
    def test_standard_game_setup_invariants_for_all_player_counts(
        self,
    ) -> None:
        expected_deck_above = {2: 22, 3: 22, 4: 26, 5: 30, 6: 30}
        expected_end_game = {2: 21, 3: 17, 4: 17, 5: 15, 6: 14}
        expected_max_plants = {2: 4, 3: 3, 4: 3, 5: 3, 6: 3}

        for count in range(2, 7):
            with self.subTest(player_count=count):
                session = create_standard_game(player_count=count, seed=42)
                meta = session.metadata
                self.assertEqual(len(meta.player_id_to_color), count)
                self.assertEqual(
                    meta.end_game_town_count, expected_end_game[count]
                )
                self.assertEqual(
                    meta.max_power_plants_per_player,
                    expected_max_plants[count],
                )
                self.assertEqual(len(meta.town_names), 21)
                self.assertEqual(len(meta.plant_catalog), 42)

                # All 21 towns must be reachable from the first town
                conn = Connections(list(meta.connections))
                total_tree_cost = conn.calculate_connecting_cost(
                    [meta.town_names[0]], list(meta.town_names[1:])
                )
                self.assertGreater(total_tree_cost, 0)

                state_obj = session.game.get_state()
                self.assertIsInstance(state_obj, SerializedGameState)
                parsed: dict[str, object] = json.loads(state_obj.state)
                self.assertEqual(parsed["game_phase"], "AUCTION_POWER_PLANTS")

                pm = parsed["power_plant_market"]
                assert isinstance(pm, dict)
                self.assertEqual(len(pm["row1"]), 4)
                self.assertEqual(len(pm["row2"]), 4)
                self.assertTrue(pm["is_first_power_plant_discounted"])
                self.assertEqual(
                    pm["deck_above_step3_count"], expected_deck_above[count]
                )
                self.assertEqual(pm["deck_below_step3_count"], 0)

                rm = parsed["resource_market"]
                assert isinstance(rm, dict)
                pool = rm["pool"]
                assert isinstance(pool, dict)
                pool_res = pool["resources"]
                assert isinstance(pool_res, list)
                self.assertEqual(rm["coal"], 21)
                self.assertEqual(pool_res.count("COAL"), 3)
                self.assertEqual(
                    rm["coal"] + pool_res.count("COAL"),
                    ResourceMarket.MAX_RESOURCES[Resource.COAL],
                )
                self.assertEqual(
                    rm["oil"] + pool_res.count("OIL"),
                    ResourceMarket.MAX_RESOURCES[Resource.OIL],
                )
                self.assertEqual(
                    rm["garbage"] + pool_res.count("GARBAGE"),
                    ResourceMarket.MAX_RESOURCES[Resource.GARBAGE],
                )
                self.assertEqual(
                    rm["uranium"] + pool_res.count("URANIUM"),
                    ResourceMarket.MAX_RESOURCES[Resource.URANIUM],
                )

    def test_seed_reproducibility_and_argument_validation(self) -> None:
        s1 = create_standard_game(player_count=4, seed=12345)
        s2 = create_standard_game(player_count=4, seed=12345)
        self.assertEqual(s1.game.get_state(), s2.game.get_state())

        for bad_count in (1, 7, True, False):
            with self.subTest(bad_count=bad_count):
                with self.assertRaises(ValueError):
                    create_standard_game(player_count=bad_count)

        for bad_money in (-1, True, False):
            with self.subTest(bad_money=bad_money):
                with self.assertRaises(ValueError):
                    create_standard_game(starting_money=bad_money)

        for bad_end in (0, 22, True, False):
            with self.subTest(bad_end=bad_end):
                with self.assertRaises(ValueError):
                    create_standard_game(end_game_town_count=bad_end)

        def noop_shuffle(_cards: list[PowerPlant]) -> None:
            return None

        with self.assertRaises(ValueError):
            create_standard_game(shuffler=noop_shuffle, seed=1)
        with self.assertRaises(ValueError):
            create_standard_game(
                shuffler="not_callable"  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            create_standard_game(
                randomize_player_order="yes"  # type: ignore[arg-type]
            )

        rand_a = create_standard_game(
            player_count=5, seed=99, randomize_player_order=True
        )
        rand_b = create_standard_game(
            player_count=5, seed=99, randomize_player_order=True
        )
        self.assertEqual(rand_a.game.get_state(), rand_b.game.get_state())
        order_a = json.loads(rand_a.game.get_state().state)["player_order"]
        self.assertEqual(
            set(order_a), {"RED", "YELLOW", "BLUE", "GREEN", "PURPLE"}
        )
        self.assertNotEqual(
            order_a, ["RED", "YELLOW", "BLUE", "GREEN", "PURPLE"]
        )

    def test_play_complete_game_via_power_grid_rules_interface(self) -> None:
        def no_shuffle(_cards: list[PowerPlant]) -> None:
            return None

        session = create_standard_game(
            player_count=2,
            starting_money=200,
            end_game_town_count=2,
            shuffler=no_shuffle,
        )
        game = session.game
        initial = json.loads(game.get_state().state)
        pm = initial["power_plant_market"]
        row1 = pm["row1"]
        self.assertEqual(row1, [3, 4, 5, 6])

        # Round 1 Auction: P1(RED) buys #3 (discounted to 1), P2(YELLOW) buys #4
        # -> Round 1 special reorder puts YELLOW(2) ahead of RED(1)!
        res = game.select_power_plant_to_bid(1, 3, 1)
        self.assertIsInstance(res, SerializedGameState)
        assert isinstance(res, SerializedGameState)
        # P2 can afford 2, so P2 passes bid
        res = game.do_not_bid_for_current_power_plant(2)
        self.assertIsInstance(res, SerializedGameState)
        res = game.select_power_plant_to_bid(2, 4, 4)
        self.assertIsInstance(res, SerializedGameState)
        assert isinstance(res, SerializedGameState)
        after_auction = json.loads(res.state)
        self.assertEqual(after_auction["game_phase"], "BUY_RESOURCES")
        self.assertEqual(after_auction["player_order"], ["YELLOW", "RED"])

        # Round 1 Buy Resources (reverse of [YELLOW, RED] -> P1(RED) -> P2(YELLOW))
        self.assertIsInstance(
            game.buy_resources(2, "CC"), RequestError
        )
        self.assertIsInstance(
            game.buy_resources(1, "OO"), SerializedGameState
        )
        res = game.buy_resources(2, "CC")
        self.assertIsInstance(res, SerializedGameState)

        # Round 1 Buy Houses (reverse: P1(RED) -> P2(YELLOW) reaches 2 -> GAME_END)
        res = game.buy_houses(1, ["Berlin"])
        self.assertIsInstance(res, SerializedGameState)
        assert isinstance(res, SerializedGameState)
        self.assertEqual(json.loads(res.state)["game_phase"], "BUY_HOUSES")

        res = game.buy_houses(2, ["Essen", "Dortmund"])
        self.assertIsInstance(res, SerializedGameState)
        assert isinstance(res, SerializedGameState)
        final_state = json.loads(res.state)
        self.assertEqual(final_state["game_phase"], "GAME_END")
        self.assertTrue(len(final_state["game_result"]) == 2)
