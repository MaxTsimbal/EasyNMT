from pathlib import Path
import unittest

from easynmt_core.lessons import CurriculumLessonRenderer
from easynmt_core.progress import (
    CurriculumProgressSnapshot,
    CurriculumUnitProgressView,
    CurriculumUnitState,
    MasteryBand,
)


class DashboardPersonalizationTests(unittest.TestCase):
    @staticmethod
    def snapshot(*, current_order: int = 2, completed_all: bool = False):
        units = []
        total = 12
        for order in range(1, total + 1):
            if completed_all:
                state = CurriculumUnitState.COMPLETED
                mastery = 0.9
                band = MasteryBand.MASTERED
            elif order < current_order:
                state = CurriculumUnitState.COMPLETED
                mastery = 0.85
                band = MasteryBand.PROFICIENT
            elif order == current_order:
                state = CurriculumUnitState.AVAILABLE
                mastery = None
                band = MasteryBand.UNKNOWN
            else:
                state = CurriculumUnitState.LOCKED
                mastery = None
                band = MasteryBand.UNKNOWN
            units.append(
                CurriculumUnitProgressView(
                    unit_id=f"unit-{order:03d}",
                    topic_id=f"english.topic.{order}",
                    title=f"Topic {order}",
                    order=order,
                    state=state,
                    mastery_score=mastery,
                    mastery_band=band,
                    prerequisite_topic_ids=(),
                    checkpoint_status="none",
                    completion_timestamp=None,
                    next_allowed_action=None,
                    version=1,
                )
            )
        completed = total if completed_all else max(0, current_order - 1)
        return CurriculumProgressSnapshot(
            curriculum_id="curriculum-dashboard",
            curriculum_version=1,
            subject="english",
            curriculum_status="published",
            historical=False,
            total_units=total,
            completed_units=completed,
            available_units=0 if completed_all else 1,
            in_progress_units=0,
            locked_units=0 if completed_all else total - current_order,
            review_required_units=0,
            completion_percent=(completed / total) * 100,
            current_unit_ids=() if completed_all else (f"unit-{current_order:03d}",),
            units=tuple(units),
            checkpoints=(),
        )

    def test_dashboard_route_shows_only_three_nearest_units(self):
        context = CurriculumLessonRenderer.navigation_context(
            self.snapshot(current_order=2)
        )
        self.assertEqual(
            [unit["order"] for unit in context["nearby_units"]],
            [1, 2, 3],
        )
        self.assertEqual(context["other_units_count"], 9)
        self.assertEqual(context["current_unit"]["order"], 2)

    def test_route_window_moves_with_the_learner(self):
        context = CurriculumLessonRenderer.navigation_context(
            self.snapshot(current_order=7)
        )
        self.assertEqual(
            [unit["order"] for unit in context["nearby_units"]],
            [6, 7, 8],
        )

    def test_completed_route_shows_last_three_topics(self):
        context = CurriculumLessonRenderer.navigation_context(
            self.snapshot(completed_all=True)
        )
        self.assertEqual(context["current_unit"]["order"], 12)
        self.assertEqual(
            [unit["order"] for unit in context["nearby_units"]],
            [10, 11, 12],
        )

    def test_dashboard_template_uses_nearby_units_and_review_link(self):
        template = (
            Path(__file__).resolve().parents[1] / "templates" / "dashboard.html"
        ).read_text(encoding="utf-8")
        self.assertIn("curriculum_navigation.nearby_units", template)
        self.assertIn("Інші уроки", template)
        self.assertIn("personal_focus_attempt_id", template)
        self.assertIn("Відкрити останній розбір", template)


if __name__ == "__main__":
    unittest.main()
