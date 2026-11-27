from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence

from power_grid.connections import Connections
from power_grid.interfaces import InterfaceTownsBuildingHouses
from power_grid.simple_types import PlayerColor, RequestError


class Towns(InterfaceTownsBuildingHouses):
    HOUSE_SLOT_COSTS: tuple[int, int, int] = (10, 15, 20)

    def __init__(
        self,
        town_names: Sequence[str],
        connections: Connections,
        initial_houses: Mapping[str, Sequence[PlayerColor]] | None = None,
        step: int = 1,
    ) -> None:
        if isinstance(step, bool) or step not in (1, 2, 3):
            raise ValueError("step must be 1, 2, or 3")

        names = list(town_names)
        if not names:
            raise ValueError("town_names cannot be empty")
        if any(not town.strip() for town in names):
            raise ValueError(
                "town_names cannot contain empty or blank names"
            )
        town_set = set(names)
        if len(town_set) != len(names):
            raise ValueError("town_names cannot contain duplicate towns")

        active_distances = [
            edge
            for edge in connections.distances
            if edge[0] in town_set and edge[1] in town_set
        ]
        self._connections = Connections(active_distances)
        self._step = step
        self._houses: dict[str, list[PlayerColor]] = self._build_initial_houses(
            names, initial_houses, step
        )

    @property
    def step(self) -> int:
        return self._step

    @property
    def houses(self) -> dict[str, list[PlayerColor]]:
        return {town: list(owners) for town, owners in self._houses.items()}

    def buy_houses(
        self, player: PlayerColor, town_names: Sequence[str], max_money: int
    ) -> int | RequestError:
        if isinstance(max_money, bool) or max_money < 0:
            return RequestError(f"Invalid max_money: {max_money}")

        targets = list(town_names)
        if not targets:
            return 0

        total_cost = self._calculate_total_cost(player, targets)
        if isinstance(total_cost, RequestError):
            return total_cost

        if total_cost > max_money:
            return RequestError(
                f"Total cost {total_cost} exceeds available money {max_money}"
            )

        for town in targets:
            self._houses[town].append(player)
        return total_cost

    def get_number_of_houses(self, player: PlayerColor) -> int:
        return sum(1 for owners in self._houses.values() if player in owners)

    def get_max_number_of_houses(self) -> int:
        counts: Counter[PlayerColor] = Counter()
        for owners in self._houses.values():
            counts.update(owners)
        return max(counts.values(), default=0)

    def start_step2(self) -> None:
        if self._step != 1:
            raise ValueError(f"Cannot start step 2 from step {self._step}")
        self._step = 2

    def start_step3(self) -> None:
        if self._step >= 3:
            raise ValueError("Step 3 has already started")
        self._step = 3

    def to_string(self) -> str:
        payload: dict[str, object] = {
            "step": self._step,
            "houses": {
                town: [owner.name for owner in owners]
                for town, owners in self._houses.items()
            },
        }
        return json.dumps(payload)

    def _calculate_total_cost(
        self,
        player: PlayerColor,
        targets: list[str],
    ) -> int | RequestError:
        validation_error = self._validate_targets(player, targets)
        if validation_error is not None:
            return validation_error

        building_cost = sum(
            self.HOUSE_SLOT_COSTS[len(self._houses[town])]
            for town in targets
        )
        owned_towns = [
            town for town, owners in self._houses.items() if player in owners
        ]
        try:
            connecting_cost = self._connections.calculate_connecting_cost(
                owned_towns, targets
            )
        except ValueError as exc:
            return RequestError(str(exc))
        return building_cost + connecting_cost

    def _validate_targets(
        self,
        player: PlayerColor,
        targets: list[str],
    ) -> RequestError | None:
        if len(set(targets)) != len(targets):
            return RequestError("Cannot buy multiple houses in the same town")

        for town in targets:
            owners = self._houses.get(town)
            if owners is None:
                return RequestError(f"Unknown town: {town}")
            if player in owners:
                return RequestError(
                    f"Player {player.name} already owns a house in {town}"
                )
            if len(owners) >= self._step:
                return RequestError(
                    f"No free house slot in {town} during step {self._step}"
                )
        return None

    @staticmethod
    def _build_initial_houses(
        names: Sequence[str],
        initial_houses: Mapping[str, Sequence[PlayerColor]] | None,
        step: int,
    ) -> dict[str, list[PlayerColor]]:
        houses_map: dict[str, list[PlayerColor]] = {name: [] for name in names}
        if initial_houses is None:
            return houses_map

        for town_name, owners in initial_houses.items():
            if town_name not in houses_map:
                raise ValueError(
                    f"Unknown town in initial_houses: {town_name}"
                )
            owner_list = list(owners)
            if len(owner_list) > step:
                raise ValueError(
                    f"Town {town_name} exceeds slot limit for step {step}"
                )
            if len(set(owner_list)) != len(owner_list):
                raise ValueError(
                    f"Town {town_name} cannot contain duplicate players"
                )
            houses_map[town_name] = owner_list
        return houses_map
