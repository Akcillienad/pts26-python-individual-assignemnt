from __future__ import annotations

import random
from collections.abc import Mapping
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
from power_grid.power_plant_market import DeckShuffler, PowerPlantMarket
from power_grid.resource_market import ResourceMarket
from power_grid.resource_pool import ResourcePool
from power_grid.simple_types import PlayerColor, Resource
from power_grid.towns import Towns


@dataclass(frozen=True)
class PowerPlantSpec:
    """Immutable primitive description of a power plant card."""

    number: int
    accepted_resources: tuple[str, ...]
    resource_amount: int
    number_of_cities: int


@dataclass(frozen=True)
class GameSetupMetadata:  # pylint: disable=too-many-instance-attributes
    """Static setup metadata exposed alongside PowerGridRulesGameInterface."""

    player_id_to_color: dict[int, str]
    color_to_player_id: dict[str, int]
    plant_catalog: dict[int, PowerPlantSpec]
    town_names: tuple[str, ...]
    connections: tuple[tuple[str, str, int], ...]
    town_positions: dict[str, tuple[float, float]]
    end_game_town_count: int
    max_power_plants_per_player: int


@dataclass(frozen=True)
class GameSession:
    """Composed game interface and static setup metadata for clients/UI."""

    game: PowerGridRulesGameInterface
    metadata: GameSetupMetadata


_CARD_DEFS: tuple[tuple[int, tuple[Resource, ...], int, int], ...] = (
    # Plug cards (03-15)
    (3, (Resource.OIL,), 2, 1),
    (4, (Resource.COAL,), 2, 1),
    (5, (Resource.COAL, Resource.OIL), 2, 1),
    (6, (Resource.GARBAGE,), 1, 1),
    (7, (Resource.OIL,), 3, 2),
    (8, (Resource.COAL,), 3, 2),
    (9, (Resource.OIL,), 1, 1),
    (10, (Resource.COAL,), 2, 2),
    (11, (Resource.URANIUM,), 1, 2),
    (12, (Resource.COAL, Resource.OIL), 2, 2),
    (13, (), 0, 1),
    (14, (Resource.GARBAGE,), 2, 2),
    (15, (Resource.COAL,), 2, 3),
    # Socket cards (16-50)
    (16, (Resource.OIL,), 2, 3),
    (17, (Resource.URANIUM,), 1, 2),
    (18, (), 0, 2),
    (19, (Resource.GARBAGE,), 2, 3),
    (20, (Resource.COAL,), 3, 5),
    (21, (Resource.COAL, Resource.OIL), 2, 4),
    (22, (), 0, 2),
    (23, (Resource.URANIUM,), 1, 3),
    (24, (Resource.GARBAGE,), 2, 4),
    (25, (Resource.COAL,), 2, 5),
    (26, (Resource.OIL,), 2, 5),
    (27, (), 0, 3),
    (28, (Resource.URANIUM,), 1, 4),
    (29, (Resource.COAL, Resource.OIL), 1, 4),
    (30, (Resource.GARBAGE,), 3, 6),
    (31, (Resource.COAL,), 3, 6),
    (32, (Resource.OIL,), 3, 6),
    (33, (), 0, 4),
    (34, (Resource.URANIUM,), 1, 5),
    (35, (Resource.OIL,), 1, 5),
    (36, (Resource.COAL,), 3, 7),
    (37, (), 0, 4),
    (38, (Resource.GARBAGE,), 3, 7),
    (39, (Resource.URANIUM,), 1, 6),
    (40, (Resource.OIL,), 2, 6),
    (42, (Resource.COAL,), 2, 6),
    (44, (), 0, 5),
    (46, (Resource.COAL, Resource.OIL), 3, 7),
    (50, (), 0, 6),
)

_SOCKET_CARDS_REMOVED_BY_PLAYERS: dict[int, int] = {
    2: 8,
    3: 8,
    4: 4,
    5: 0,
    6: 0,
}

