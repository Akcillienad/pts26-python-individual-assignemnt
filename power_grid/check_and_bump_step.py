from collections.abc import Sequence

from power_grid.interfaces import StepTransitionHandler


class CheckAndBumpStep:

    def __init__(
        self,
        number_of_players: int,
        step_transition_handlers: Sequence[StepTransitionHandler] = (),
    ) -> None:
        if number_of_players < 2 or number_of_players > 6:
            raise ValueError("Power Grid supports 2 to 6 players")

        self._number_of_players = number_of_players
        self._step = 1
        self._step_transition_handlers = list(step_transition_handlers)

    def get_step(self) -> int:
        return self._step

    def check_and_bump_to_step2(
        self, connected_city_counts: Sequence[int]
    ) -> bool:
        if any(city_count < 0 for city_count in connected_city_counts):
            raise ValueError("connected city counts cannot be negative")
        if self._step != 1:
            return False

        threshold = 6 if self._number_of_players == 6 else 7
        if not any(city_count >= threshold for city_count in connected_city_counts):
            return False

        self._start_step2()
        return True

    def check_and_bump_to_step3(self, step_3_card_drawn: bool) -> bool:
        if not step_3_card_drawn or self._step == 3:
            return False

        self._start_step3()
        return True

    def _start_step2(self) -> None:
        assert self._step == 1
        for handler in self._step_transition_handlers:
            handler.start_step2()
        self._step = 2

    def _start_step3(self) -> None:
        assert self._step < 3
        if self._step == 1:
            self._start_step2()
        for handler in self._step_transition_handlers:
            handler.start_step3()
        self._step = 3
