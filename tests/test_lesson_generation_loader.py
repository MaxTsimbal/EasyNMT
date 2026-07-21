from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class LessonGenerationLoaderContractTests(unittest.TestCase):
    def test_base_exposes_a_dedicated_accessible_lesson_loader(self):
        base = (ROOT / "templates/base.html").read_text(encoding="utf-8")

        self.assertIn('id="lessonGenerationStatus" hidden', base)
        self.assertIn('id="lessonGenerationTopic"', base)
        self.assertIn('data-loader-step="0"', base)
        self.assertIn('data-loader-step="1"', base)
        self.assertIn('data-loader-step="2"', base)
        self.assertIn("Зазвичай це займає 20–30 секунд", base)
        self.assertIn("task3d2-lesson-loader", base)

    def test_navigation_detects_both_direct_and_start_lesson_routes(self):
        script = (ROOT / "static/js/page_transitions.js").read_text(encoding="utf-8")

        self.assertIn("lessonRoutePattern", script)
        self.assertIn("(?:start|lesson)", script)
        self.assertIn("input[name='curriculum_unit_id']", script)
        self.assertIn("prepareLessonLoader", script)
        self.assertIn("Створюємо твій урок", script)
        self.assertIn("не натискай кнопку повторно", script)

    def test_progress_is_explicitly_estimated_and_never_claims_exact_completion(self):
        script = (ROOT / "static/js/page_transitions.js").read_text(encoding="utf-8")

        self.assertIn("estimated visual indicator", script)
        self.assertIn("Math.min(92", script)
        self.assertNotIn("100% готово", script)

    def test_loader_styles_include_mobile_and_reduced_motion_states(self):
        styles = (ROOT / "static/css/style.css").read_text(encoding="utf-8")

        self.assertIn(".page-loader.lesson-generation-mode", styles)
        self.assertIn(".lesson-generation-steps li.is-active", styles)
        self.assertIn("@media (max-width: 600px)", styles)
        self.assertIn("@media (prefers-reduced-motion: reduce)", styles)


if __name__ == "__main__":
    unittest.main()