_REFILL_TABLES: dict[int, dict[int, dict[Resource, int]]] = {
    2: {
        1: {
            Resource.COAL: 3, Resource.OIL: 2,
            Resource.GARBAGE: 1, Resource.URANIUM: 1,
        },
        2: {
            Resource.COAL: 3, Resource.OIL: 2,
            Resource.GARBAGE: 2, Resource.URANIUM: 1,
        },
        3: {
            Resource.COAL: 3, Resource.OIL: 3,
            Resource.GARBAGE: 3, Resource.URANIUM: 2,
        },
    },
    3: {
        1: {
            Resource.COAL: 3, Resource.OIL: 2,
            Resource.GARBAGE: 1, Resource.URANIUM: 1,
        },
        2: {
            Resource.COAL: 4, Resource.OIL: 3,
            Resource.GARBAGE: 2, Resource.URANIUM: 1,
        },
        3: {
            Resource.COAL: 3, Resource.OIL: 4,
            Resource.GARBAGE: 3, Resource.URANIUM: 2,
        },
    },
    4: {
        1: {
            Resource.COAL: 4, Resource.OIL: 3,
            Resource.GARBAGE: 2, Resource.URANIUM: 1,
        },
        2: {
            Resource.COAL: 5, Resource.OIL: 3,
            Resource.GARBAGE: 3, Resource.URANIUM: 2,
        },
        3: {
            Resource.COAL: 4, Resource.OIL: 4,
            Resource.GARBAGE: 3, Resource.URANIUM: 2,
        },
    },
    5: {
        1: {
            Resource.COAL: 5, Resource.OIL: 4,
            Resource.GARBAGE: 3, Resource.URANIUM: 2,
        },
        2: {
            Resource.COAL: 6, Resource.OIL: 4,
            Resource.GARBAGE: 4, Resource.URANIUM: 3,
        },
        3: {
            Resource.COAL: 5, Resource.OIL: 5,
            Resource.GARBAGE: 4, Resource.URANIUM: 3,
        },
    },
    6: {
        1: {
            Resource.COAL: 5, Resource.OIL: 5,
            Resource.GARBAGE: 4, Resource.URANIUM: 3,
        },
        2: {
            Resource.COAL: 7, Resource.OIL: 5,
            Resource.GARBAGE: 5, Resource.URANIUM: 3,
        },
        3: {
            Resource.COAL: 7, Resource.OIL: 6,
            Resource.GARBAGE: 5, Resource.URANIUM: 4,
        },
    },
}

_TOWN_POSITIONS: dict[str, tuple[float, float]] = {
    "Kiel": (0.28, 0.10),
    "Rostock": (0.62, 0.10),
    "Hamburg": (0.34, 0.24),
    "Bremen": (0.14, 0.26),
    "Berlin": (0.76, 0.26),
    "Hannover": (0.36, 0.40),
    "Essen": (0.10, 0.44),
    "Dortmund": (0.22, 0.46),
    "Leipzig": (0.64, 0.44),
    "Dresden": (0.86, 0.44),
    "Cologne": (0.12, 0.60),
    "Kassel": (0.36, 0.56),
    "Erfurt": (0.56, 0.58),
    "Frankfurt": (0.26, 0.70),
    "Nuremberg": (0.60, 0.72),
    "Regensburg": (0.82, 0.68),
    "Mannheim": (0.20, 0.82),
    "Stuttgart": (0.42, 0.82),
    "Augsburg": (0.62, 0.86),
    "Munich": (0.82, 0.88),
    "Freiburg": (0.16, 0.92),
}

_MAP_CONNECTIONS: tuple[tuple[str, str, int], ...] = (
    ("Kiel", "Hamburg", 8),
    ("Kiel", "Rostock", 11),
    ("Rostock", "Hamburg", 12),
    ("Rostock", "Berlin", 15),
    ("Bremen", "Hamburg", 11),
    ("Bremen", "Hannover", 10),
    ("Bremen", "Essen", 14),
    ("Hamburg", "Hannover", 13),
    ("Hamburg", "Berlin", 17),
    ("Berlin", "Leipzig", 14),
    ("Berlin", "Dresden", 13),
    ("Hannover", "Dortmund", 12),
    ("Hannover", "Kassel", 10),
    ("Hannover", "Leipzig", 15),
    ("Essen", "Dortmund", 4),
    ("Essen", "Cologne", 6),
    ("Dortmund", "Cologne", 7),
    ("Dortmund", "Kassel", 13),
    ("Leipzig", "Dresden", 9),
    ("Leipzig", "Erfurt", 10),
    ("Dresden", "Regensburg", 18),
    ("Cologne", "Frankfurt", 14),
    ("Kassel", "Erfurt", 11),
    ("Kassel", "Frankfurt", 13),
    ("Erfurt", "Nuremberg", 14),
    ("Frankfurt", "Mannheim", 7),
    ("Frankfurt", "Nuremberg", 16),
    ("Nuremberg", "Regensburg", 9),
    ("Nuremberg", "Stuttgart", 13),
    ("Nuremberg", "Augsburg", 12),
    ("Regensburg", "Munich", 10),
    ("Mannheim", "Stuttgart", 6),
    ("Mannheim", "Freiburg", 14),
    ("Stuttgart", "Freiburg", 13),
    ("Stuttgart", "Augsburg", 11),
    ("Augsburg", "Munich", 6),
)


