import unittest

from power_grid.check_and_bump_step import CheckAndBumpStep


class StepTransitionRecorder:
    def __init__(self) -> None:
        self.transitions: list[str] = []

    def start_step2(self) -> None:
        self.transitions.append("step2")

    def start_step3(self) -> None:
        self.transitions.append("step3")


class TestCheckAndBumpStep(unittest.TestCase):
    def test_step_starts_at_one(self) -> None:
        step = CheckAndBumpStep(4)

        self.assertEqual(step.get_step(), 1)

    def test_step2_threshold_is_seven_for_two_to_five_players(self) -> None:
        for number_of_players in (2, 3, 4, 5):
            with self.subTest(number_of_players=number_of_players):
                step = CheckAndBumpStep(number_of_players)

                self.assertFalse(step.check_and_bump_to_step2([6]))
                self.assertEqual(step.get_step(), 1)
                self.assertTrue(step.check_and_bump_to_step2([7]))
                self.assertEqual(step.get_step(), 2)

    def test_step2_threshold_is_six_for_six_players(self) -> None:
        step = CheckAndBumpStep(6)

        self.assertFalse(step.check_and_bump_to_step2([5]))
        self.assertTrue(step.check_and_bump_to_step2([6]))
        self.assertEqual(step.get_step(), 2)

    def test_step2_starts_when_any_player_reaches_threshold(self) -> None:
        step = CheckAndBumpStep(4)

        self.assertFalse(step.check_and_bump_to_step2([3, 6, 2]))
        self.assertTrue(step.check_and_bump_to_step2([3, 7, 2]))

    def test_step3_can_start_before_step2_and_runs_both_transitions(self) -> None:
        recorder = StepTransitionRecorder()
        step = CheckAndBumpStep(4, [recorder])

        changed = step.check_and_bump_to_step3(True)

        self.assertTrue(changed)
        self.assertEqual(step.get_step(), 3)
        self.assertEqual(recorder.transitions, ["step2", "step3"])

    def test_step3_after_step2_only_runs_step3_transition(self) -> None:
        recorder = StepTransitionRecorder()
        step = CheckAndBumpStep(4, [recorder])
        step.check_and_bump_to_step2([7])

        changed = step.check_and_bump_to_step3(True)

        self.assertTrue(changed)
        self.assertEqual(step.get_step(), 3)
        self.assertEqual(recorder.transitions, ["step2", "step3"])

    def test_step3_card_not_drawn_does_not_change_step(self) -> None:
        step = CheckAndBumpStep(4)

        self.assertFalse(step.check_and_bump_to_step3(False))
        self.assertEqual(step.get_step(), 1)

    def test_step_transitions_only_happen_once(self) -> None:
        step = CheckAndBumpStep(4)
        self.assertTrue(step.check_and_bump_to_step2([7]))
        self.assertFalse(step.check_and_bump_to_step2([8]))
        self.assertTrue(step.check_and_bump_to_step3(True))
        self.assertFalse(step.check_and_bump_to_step3(True))
        self.assertEqual(step.get_step(), 3)

    def test_invalid_player_count_is_rejected(self) -> None:
        for number_of_players in (1, 7):
            with self.subTest(number_of_players=number_of_players):
                with self.assertRaises(ValueError):
                    CheckAndBumpStep(number_of_players)

    def test_negative_connected_city_count_is_rejected(self) -> None:
        step = CheckAndBumpStep(4)

        with self.assertRaises(ValueError):
            step.check_and_bump_to_step2([-1])
