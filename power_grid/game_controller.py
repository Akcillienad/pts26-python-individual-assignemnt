from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from power_grid.determine_player_order import (
    DeterminePlayerOrder,
    PlayerOrderData,
)
from power_grid.interfaces import (
    InterfaceAuctionPowerPlantsGameController,
    InterfaceBuildingHousesGameController,
    InterfaceBureaucracyGameController,
    InterfaceBuyingResourcesGameController,
    InterfaceCheckAndBumpStepGameController,
    InterfacePlayerBoardGameController,
    InterfacePowerPlantMarketGameController,
    InterfaceResourceMarketGameController,
    InterfaceTownsGameController,
)
from power_grid.power_plant import PowerPlantNumber
from power_grid.simple_types import (
    GamePhase,
    PhaseStatus,
    PlayerColor,
    RequestError,
    Resource,
)


def _decode_json_or_raw(raw_state: str) -> object:
    try:
        parsed: object = json.loads(raw_state)
        return parsed
    except json.JSONDecodeError:
        return raw_state


def _validate_positive_int(value: int, label: str) -> RequestError | None:
    if isinstance(value, bool) or value < 1:
        return RequestError(f"Invalid {label}: {value}")
    return None


@dataclass(frozen=True)
class GamePhases:
    auction_power_plants: InterfaceAuctionPowerPlantsGameController
    buying_resources: InterfaceBuyingResourcesGameController
    building_houses: InterfaceBuildingHousesGameController
    bureaucracy: InterfaceBureaucracyGameController


@dataclass(frozen=True)
class GameBoardComponents:
    power_plant_market: InterfacePowerPlantMarketGameController
    resource_market: InterfaceResourceMarketGameController
    towns: InterfaceTownsGameController
    check_and_bump_step: InterfaceCheckAndBumpStepGameController