def _build_plant_catalog() -> dict[int, PowerPlantSpec]:
    return {
        num: PowerPlantSpec(
            number=num,
            accepted_resources=tuple(res.name for res in resources),
            resource_amount=amount,
            number_of_cities=cities,
        )
        for num, resources, amount, cities in _CARD_DEFS
    }


def _build_power_plant(
    spec_tuple: tuple[int, tuple[Resource, ...], int, int],
) -> PowerPlant:
    num, resources, amount, cities = spec_tuple
    return PowerPlant(
        PowerPlantNumber(num), list(resources), amount, cities
    )


def _resolve_shuffler(
    shuffler: DeckShuffler | None, seed: int | None
) -> DeckShuffler:
    if shuffler is not None and seed is not None:
        raise ValueError("Cannot specify both shuffler and seed")
    if shuffler is not None:
        if not callable(shuffler):
            raise ValueError("shuffler must be callable or None")
        return shuffler
    return random.Random(seed).shuffle


def _build_initial_market_and_deck(
    player_count: int, shuffler: DeckShuffler
) -> tuple[list[PowerPlant], list[PowerPlant], list[PowerPlant]]:
    plug_cards = [_build_power_plant(entry) for entry in _CARD_DEFS[:13]]
    socket_cards = [_build_power_plant(entry) for entry in _CARD_DEFS[13:]]
    shuffler(plug_cards)
    shuffler(socket_cards)

    initial_market = sorted(
        plug_cards[:8], key=lambda plant: plant.number.number
    )
    top_plug_card = plug_cards[8]
    remove_count = _SOCKET_CARDS_REMOVED_BY_PLAYERS[player_count]
    kept_sockets = socket_cards[remove_count:]
    deck_above = [top_plug_card] + kept_sockets
    return initial_market[:4], initial_market[4:], deck_above


def _validate_factory_args(
    player_count: int,
    starting_money: int,
    end_game_town_count: int | None,
) -> int:
    if (
        isinstance(player_count, bool)
        or not isinstance(player_count, int)
        or player_count < 2
        or player_count > 6
    ):
        raise ValueError("player_count must be an integer between 2 and 6")
    if (
        isinstance(starting_money, bool)
        or not isinstance(starting_money, int)
        or starting_money < 0
    ):
        raise ValueError("starting_money must be a non-negative integer")
    if end_game_town_count is None:
        return BuildingHouses.END_GAME_CITY_THRESHOLDS[player_count]
    if (
        isinstance(end_game_town_count, bool)
        or not isinstance(end_game_town_count, int)
        or end_game_town_count < 1
        or end_game_town_count > len(_TOWN_POSITIONS)
    ):
        raise ValueError(
            "end_game_town_count must be between 1 and "
            f"{len(_TOWN_POSITIONS)}"
        )
    return end_game_town_count


def _build_resource_system(
    player_count: int,
) -> tuple[ResourcePool, ResourceMarket]:
    pool = ResourcePool(
        resources=(
            [Resource.OIL] * 6
            + [Resource.GARBAGE] * 18
            + [Resource.URANIUM] * 10
        ),
        storage_space=[],
    )
    resource_market = ResourceMarket(
        pool=pool,
        starting_resources=(
            [Resource.COAL] * 24
            + [Resource.OIL] * 18
            + [Resource.GARBAGE] * 6
            + [Resource.URANIUM] * 2
        ),
        refilling_pattern=_REFILL_TABLES[player_count],
    )
    return pool, resource_market


