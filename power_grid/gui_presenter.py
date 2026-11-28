from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from power_grid.factories import GameSession, GameSetupMetadata
from power_grid.simple_types import RequestError, SerializedGameState


@dataclass(frozen=True)
class PlayerView:
    color: str
    money: int
    power_plants: tuple[int, ...]
    resources: tuple[str, ...]


@dataclass(frozen=True)
class PowerPlantMarketView:  # pylint: disable=too-many-instance-attributes
    step: int
    is_step3: bool
    is_step3_start: bool
    is_first_power_plant_discounted: bool
    row1: tuple[int, ...]
    row2: tuple[int, ...]
    deck_above_step3_count: int
    deck_below_step3_count: int


@dataclass(frozen=True)
class ResourceMarketView:
    coal: int
    oil: int
    garbage: int
    uranium: int
    pool_resources: tuple[str, ...]
    pool_storage_space: tuple[str, ...]


@dataclass(frozen=True)
class TownsView:
    step: int
    houses: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class PhaseView:  # pylint: disable=too-many-instance-attributes
    is_active: bool
    current_player: str | None
    stage: str | None
    is_first_round: bool | None
    eligible_players: tuple[str, ...]
    remaining_players: tuple[str, ...]
    current_plant: int | None
    current_bid: int | None
    highest_bidder: str | None
    active_bidders: tuple[str, ...]
    pending_removal_player: str | None
    pending_removal_bought_plant: int | None
    end_game_town_count: int | None


@dataclass(frozen=True)
class GameViewState:  # pylint: disable=too-many-instance-attributes
    game_phase: str
    is_first_turn: bool
    step: int
    player_order: tuple[str, ...]
    phase_state: PhaseView | None
    power_plant_market: PowerPlantMarketView
    resource_market: ResourceMarketView
    towns: TownsView
    players: dict[str, PlayerView]
    game_result: tuple[str, ...]


def _as_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object for {label}")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"Expected string keys in {label}")
        result[key] = item
    return result


def _as_str(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Expected string for {label}")
    return value


def _as_optional_str(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _as_str(value, label)


def _as_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"Expected bool for {label}")
    return value


def _as_optional_bool(value: object, label: str) -> bool | None:
    if value is None:
        return None
    return _as_bool(value, label)


def _as_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Expected integer for {label}")
    return value


def _as_optional_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _as_int(value, label)


def _as_str_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"Expected list for {label}")
    return tuple(_as_str(item, f"{label}[]") for item in value)