class GameController:
    def __init__(
        self,
        initial_player_order: Sequence[PlayerColor],
        player_boards: Mapping[PlayerColor, InterfacePlayerBoardGameController],
        phases: GamePhases,
        board: GameBoardComponents,
    ) -> None:
        order = list(initial_player_order)
        if len(order) < 2 or len(order) > 6:
            raise ValueError("Power Grid supports 2 to 6 players")
        if len(set(order)) != len(order):
            raise ValueError(
                "initial_player_order cannot contain duplicate players"
            )
        if set(order) != set(player_boards):
            raise ValueError(
                "initial_player_order must contain exactly the registered players"
            )

        self._player_boards: dict[
            PlayerColor, InterfacePlayerBoardGameController
        ] = dict(player_boards)
        self._phases = phases
        self._board = board
        self._is_first_turn = True
        self._game_phase = GamePhase.AUCTION_POWER_PLANTS
        self._player_order: list[PlayerColor] = order
        self._game_result: list[PlayerColor] = []

        self._phases.auction_power_plants.start_phase(list(self._player_order))

    @property
    def is_first_turn(self) -> bool:
        return self._is_first_turn

    @property
    def game_phase(self) -> GamePhase:
        return self._game_phase

    @property
    def player_order(self) -> list[PlayerColor]:
        return list(self._player_order)

    @property
    def game_result(self) -> list[PlayerColor]:
        return list(self._game_result)

    def select_power_plant_to_bid(
        self,
        player: PlayerColor,
        ppn: PowerPlantNumber,
        first_bid: int,
    ) -> RequestError | None:
        phase_error = self._ensure_phase_and_player(
            GamePhase.AUCTION_POWER_PLANTS, player
        )
        if phase_error is not None:
            return phase_error
        ppn_error = _validate_positive_int(ppn.number, "power plant number")
        if ppn_error is not None:
            return ppn_error
        bid_error = _validate_positive_int(first_bid, "bid")
        if bid_error is not None:
            return bid_error
        result = self._phases.auction_power_plants.select_power_plant_to_bid(
            player, ppn, first_bid
        )
        return self._handle_auction_result(result)

    def do_not_want_power_plant(
        self,
        player: PlayerColor,
    ) -> RequestError | None:
        phase_error = self._ensure_phase_and_player(
            GamePhase.AUCTION_POWER_PLANTS, player
        )
        if phase_error is not None:
            return phase_error
        result = self._phases.auction_power_plants.do_not_want_power_plant(
            player
        )
        return self._handle_auction_result(result)

    def bid_for_current_power_plant(
        self,
        player: PlayerColor,
        bid: int,
    ) -> RequestError | None:
        phase_error = self._ensure_phase_and_player(
            GamePhase.AUCTION_POWER_PLANTS, player
        )
        if phase_error is not None:
            return phase_error
        bid_error = _validate_positive_int(bid, "bid")
        if bid_error is not None:
            return bid_error
        result = self._phases.auction_power_plants.bid_for_current_power_plant(
            player, bid
        )
        return self._handle_auction_result(result)

    def do_not_bid_for_current_power_plant(
        self,
        player: PlayerColor,
    ) -> RequestError | None:
        phase_error = self._ensure_phase_and_player(
            GamePhase.AUCTION_POWER_PLANTS, player
        )
        if phase_error is not None:
            return phase_error
        auction = self._phases.auction_power_plants
        result = auction.do_not_bid_for_current_power_plant(player)
        return self._handle_auction_result(result)

    def remove_power_plant(
        self,
        player: PlayerColor,
        ppn: PowerPlantNumber,
        removed_resources: Sequence[Resource],
    ) -> RequestError | None:
        phase_error = self._ensure_phase_and_player(
            GamePhase.AUCTION_POWER_PLANTS, player
        )
        if phase_error is not None:
            return phase_error
        ppn_error = _validate_positive_int(ppn.number, "power plant number")
        if ppn_error is not None:
            return ppn_error
        result = self._phases.auction_power_plants.remove_power_plant(
            player, ppn, list(removed_resources)
        )
        return self._handle_auction_result(result)

    def buy_resources(
        self,
        player: PlayerColor,
        resources: Sequence[Resource],
    ) -> RequestError | None:
        phase_error = self._ensure_phase_and_player(
            GamePhase.BUY_RESOURCES, player
        )
        if phase_error is not None:
            return phase_error
        result = self._phases.buying_resources.buy_resources(
            player, list(resources)
        )
        if isinstance(result, RequestError):
            return result
        if result == PhaseStatus.GAME_ENDS:
            raise ValueError(
                "Buying resources phase cannot end the game with GAME_ENDS"
            )
        if result == PhaseStatus.PHASE_ENDS:
            self._game_phase = GamePhase.BUY_HOUSES
            self._phases.building_houses.start_phase(list(self._player_order))
        return None

    def buy_houses(
        self,
        player: PlayerColor,
        town_names: Sequence[str],
    ) -> RequestError | None:
        phase_error = self._ensure_phase_and_player(
            GamePhase.BUY_HOUSES, player
        )
        if phase_error is not None:
            return phase_error
        result = self._phases.building_houses.buy_houses(
            player, list(town_names)
        )
        if isinstance(result, RequestError):
            return result
        if result == PhaseStatus.GAME_ENDS:
            self._game_phase = GamePhase.GAME_END
            self._game_result = DeterminePlayerOrder(
                self._build_order_data()
            ).game_result()
        elif result == PhaseStatus.PHASE_ENDS:
            connected_counts = [
                self._board.towns.get_number_of_houses(color)
                for color in self._player_order
            ]
            self._board.check_and_bump_step.check_and_bump_to_step2(
                connected_counts
            )
            self._board.check_and_bump_step.check_and_bump_to_step3(
                self._board.power_plant_market.is_step3_start()
            )
            self._game_phase = GamePhase.BUREAUCRACY
            self._phases.bureaucracy.start_phase(list(self._player_order))
        return None

    def use_power_plants(
        self,
        player: PlayerColor,
        ppns: Sequence[PowerPlantNumber],
        resources_to_burn: Sequence[Resource],
    ) -> RequestError | None:
        phase_error = self._ensure_phase_and_player(
            GamePhase.BUREAUCRACY, player
        )
        if phase_error is not None:
            return phase_error
        ppn_list = list(ppns)
        for ppn in ppn_list:
            ppn_error = _validate_positive_int(
                ppn.number, "power plant number"
            )
            if ppn_error is not None:
                return ppn_error
        result = self._phases.bureaucracy.use_power_plants(
            player, ppn_list, list(resources_to_burn)
        )
        if isinstance(result, RequestError):
            return result
        if result == PhaseStatus.GAME_ENDS:
            raise ValueError(
                "Bureaucracy phase cannot end the game with GAME_ENDS"
            )
        if result == PhaseStatus.PHASE_ENDS:
            self._board.check_and_bump_step.check_and_bump_to_step3(
                self._board.power_plant_market.is_step3_start()
            )
            self._player_order = DeterminePlayerOrder(
                self._build_order_data()
            ).reorder()
            self._game_phase = GamePhase.AUCTION_POWER_PLANTS
            self._phases.auction_power_plants.start_phase(
                list(self._player_order)
            )
        return None

    def get_state(self) -> str:
        players_state: dict[str, object] = {
            color.name: _decode_json_or_raw(self._player_boards[color].state())
            for color in self._player_order
        }
        state: dict[str, object] = {
            "game_phase": self._game_phase.name,
            "is_first_turn": self._is_first_turn,
            "step": self._board.check_and_bump_step.get_step(),
            "player_order": [color.name for color in self._player_order],
            "phase_state": self._current_phase_state(),
            "resource_market": _decode_json_or_raw(
                self._board.resource_market.to_string()
            ),
            "players": players_state,
            "game_result": [color.name for color in self._game_result],
        }
        return json.dumps(state)

    def _ensure_phase_and_player(
        self,
        expected_phase: GamePhase,
        player: PlayerColor,
    ) -> RequestError | None:
        if self._game_phase == GamePhase.GAME_END:
            return RequestError("Game has already ended")
        if self._game_phase != expected_phase:
            return RequestError(
                f"Action is not allowed during {self._game_phase.name}; "
                f"expected {expected_phase.name}"
            )
        if player not in self._player_boards:
            return RequestError(f"Unregistered player: {player.name}")
        return None

    def _handle_auction_result(
        self,
        result: PhaseStatus | RequestError,
    ) -> RequestError | None:
        if isinstance(result, RequestError):
            return result
        if result == PhaseStatus.GAME_ENDS:
            raise ValueError(
                "Auction phase cannot end the game with GAME_ENDS"
            )
        if result == PhaseStatus.PHASE_ENDS:
            self._board.check_and_bump_step.check_and_bump_to_step3(
                self._board.power_plant_market.is_step3_start()
            )
            if self._is_first_turn:
                self._player_order = DeterminePlayerOrder(
                    self._build_order_data()
                ).reorder()
                self._is_first_turn = False
            self._game_phase = GamePhase.BUY_RESOURCES
            self._phases.buying_resources.start_phase(list(self._player_order))
        return None

    def _build_order_data(self) -> list[PlayerOrderData]:
        order_data: list[PlayerOrderData] = []
        for player in self._player_order:
            board = self._player_boards[player]
            connected_cities = self._board.towns.get_number_of_houses(player)
            powered_cities = min(
                connected_cities, board.number_of_connectable_cities()
            )
            order_data.append(
                PlayerOrderData(
                    color=player,
                    connected_cities=connected_cities,
                    largest_power_plant=board.best_power_plant_number(),
                    powered_cities=powered_cities,
                    remaining_money=board.outstanding_money(),
                )
            )
        return order_data

    def _current_phase_state(self) -> object:
        phase_getters: dict[GamePhase, Callable[[], str]] = {
            GamePhase.AUCTION_POWER_PLANTS: (
                self._phases.auction_power_plants.get_state
            ),
            GamePhase.BUY_RESOURCES: self._phases.buying_resources.get_state,
            GamePhase.BUY_HOUSES: self._phases.building_houses.get_state,
            GamePhase.BUREAUCRACY: self._phases.bureaucracy.get_state,
        }
        getter = phase_getters.get(self._game_phase)
        if getter is None:
            return None
        return _decode_json_or_raw(getter())
