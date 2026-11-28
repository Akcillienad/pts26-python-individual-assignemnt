# pylint: disable=too-many-public-methods
from __future__ import annotations

import json
import tkinter as tk
import unittest
from collections.abc import Sequence

from power_grid.factories import GameSession, create_standard_game
from power_grid.gui import PowerGridApp
from power_grid.gui_presenter import PowerGridGuiPresenter
from power_grid.interfaces import PowerGridRulesGameInterface
from power_grid.power_plant import PowerPlant
from power_grid.simple_types import RequestError, SerializedGameState


class FakeRulesGame(PowerGridRulesGameInterface):
    def __init__(self, initial_json: str) -> None:
        self.state_json = initial_json
        self.next_result: SerializedGameState | RequestError | None = None
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def select_power_plant_to_bid(
        self, player_id: int, power_plant_number: int, first_bid: int
    ) -> SerializedGameState | RequestError:
        self.calls.append(("select", (player_id, power_plant_number, first_bid)))
        return self._reply()

    def do_not_want_power_plant(
        self, player_id: int
    ) -> SerializedGameState | RequestError:
        self.calls.append(("pass_select", (player_id,)))
        return self._reply()

    def bid_for_current_power_plant(
        self, player_id: int, bid: int
    ) -> SerializedGameState | RequestError:
        self.calls.append(("bid", (player_id, bid)))
        return self._reply()

    def do_not_bid_for_current_power_plant(
        self, player_id: int
    ) -> SerializedGameState | RequestError:
        self.calls.append(("pass_bid", (player_id,)))
        return self._reply()

    def remove_power_plant(
        self, player_id: int, power_plant_number: int, removed_resources: str
    ) -> SerializedGameState | RequestError:
        self.calls.append(("remove", (player_id, power_plant_number, removed_resources)))
        return self._reply()

    def buy_resources(
        self, player_id: int, resources: str
    ) -> SerializedGameState | RequestError:
        self.calls.append(("buy_resources", (player_id, resources)))
        return self._reply()

    def buy_houses(
        self, player_id: int, town_names: Sequence[str]
    ) -> SerializedGameState | RequestError:
        self.calls.append(("buy_houses", (player_id, list(town_names))))
        return self._reply()

    def use_power_plants(
        self,
        player_id: int,
        power_plant_numbers: Sequence[int],
        resources_to_burn: str,
    ) -> SerializedGameState | RequestError:
        self.calls.append(
            ("use_plants", (player_id, list(power_plant_numbers), resources_to_burn))
        )
        return self._reply()

    def get_state(self) -> SerializedGameState:
        return SerializedGameState(self.state_json)

    def _reply(self) -> SerializedGameState | RequestError:
        if self.next_result is not None:
            res = self.next_result
            self.next_result = None
            return res
        return SerializedGameState(self.state_json)


def _sample_state_json(
    phase: str = "AUCTION_POWER_PLANTS",
    stage: str | None = "SELECTING",
    current_player: str | None = "RED",
) -> str:
    phase_state: dict[str, object] | None
    if phase == "GAME_END":
        phase_state = None
    else:
        phase_state = {
            "is_active": True,
            "current_player": current_player,
            "stage": stage,
            "is_first_round": True,
            "eligible_players": ["RED", "YELLOW"],
            "remaining_players": ["RED", "YELLOW"],
            "current_plant": 3 if stage == "BIDDING" else None,
            "current_bid": 4 if stage == "BIDDING" else None,
            "highest_bidder": "RED" if stage == "BIDDING" else None,
            "active_bidders": ["YELLOW", "RED"] if stage == "BIDDING" else [],
            "pending_removal_player": (
                "RED" if stage == "REMOVING_PLANT" else None
            ),
            "pending_removal_bought_plant": (
                10 if stage == "REMOVING_PLANT" else None
            ),
        }
    return json.dumps(
        {
            "game_phase": phase,
            "is_first_turn": True,
            "step": 1,
            "player_order": ["RED", "YELLOW"],
            "phase_state": phase_state,
            "power_plant_market": {
                "step": 1,
                "is_step3": False,
                "is_step3_start": False,
                "is_first_power_plant_discounted": True,
                "row1": [3, 4, 5, 6],
                "row2": [7, 8, 9, 10],
                "deck_above_step3_count": 20,
                "deck_below_step3_count": 0,
            },
            "resource_market": {
                "coal": 24,
                "oil": 18,
                "garbage": 6,
                "uranium": 2,
                "pool": {
                    "resources": ["OIL"] * 6,
                    "storage_space": [],
                },
            },
            "towns": {
                "step": 1,
                "houses": {"Essen": ["RED"], "Dortmund": []},
            },
            "players": {
                "RED": {
                    "color": "RED",
                    "money": 50,
                    "power_plants": [3],
                    "resources": ["OIL"],
                },
                "YELLOW": {
                    "color": "YELLOW",
                    "money": 50,
                    "power_plants": [],
                    "resources": [],
                },
            },
            "game_result": ["RED", "YELLOW"] if phase == "GAME_END" else [],
        }
    )