def _as_int_tuple(value: object, label: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ValueError(f"Expected list for {label}")
    return tuple(_as_int(item, f"{label}[]") for item in value)


def _parse_phase_view(raw_phase: object) -> PhaseView | None:
    if raw_phase is None:
        return None
    data = _as_dict(raw_phase, "phase_state")
    eligible = (
        _as_str_tuple(data["eligible_players"], "eligible_players")
        if "eligible_players" in data
        else ()
    )
    remaining = (
        _as_str_tuple(data["remaining_players"], "remaining_players")
        if "remaining_players" in data
        else ()
    )
    bidders = (
        _as_str_tuple(data["active_bidders"], "active_bidders")
        if "active_bidders" in data
        else ()
    )
    return PhaseView(
        is_active=_as_bool(data.get("is_active"), "phase_state.is_active"),
        current_player=_as_optional_str(
            data.get("current_player"), "phase_state.current_player"
        ),
        stage=_as_optional_str(data.get("stage"), "phase_state.stage"),
        is_first_round=_as_optional_bool(
            data.get("is_first_round"), "phase_state.is_first_round"
        ),
        eligible_players=eligible,
        remaining_players=remaining,
        current_plant=_as_optional_int(
            data.get("current_plant"), "phase_state.current_plant"
        ),
        current_bid=_as_optional_int(
            data.get("current_bid"), "phase_state.current_bid"
        ),
        highest_bidder=_as_optional_str(
            data.get("highest_bidder"), "phase_state.highest_bidder"
        ),
        active_bidders=bidders,
        pending_removal_player=_as_optional_str(
            data.get("pending_removal_player"),
            "phase_state.pending_removal_player",
        ),
        pending_removal_bought_plant=_as_optional_int(
            data.get("pending_removal_bought_plant"),
            "phase_state.pending_removal_bought_plant",
        ),
        end_game_town_count=_as_optional_int(
            data.get("end_game_town_count"),
            "phase_state.end_game_town_count",
        ),
    )


def _parse_plant_market(raw_market: object) -> PowerPlantMarketView:
    data = _as_dict(raw_market, "power_plant_market")
    return PowerPlantMarketView(
        step=_as_int(data.get("step"), "power_plant_market.step"),
        is_step3=_as_bool(
            data.get("is_step3"), "power_plant_market.is_step3"
        ),
        is_step3_start=_as_bool(
            data.get("is_step3_start"), "power_plant_market.is_step3_start"
        ),
        is_first_power_plant_discounted=_as_bool(
            data.get("is_first_power_plant_discounted"),
            "power_plant_market.is_first_power_plant_discounted",
        ),
        row1=_as_int_tuple(data.get("row1"), "power_plant_market.row1"),
        row2=_as_int_tuple(data.get("row2"), "power_plant_market.row2"),
        deck_above_step3_count=_as_int(
            data.get("deck_above_step3_count"),
            "power_plant_market.deck_above_step3_count",
        ),
        deck_below_step3_count=_as_int(
            data.get("deck_below_step3_count"),
            "power_plant_market.deck_below_step3_count",
        ),
    )


def _parse_resource_market(raw_market: object) -> ResourceMarketView:
    data = _as_dict(raw_market, "resource_market")
    pool = _as_dict(data.get("pool"), "resource_market.pool")
    return ResourceMarketView(
        coal=_as_int(data.get("coal"), "resource_market.coal"),
        oil=_as_int(data.get("oil"), "resource_market.oil"),
        garbage=_as_int(data.get("garbage"), "resource_market.garbage"),
        uranium=_as_int(data.get("uranium"), "resource_market.uranium"),
        pool_resources=_as_str_tuple(
            pool.get("resources"), "resource_market.pool.resources"
        ),
        pool_storage_space=_as_str_tuple(
            pool.get("storage_space"), "resource_market.pool.storage_space"
        ),
    )


def _parse_towns(raw_towns: object) -> TownsView:
    data = _as_dict(raw_towns, "towns")
    raw_houses = _as_dict(data.get("houses"), "towns.houses")
    houses = {
        town: _as_str_tuple(owners, f"towns.houses.{town}")
        for town, owners in raw_houses.items()
    }
    return TownsView(
        step=_as_int(data.get("step"), "towns.step"),
        houses=houses,
    )


def _parse_players(raw_players: object) -> dict[str, PlayerView]:
    data = _as_dict(raw_players, "players")
    parsed: dict[str, PlayerView] = {}
    for color_name, raw_board in data.items():
        board = _as_dict(raw_board, f"players.{color_name}")
        parsed[color_name] = PlayerView(
            color=_as_str(board.get("color"), f"players.{color_name}.color"),
            money=_as_int(board.get("money"), f"players.{color_name}.money"),
            power_plants=_as_int_tuple(
                board.get("power_plants"),
                f"players.{color_name}.power_plants",
            ),
            resources=_as_str_tuple(
                board.get("resources"), f"players.{color_name}.resources"
            ),
        )
    return parsed


def parse_game_view_state(serialized: SerializedGameState) -> GameViewState:
    """Decode SerializedGameState JSON into typed view models."""
    try:
        decoded: object = json.loads(serialized.state)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed game state JSON: {exc}") from exc

    root = _as_dict(decoded, "root")
    return GameViewState(
        game_phase=_as_str(root.get("game_phase"), "game_phase"),
        is_first_turn=_as_bool(root.get("is_first_turn"), "is_first_turn"),
        step=_as_int(root.get("step"), "step"),
        player_order=_as_str_tuple(root.get("player_order"), "player_order"),
        phase_state=_parse_phase_view(root.get("phase_state")),
        power_plant_market=_parse_plant_market(root.get("power_plant_market")),
        resource_market=_parse_resource_market(root.get("resource_market")),
        towns=_parse_towns(root.get("towns")),
        players=_parse_players(root.get("players")),
        game_result=_as_str_tuple(root.get("game_result"), "game_result"),
    )


class PowerGridGuiPresenter:
    """Thin presentation bridge strictly bound to PowerGridRulesGameInterface."""

    def __init__(self, session: GameSession) -> None:
        self._game = session.game
        self._metadata = session.metadata
        self._last_error: str | None = None
        self._view_state = parse_game_view_state(self._game.get_state())

    @property
    def metadata(self) -> GameSetupMetadata:
        return self._metadata

    @property
    def view_state(self) -> GameViewState:
        return self._view_state

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def current_player_color(self) -> str | None:
        if self._view_state.phase_state is None:
            return None
        return self._view_state.phase_state.current_player

    @property
    def current_player_id(self) -> int | None:
        color = self.current_player_color
        if color is None:
            return None
        return self._metadata.color_to_player_id.get(color)

    def refresh(self) -> GameViewState:
        self._view_state = parse_game_view_state(self._game.get_state())
        return self._view_state

    def format_plant_spec(self, plant_number: int) -> str:
        spec = self._metadata.plant_catalog.get(plant_number)
        if spec is None:
            return f"#{plant_number}"
        if spec.resource_amount == 0 or not spec.accepted_resources:
            fuel_label = "ECO"
        else:
            fuel_names = "/".join(res[0] for res in spec.accepted_resources)
            fuel_label = f"{spec.resource_amount}{fuel_names}"
        return f"#{spec.number} [{fuel_label} -> {spec.number_of_cities}C]"

    def select_power_plant(
        self, player_id: int, plant_number: int, first_bid: int
    ) -> str | None:
        return self._apply(
            self._game.select_power_plant_to_bid(
                player_id, plant_number, first_bid
            )
        )

    def pass_select_power_plant(self, player_id: int) -> str | None:
        return self._apply(self._game.do_not_want_power_plant(player_id))

    def bid_current_power_plant(
        self, player_id: int, bid: int
    ) -> str | None:
        return self._apply(
            self._game.bid_for_current_power_plant(player_id, bid)
        )

    def pass_bid_current_power_plant(self, player_id: int) -> str | None:
        return self._apply(
            self._game.do_not_bid_for_current_power_plant(player_id)
        )

    def remove_power_plant(
        self, player_id: int, plant_number: int, removed_resources: str
    ) -> str | None:
        return self._apply(
            self._game.remove_power_plant(
                player_id, plant_number, removed_resources
            )
        )

    def buy_resources(self, player_id: int, resources: str) -> str | None:
        return self._apply(self._game.buy_resources(player_id, resources))

    def buy_houses(
        self, player_id: int, town_names: Sequence[str]
    ) -> str | None:
        return self._apply(self._game.buy_houses(player_id, list(town_names)))

    def use_power_plants(
        self,
        player_id: int,
        plant_numbers: Sequence[int],
        resources_to_burn: str,
    ) -> str | None:
        return self._apply(
            self._game.use_power_plants(
                player_id, list(plant_numbers), resources_to_burn
            )
        )

    def _apply(
        self, result: SerializedGameState | RequestError
    ) -> str | None:
        if isinstance(result, RequestError):
            self._last_error = result.description
            return result.description
        self._view_state = parse_game_view_state(result)
        self._last_error = None
        return None