def _build_player_boards(
    player_colors: list[PlayerColor],
    starting_money: int,
    max_plants: int,
    board_context: PlayerBoardContext,
) -> dict[PlayerColor, PlayerBoardFacade]:
    return {
        color: PlayerBoardFacade(
            PlayerMoney(color, starting_money),
            PlayerPowerPlants(max_plants=max_plants),
            board_context,
        )
        for color in player_colors
    }


def _build_metadata(
    id_to_color: Mapping[int, PlayerColor],
    resolved_end_game: int,
    max_plants: int,
) -> GameSetupMetadata:
    return GameSetupMetadata(
        player_id_to_color={
            player_id: color.name for player_id, color in id_to_color.items()
        },
        color_to_player_id={
            color.name: player_id for player_id, color in id_to_color.items()
        },
        plant_catalog=_build_plant_catalog(),
        town_names=tuple(_TOWN_POSITIONS.keys()),
        connections=_MAP_CONNECTIONS,
        town_positions=dict(_TOWN_POSITIONS),
        end_game_town_count=resolved_end_game,
        max_power_plants_per_player=max_plants,
    )


def _build_plant_market(
    player_count: int, shuffler: DeckShuffler
) -> PowerPlantMarket:
    row1, row2, deck_above = _build_initial_market_and_deck(
        player_count, shuffler
    )
    return PowerPlantMarket(
        row1=row1,
        row2=row2,
        deck_above_step3=deck_above,
        deck_below_step3=[],
        shuffler=shuffler,
    )


def _build_board_components(
    player_count: int,
    resource_market: ResourceMarket,
    shuffler: DeckShuffler,
) -> tuple[GameBoardComponents, Towns]:
    towns = Towns(
        tuple(_TOWN_POSITIONS.keys()), Connections(list(_MAP_CONNECTIONS))
    )
    plant_market = _build_plant_market(player_count, shuffler)
    board = GameBoardComponents(
        plant_market,
        resource_market,
        towns,
        CheckAndBumpStep(player_count, [resource_market, towns, plant_market]),
    )
    return board, towns


def _build_game_adapter(
    *,
    player_colors: list[PlayerColor],
    player_boards: dict[PlayerColor, PlayerBoardFacade],
    board_components: GameBoardComponents,
    resolved_end_game: int,
) -> tuple[PowerGridGameAdapter, dict[int, PlayerColor]]:
    plant_market = board_components.power_plant_market
    resource_market = board_components.resource_market
    towns = board_components.towns
    assert isinstance(plant_market, PowerPlantMarket)
    assert isinstance(resource_market, ResourceMarket)
    assert isinstance(towns, Towns)
    phases = GamePhases(
        AuctionPowerPlants(plant_market, player_boards, is_first_round=True),
        BuyingResources(player_boards),
        BuildingHouses(
            towns,
            plant_market,
            player_boards,
            end_game_town_count=resolved_end_game,
        ),
        Bureaucracy(player_boards, resource_market, plant_market),
    )
    controller = GameController(
        player_colors, player_boards, phases, board_components
    )
    id_to_color = {idx + 1: color for idx, color in enumerate(player_colors)}
    return PowerGridGameAdapter(controller, id_to_color), id_to_color


def create_standard_game(
    player_count: int = 3,
    *,
    starting_money: int = 50,
    end_game_town_count: int | None = None,
    shuffler: DeckShuffler | None = None,
    seed: int | None = None,
) -> GameSession:
    """Create a fully wired standard Power Grid Recharged game session."""
    resolved_end_game = _validate_factory_args(
        player_count, starting_money, end_game_town_count
    )
    pool, resource_market = _build_resource_system(player_count)
    board_components, towns = _build_board_components(
        player_count, resource_market, _resolve_shuffler(shuffler, seed)
    )
    player_colors = list(PlayerColor)[:player_count]
    max_plants = 4 if player_count == 2 else 3
    player_boards = _build_player_boards(
        player_colors,
        starting_money,
        max_plants,
        PlayerBoardContext(resource_market, pool, towns),
    )
    adapter, id_to_color = _build_game_adapter(
        player_colors=player_colors,
        player_boards=player_boards,
        board_components=board_components,
        resolved_end_game=resolved_end_game,
    )
    return GameSession(
        game=adapter,
        metadata=_build_metadata(id_to_color, resolved_end_game, max_plants),
    )