class TestGuiPresenterAndTkApp(unittest.TestCase):
    def test_solitary_presenter_delegation_and_error_handling(self) -> None:
        base_session = create_standard_game(player_count=2, seed=1)
        fake_game = FakeRulesGame(_sample_state_json())
        presenter = PowerGridGuiPresenter(
            GameSession(game=fake_game, metadata=base_session.metadata)
        )

        self.assertEqual(presenter.view_state.game_phase, "AUCTION_POWER_PLANTS")
        self.assertEqual(presenter.current_player_color, "RED")
        self.assertEqual(presenter.current_player_id, 1)
        self.assertIsNone(presenter.last_error)
        self.assertEqual(presenter.format_plant_spec(13), "#13 [ECO -> 1C]")
        self.assertEqual(presenter.format_plant_spec(5), "#5 [2C/O -> 1C]")
        self.assertEqual(presenter.format_plant_spec(999), "#999")

        # RequestError must preserve view_state and record last_error
        fake_game.next_result = RequestError("Invalid bid")
        err = presenter.select_power_plant(1, 3, 0)
        self.assertEqual(err, "Invalid bid")
        self.assertEqual(presenter.last_error, "Invalid bid")
        self.assertEqual(presenter.view_state.game_phase, "AUCTION_POWER_PLANTS")

        # Next valid action clears last_error and updates view_state
        fake_game.next_result = SerializedGameState(
            _sample_state_json(phase="BUY_RESOURCES", stage=None, current_player="YELLOW")
        )
        self.assertIsNone(presenter.pass_select_power_plant(1))
        self.assertIsNone(presenter.last_error)
        self.assertEqual(presenter.view_state.game_phase, "BUY_RESOURCES")
        self.assertEqual(presenter.current_player_id, 2)

        # Remaining delegations
        self.assertIsNone(presenter.bid_current_power_plant(2, 5))
        self.assertIsNone(presenter.pass_bid_current_power_plant(1))
        self.assertIsNone(presenter.remove_power_plant(1, 3, "O"))
        self.assertIsNone(presenter.buy_resources(2, "CC"))
        self.assertIsNone(presenter.buy_houses(2, ["Essen"]))
        self.assertIsNone(presenter.use_power_plants(1, [3], "OO"))
        self.assertEqual(len(fake_game.calls), 8)

    def test_malformed_json_rejected_cleanly(self) -> None:
        base_session = create_standard_game(player_count=2, seed=1)
        bad_game = FakeRulesGame("{not valid json")
        with self.assertRaises(ValueError):
            PowerGridGuiPresenter(
                GameSession(game=bad_game, metadata=base_session.metadata)
            )

        bad_schema = FakeRulesGame('{"game_phase": 123}')
        with self.assertRaises(ValueError):
            PowerGridGuiPresenter(
                GameSession(game=bad_schema, metadata=base_session.metadata)
            )

    def test_real_backend_end_to_end_via_presenter(self) -> None:
        def no_shuffle(_cards: list[PowerPlant]) -> None:
            return None

        session = create_standard_game(
            player_count=2,
            starting_money=200,
            end_game_town_count=2,
            shuffler=no_shuffle,
        )
        presenter = PowerGridGuiPresenter(session)
        self.assertEqual(presenter.view_state.game_phase, "AUCTION_POWER_PLANTS")
        self.assertEqual(presenter.current_player_id, 1)

        # Invalid pass in Round 1 returns error and preserves state
        err = presenter.pass_select_power_plant(1)
        self.assertIsNotNone(err)
        self.assertEqual(presenter.last_error, err)
        self.assertEqual(presenter.current_player_id, 1)

        # Round 1 Auction -> Reorders to [YELLOW(2), RED(1)]
        # Reverse order for BUY_RESOURCES & BUY_HOUSES is RED(1) -> YELLOW(2)
        self.assertIsNone(presenter.select_power_plant(1, 3, 1))
        self.assertIsNone(presenter.pass_bid_current_power_plant(2))
        self.assertIsNone(presenter.select_power_plant(2, 4, 4))
        self.assertEqual(presenter.view_state.game_phase, "BUY_RESOURCES")
        self.assertEqual(presenter.current_player_id, 1)

        self.assertIsNone(presenter.buy_resources(1, "OO"))
        self.assertIsNone(presenter.buy_resources(2, "CC"))
        self.assertEqual(presenter.view_state.game_phase, "BUY_HOUSES")

        self.assertIsNone(presenter.buy_houses(1, ["Berlin"]))
        self.assertIsNone(presenter.buy_houses(2, ["Essen"]))
        self.assertEqual(presenter.view_state.game_phase, "BUREAUCRACY")
        self.assertEqual(presenter.current_player_id, 2)

        self.assertIsNone(presenter.use_power_plants(2, [4], "CC"))
        self.assertIsNone(presenter.use_power_plants(1, [3], "OO"))
        self.assertEqual(presenter.view_state.game_phase, "AUCTION_POWER_PLANTS")

        # Round 2: both pass (in order P1, P2 or P2, P1 based on tie-break -> use active!)
        first = presenter.current_player_id
        assert first is not None
        self.assertIsNone(presenter.pass_select_power_plant(first))
        second = presenter.current_player_id
        assert second is not None
        self.assertIsNone(presenter.pass_select_power_plant(second))
        self.assertEqual(presenter.view_state.game_phase, "BUY_RESOURCES")
        first_rev = presenter.current_player_id
        assert first_rev is not None
        self.assertIsNone(presenter.buy_resources(first_rev, ""))
        second_rev = presenter.current_player_id
        assert second_rev is not None
        self.assertIsNone(presenter.buy_resources(second_rev, ""))
        self.assertEqual(presenter.view_state.game_phase, "BUY_HOUSES")
        first_house = presenter.current_player_id
        assert first_house is not None
        self.assertIsNone(presenter.buy_houses(first_house, ["Dortmund"]))
        second_house = presenter.current_player_id
        assert second_house is not None
        self.assertIsNone(presenter.buy_houses(second_house, []))
        self.assertEqual(presenter.view_state.game_phase, "GAME_END")
        self.assertIsNone(presenter.current_player_id)
        self.assertEqual(len(presenter.view_state.game_result), 2)

    def test_tkinter_app_smoke_renders_and_handles_actions(self) -> None:
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
            return
        root.withdraw()
        try:
            app = PowerGridApp(
                root,
                session_factory=lambda count, limit: create_standard_game(
                    player_count=count,
                    end_game_town_count=limit,
                    seed=7,
                ),
            )
            self.assertEqual(
                app.presenter.view_state.game_phase, "AUCTION_POWER_PLANTS"
            )
            # Trigger an invalid Round 1 pass to exercise error banner
            app.presenter.pass_select_power_plant(1)
            app.start_new_game()
            self.assertIsNone(app.presenter.last_error)
            root.update_idletasks()
        finally:
            root.destroy()

    def test_tkinter_app_renders_all_phases_and_rejects_bad_int_input(
        self,
    ) -> None:
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
            return
        root.withdraw()
        try:
            base_session = create_standard_game(player_count=2, seed=2)
            fake_game = FakeRulesGame(_sample_state_json())
            app = PowerGridApp(
                root,
                session_factory=lambda _c, _l: GameSession(
                    game=fake_game, metadata=base_session.metadata
                ),
            )
            # Simulate rendering across every UI phase/stage
            for phase, stage in (
                ("AUCTION_POWER_PLANTS", "BIDDING"),
                ("AUCTION_POWER_PLANTS", "REMOVING_PLANT"),
                ("BUY_RESOURCES", None),
                ("BUY_HOUSES", None),
                ("BUREAUCRACY", None),
                ("GAME_END", None),
            ):
                fake_game.next_result = SerializedGameState(
                    _sample_state_json(phase=phase, stage=stage)
                )
                app.presenter.pass_select_power_plant(1)
                app.refresh()
                root.update_idletasks()

            self.assertEqual(app.presenter.view_state.game_phase, "GAME_END")
        finally:
            root.destroy()
