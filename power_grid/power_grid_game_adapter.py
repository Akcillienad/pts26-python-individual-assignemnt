from __future__ import annotations

from collections.abc import Mapping, Sequence

from power_grid.interfaces import (
    InterfaceGameControllerAdapter,
    PowerGridRulesGameInterface,
)
from power_grid.power_plant import PowerPlantNumber
from power_grid.simple_types import (
    PlayerColor,
    RequestError,
    Resource,
    SerializedGameState,
)


class PowerGridGameAdapter(PowerGridRulesGameInterface):
    RESOURCE_CODE_MAP: dict[str, Resource] = {
        "C": Resource.COAL,
        "O": Resource.OIL,
        "G": Resource.GARBAGE,
        "U": Resource.URANIUM,
    }

    def __init__(
        self,
        controller: InterfaceGameControllerAdapter,
        player_id_to_color: Mapping[int, PlayerColor] | None = None,
    ) -> None:
        if player_id_to_color is None:
            mapping: dict[int, PlayerColor] = {
                color.value: color for color in PlayerColor
            }
        else:
            mapping = dict(player_id_to_color)
            if not mapping:
                raise ValueError("player_id_to_color cannot be empty")
            if len(set(mapping.values())) != len(mapping):
                raise ValueError(
                    "player_id_to_color cannot map multiple IDs to the same color"
                )

        self._controller = controller
        self._player_id_to_color: dict[int, PlayerColor] = mapping

    def select_power_plant_to_bid(
        self,
        player_id: int,
        power_plant_number: int,
        first_bid: int,
    ) -> SerializedGameState | RequestError:
        color = self._parse_player_id(player_id)
        if isinstance(color, RequestError):
            return color
        ppn = self._parse_power_plant_number(power_plant_number)
        if isinstance(ppn, RequestError):
            return ppn
        bid_error = self._validate_bid(first_bid)
        if bid_error is not None:
            return bid_error
        error = self._controller.select_power_plant_to_bid(
            color, ppn, first_bid
        )
        return self._finalize(error)

    def do_not_want_power_plant(
        self,
        player_id: int,
    ) -> SerializedGameState | RequestError:
        color = self._parse_player_id(player_id)
        if isinstance(color, RequestError):
            return color
        error = self._controller.do_not_want_power_plant(color)
        return self._finalize(error)

    def bid_for_current_power_plant(
        self,
        player_id: int,
        bid: int,
    ) -> SerializedGameState | RequestError:
        color = self._parse_player_id(player_id)
        if isinstance(color, RequestError):
            return color
        bid_error = self._validate_bid(bid)
        if bid_error is not None:
            return bid_error
        error = self._controller.bid_for_current_power_plant(color, bid)
        return self._finalize(error)

    def do_not_bid_for_current_power_plant(
        self,
        player_id: int,
    ) -> SerializedGameState | RequestError:
        color = self._parse_player_id(player_id)
        if isinstance(color, RequestError):
            return color
        error = self._controller.do_not_bid_for_current_power_plant(color)
        return self._finalize(error)

    def remove_power_plant(
        self,
        player_id: int,
        power_plant_number: int,
        removed_resources: str,
    ) -> SerializedGameState | RequestError:
        color = self._parse_player_id(player_id)
        if isinstance(color, RequestError):
            return color
        ppn = self._parse_power_plant_number(power_plant_number)
        if isinstance(ppn, RequestError):
            return ppn
        resources = self._parse_resources(removed_resources)
        if isinstance(resources, RequestError):
            return resources
        error = self._controller.remove_power_plant(color, ppn, resources)
        return self._finalize(error)

    def buy_resources(
        self,
        player_id: int,
        resources: str,
    ) -> SerializedGameState | RequestError:
        color = self._parse_player_id(player_id)
        if isinstance(color, RequestError):
            return color
        parsed_resources = self._parse_resources(resources)
        if isinstance(parsed_resources, RequestError):
            return parsed_resources
        error = self._controller.buy_resources(color, parsed_resources)
        return self._finalize(error)

    def buy_houses(
        self,
        player_id: int,
        town_names: Sequence[str],
    ) -> SerializedGameState | RequestError:
        color = self._parse_player_id(player_id)
        if isinstance(color, RequestError):
            return color
        error = self._controller.buy_houses(color, list(town_names))
        return self._finalize(error)

    def use_power_plants(
        self,
        player_id: int,
        power_plant_numbers: Sequence[int],
        resources_to_burn: str,
    ) -> SerializedGameState | RequestError:
        color = self._parse_player_id(player_id)
        if isinstance(color, RequestError):
            return color
        ppns: list[PowerPlantNumber] = []
        for number in power_plant_numbers:
            ppn = self._parse_power_plant_number(number)
            if isinstance(ppn, RequestError):
                return ppn
            ppns.append(ppn)
        parsed_resources = self._parse_resources(resources_to_burn)
        if isinstance(parsed_resources, RequestError):
            return parsed_resources
        error = self._controller.use_power_plants(
            color, ppns, parsed_resources
        )
        return self._finalize(error)

    def get_state(self) -> SerializedGameState:
        return SerializedGameState(self._controller.get_state())

    def _parse_player_id(self, player_id: int) -> PlayerColor | RequestError:
        if isinstance(player_id, bool):
            return RequestError(f"Unknown player_id: {player_id}")
        color = self._player_id_to_color.get(player_id)
        if color is None:
            return RequestError(f"Unknown player_id: {player_id}")
        return color

    def _parse_power_plant_number(
        self,
        number: int,
    ) -> PowerPlantNumber | RequestError:
        if isinstance(number, bool) or number <= 0:
            return RequestError(f"Invalid power plant number: {number}")
        return PowerPlantNumber(number)

    def _validate_bid(self, bid: int) -> RequestError | None:
        if isinstance(bid, bool) or bid < 1:
            return RequestError(f"Invalid bid: {bid}")
        return None

    def _parse_resources(self, encoded: str) -> list[Resource] | RequestError:
        parsed: list[Resource] = []
        for code in encoded:
            resource = self.RESOURCE_CODE_MAP.get(code)
            if resource is None:
                return RequestError(f"Invalid resource code: {code!r}")
            parsed.append(resource)
        return parsed

    def _finalize(
        self,
        error: RequestError | None,
    ) -> SerializedGameState | RequestError:
        if error is not None:
            return error
        return SerializedGameState(self._controller.get_state())


RESOURCE_CODE_MAP: dict[str, Resource] = PowerGridGameAdapter.RESOURCE_CODE_MAP
