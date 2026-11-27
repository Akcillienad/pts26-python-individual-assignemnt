from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager

from power_grid.interfaces import InterfacePowerPlantMarketBuildingHouses
from power_grid.power_plant import PowerPlant, PowerPlantNumber
from power_grid.simple_types import RequestError

DeckShuffler = Callable[[list[PowerPlant]], None]


class PowerPlantMarket(InterfacePowerPlantMarketBuildingHouses):  # pylint: disable=too-many-instance-attributes
    STEP_1_2_ROW_SIZE: int = 4
    STEP_3_MARKET_SIZE: int = 6

    def __init__(  # pylint: disable=too-many-arguments
        self,
        row1: Sequence[PowerPlant],
        row2: Sequence[PowerPlant] = (),
        deck_above_step3: Sequence[PowerPlant] = (),
        deck_below_step3: Sequence[PowerPlant] = (),
        *,
        is_first_power_plant_discounted: bool | None = None,
        step: int = 1,
        step3_card_drawn: bool = False,
        shuffler: DeckShuffler | None = None,
    ) -> None:
        self._validate_flags(
            step, step3_card_drawn, is_first_power_plant_discounted
        )
        if shuffler is not None and not callable(shuffler):
            raise ValueError("shuffler must be callable or None")

        row1_list = list(row1)
        row2_list = list(row2)
        deck_above_list = list(deck_above_step3)
        deck_below_list = list(deck_below_step3)

        self._validate_plants(
            (row1_list, row2_list, deck_above_list, deck_below_list)
        )
        self._validate_structure(
            step, step3_card_drawn, row1_list, row2_list, deck_above_list
        )

        self._step = step
        self._step3_card_drawn = step3_card_drawn
        self._deck_above_step3: list[PowerPlant] = deck_above_list
        self._deck_below_step3: list[PowerPlant] = deck_below_list
        self._shuffler: DeckShuffler = (
            shuffler if shuffler is not None else random.Random().shuffle
        )

        sorted_market = sorted(
            row1_list + row2_list, key=lambda plant: plant.number.number
        )
        if self._step == 3:
            self._row1: list[PowerPlant] = sorted_market
            self._row2: list[PowerPlant] = []
        else:
            self._row1 = sorted_market[: self.STEP_1_2_ROW_SIZE]
            self._row2 = sorted_market[self.STEP_1_2_ROW_SIZE :]

        if is_first_power_plant_discounted is None:
            self._is_first_power_plant_discounted = bool(self._row1)
        elif is_first_power_plant_discounted and not self._row1:
            raise ValueError(
                "Cannot discount a power plant in an empty market"
            )
        else:
            self._is_first_power_plant_discounted = (
                is_first_power_plant_discounted
            )

    @property
    def step(self) -> int:
        return self._step

    @property
    def is_step3(self) -> bool:
        return self._step == 3

    @property
    def is_first_power_plant_discounted(self) -> bool:
        return self._is_first_power_plant_discounted

    @property
    def power_plant_selection_row1(self) -> list[PowerPlant]:
        return list(self._row1)

    @property
    def power_plant_selection_row2(self) -> list[PowerPlant]:
        return list(self._row2)

    @property
    def power_plant_deck_above_3rd_step(self) -> list[PowerPlant]:
        return list(self._deck_above_step3)

    @property
    def power_plant_deck_below_3rd_step(self) -> list[PowerPlant]:
        return list(self._deck_below_step3)

    def can_take_power_plant(
        self, ppn: PowerPlantNumber, price: int
    ) -> RequestError | None:
        if not self._is_valid_positive_int(ppn.number):
            return RequestError(f"Invalid power plant number: {ppn.number}")
        if not self._is_valid_positive_int(price):
            return RequestError(f"Invalid price: {price}")

        found = self._find_in_row1(ppn.number)
        if found is None:
            if any(plant.number.number == ppn.number for plant in self._row2):
                return RequestError(
                    f"Power plant {ppn.number} is in the future market "
                    "and cannot be taken"
                )
            return RequestError(
                f"Power plant {ppn.number} is not available in the market"
            )

        idx, plant = found
        min_price = (
            1
            if (self._is_first_power_plant_discounted and idx == 0)
            else plant.number.number
        )
        if price < min_price:
            return RequestError(
                f"Price {price} is below minimum price {min_price} "
                f"for power plant {ppn.number}"
            )
        return None

    def take_power_plant(self, ppn: PowerPlantNumber) -> PowerPlant:
        if not self._is_valid_positive_int(ppn.number):
            raise ValueError(f"Invalid power plant number: {ppn.number}")

        found = self._find_in_row1(ppn.number)
        if found is None:
            if any(plant.number.number == ppn.number for plant in self._row2):
                raise ValueError(
                    f"Power plant {ppn.number} is in the future market "
                    "and cannot be taken"
                )
            raise ValueError(
                f"Power plant {ppn.number} is not available in the market"
            )

        idx, _ = found
        with self._atomic_mutation():
            took_discounted = self._is_first_power_plant_discounted and idx == 0
            discounted_number = (
                self._row1[0].number.number
                if (
                    self._is_first_power_plant_discounted
                    and not took_discounted
                )
                else None
            )

            taken_plant = self._row1.pop(idx)
            if took_discounted:
                self._is_first_power_plant_discounted = False

            replacement = self._draw_replacement()
            if (
                replacement is not None
                and discounted_number is not None
                and replacement.number.number < discounted_number
            ):
                self._is_first_power_plant_discounted = False
                replacement = self._draw_replacement()

            market_plants = self._row1 + self._row2
            if replacement is not None:
                market_plants.append(replacement)
            self._rebalance_market(market_plants)
            return taken_plant

    def remove_discounted_power_plant(self) -> None:
        with self._atomic_mutation():
            if not self._is_first_power_plant_discounted or not self._row1:
                self._is_first_power_plant_discounted = False
                return

            self._row1.pop(0)
            self._is_first_power_plant_discounted = False
            replacement = self._draw_replacement()
            market_plants = self._row1 + self._row2
            if replacement is not None:
                market_plants.append(replacement)
            self._rebalance_market(market_plants)

    def remove_power_plants_cheaper_than(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("value must be a non-negative integer")

        with self._atomic_mutation():
            while self._row1 and self._row1[0].number.number <= value:
                self._row1.pop(0)
                self._is_first_power_plant_discounted = False
                replacement = self._draw_replacement()
                market_plants = self._row1 + self._row2
                if replacement is not None:
                    market_plants.append(replacement)
                self._rebalance_market(market_plants)

    def prepare_next_turn(self) -> None:
        with self._atomic_mutation():
            if self._step < 3:
                all_plants = self._row1 + self._row2
                if all_plants:
                    highest_plant = all_plants.pop()
                    self._deck_below_step3.append(highest_plant)
                    self._rebalance_market(all_plants)
                    replacement = self._draw_replacement()
                    if replacement is not None:
                        all_plants.append(replacement)
                    self._rebalance_market(all_plants)
            else:
                if self._row1:
                    self._row1.pop(0)
                    replacement = self._draw_replacement()
                    market_plants = list(self._row1)
                    if replacement is not None:
                        market_plants.append(replacement)
                    self._rebalance_market(market_plants)

            self._is_first_power_plant_discounted = bool(self._row1)

    def is_step3_start(self) -> bool:
        return self._step3_card_drawn and self._step < 3

    def start_step2(self) -> None:
        if self._step != 1:
            raise ValueError(f"Cannot start step 2 from step {self._step}")

        with self._atomic_mutation():
            self._step = 2
            if not self._step3_card_drawn and self._row1:
                self._row1.pop(0)
                self._is_first_power_plant_discounted = False
                replacement = self._draw_replacement()
                market_plants = self._row1 + self._row2
                if replacement is not None:
                    market_plants.append(replacement)
                self._rebalance_market(market_plants)

    def start_step3(self) -> None:
        if self._step >= 3:
            raise ValueError("Step 3 has already started")

        with self._atomic_mutation():
            was_step3_card_drawn = self._step3_card_drawn
            self._step = 3
            self._step3_card_drawn = False

            market_plants = self._row1 + self._row2
            if market_plants:
                market_plants.pop(0)

            if not was_step3_card_drawn:
                if self._deck_above_step3:
                    self._deck_below_step3.extend(self._deck_above_step3)
                    self._deck_above_step3.clear()
                if len(market_plants) > self.STEP_3_MARKET_SIZE:
                    self._deck_below_step3.extend(
                        market_plants[self.STEP_3_MARKET_SIZE :]
                    )
                    market_plants = market_plants[: self.STEP_3_MARKET_SIZE]
                self._shuffle_deck_below()

            self._row1 = sorted(
                market_plants, key=lambda plant: plant.number.number
            )
            self._row2 = []
            if not self._row1:
                self._is_first_power_plant_discounted = False

    def to_string(self) -> str:
        payload: dict[str, object] = {
            "step": self._step,
            "is_step3": self.is_step3,
            "is_step3_start": self.is_step3_start(),
            "is_first_power_plant_discounted": (
                self._is_first_power_plant_discounted
            ),
            "row1": [plant.number.number for plant in self._row1],
            "row2": [plant.number.number for plant in self._row2],
            "deck_above_step3_count": len(self._deck_above_step3),
            "deck_below_step3_count": len(self._deck_below_step3),
        }
        return json.dumps(payload)

    @contextmanager
    def _atomic_mutation(self) -> Iterator[None]:
        snapshot = (
            self._step,
            self._step3_card_drawn,
            self._is_first_power_plant_discounted,
            list(self._row1),
            list(self._row2),
            list(self._deck_above_step3),
            list(self._deck_below_step3),
        )
        try:
            yield
        except Exception:
            (
                self._step,
                self._step3_card_drawn,
                self._is_first_power_plant_discounted,
                self._row1,
                self._row2,
                self._deck_above_step3,
                self._deck_below_step3,
            ) = snapshot
            raise

    def _draw_replacement(self) -> PowerPlant | None:
        if self._step == 3:
            return (
                self._deck_below_step3.pop(0)
                if self._deck_below_step3
                else None
            )
        if not self._step3_card_drawn:
            if self._deck_above_step3:
                return self._deck_above_step3.pop(0)
            self._shuffle_deck_below()
            self._step3_card_drawn = True
            return None
        return (
            self._deck_below_step3.pop(0) if self._deck_below_step3 else None
        )

    def _rebalance_market(
        self, plants: list[PowerPlant] | None = None
    ) -> None:
        source = plants if plants is not None else (self._row1 + self._row2)
        sorted_plants = sorted(source, key=lambda plant: plant.number.number)
        if self._step == 3:
            self._row1 = sorted_plants
            self._row2 = []
        else:
            self._row1 = sorted_plants[: self.STEP_1_2_ROW_SIZE]
            self._row2 = sorted_plants[self.STEP_1_2_ROW_SIZE :]
        if not self._row1:
            self._is_first_power_plant_discounted = False

    def _shuffle_deck_below(self) -> None:
        expected_ids = Counter(id(plant) for plant in self._deck_below_step3)
        shuffled = list(self._deck_below_step3)
        self._shuffler(shuffled)
        if len(shuffled) != len(self._deck_below_step3) or (
            Counter(id(plant) for plant in shuffled) != expected_ids
        ):
            raise ValueError(
                "Shuffler must permute deck_below_step3 without adding, "
                "removing, duplicating, or replacing cards"
            )
        self._deck_below_step3 = shuffled

    def _find_in_row1(self, number: int) -> tuple[int, PowerPlant] | None:
        for idx, plant in enumerate(self._row1):
            if plant.number.number == number:
                return idx, plant
        return None

    @staticmethod
    def _is_valid_positive_int(value: int) -> bool:
        return (
            not isinstance(value, bool)
            and isinstance(value, int)
            and value >= 1
        )

    @staticmethod
    def _validate_flags(
        step: int,
        step3_card_drawn: bool,
        is_first_power_plant_discounted: bool | None,
    ) -> None:
        if (
            isinstance(step, bool)
            or not isinstance(step, int)
            or step not in (1, 2, 3)
        ):
            raise ValueError("step must be 1, 2, or 3")
        if not isinstance(step3_card_drawn, bool):
            raise ValueError("step3_card_drawn must be a bool")
        if is_first_power_plant_discounted is not None and not isinstance(
            is_first_power_plant_discounted, bool
        ):
            raise ValueError(
                "is_first_power_plant_discounted must be a bool or None"
            )

    @classmethod
    def _validate_plants(
        cls, collections: Sequence[Sequence[PowerPlant]]
    ) -> None:
        seen_numbers: set[int] = set()
        for group in collections:
            for plant in group:
                number = plant.number.number
                if not cls._is_valid_positive_int(number):
                    raise ValueError(f"Invalid power plant number: {number}")
                if number in seen_numbers:
                    raise ValueError(
                        f"Duplicate power plant number: {number}"
                    )
                seen_numbers.add(number)

    @classmethod
    def _validate_structure(
        cls,
        step: int,
        step3_card_drawn: bool,
        row1: list[PowerPlant],
        row2: list[PowerPlant],
        deck_above: list[PowerPlant],
    ) -> None:
        if step == 3:
            if step3_card_drawn:
                raise ValueError(
                    "step3_card_drawn cannot be True when step is 3"
                )
            if row2:
                raise ValueError("row2 must be empty in step 3")
            if deck_above:
                raise ValueError("deck_above_step3 must be empty in step 3")
            if len(row1) > cls.STEP_3_MARKET_SIZE:
                raise ValueError(
                    f"row1 cannot exceed {cls.STEP_3_MARKET_SIZE} plants "
                    "in step 3"
                )
            return

        if step3_card_drawn and deck_above:
            raise ValueError(
                "deck_above_step3 must be empty when step3_card_drawn is True"
            )
        max_row2 = (
            cls.STEP_1_2_ROW_SIZE - 1
            if step3_card_drawn
            else cls.STEP_1_2_ROW_SIZE
        )
        if len(row1) > cls.STEP_1_2_ROW_SIZE:
            raise ValueError(
                f"row1 cannot exceed {cls.STEP_1_2_ROW_SIZE} plants "
                f"in step {step}"
            )
        if len(row2) > max_row2:
            raise ValueError(
                f"row2 cannot exceed {max_row2} plants in step {step}"
            )
        if len(row1) < cls.STEP_1_2_ROW_SIZE and row2:
            raise ValueError(
                "row2 cannot be populated while row1 is not full"
            )
