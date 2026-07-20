from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ContextualEasyUiContractTests(unittest.TestCase):
    def test_contextual_form_never_triggers_global_page_loader(self):
        component = (ROOT / "templates/components/contextual_easy.html").read_text(encoding="utf-8")
        transitions = (ROOT / "static/js/page_transitions.js").read_text(encoding="utf-8")
        self.assertIn('id="contextualEasyComposer" data-no-transition', component)
        self.assertIn('form.closest(".contextual-easy-panel")', transitions)

    def test_v3_markdown_typing_and_smooth_scroll_are_connected(self):
        component = (ROOT / "templates/components/contextual_easy.html").read_text(encoding="utf-8")
        script = (ROOT / "static/js/contextual_easy.js").read_text(encoding="utf-8")
        self.assertLess(
            component.index("js/easy_chat_v3/markdown.js"),
            component.index("js/contextual_easy.js"),
        )
        self.assertIn("const typeAnswer = async", script)
        self.assertIn('behavior: reduceMotion ? "auto" : behavior', script)
        self.assertIn("markdown.render", script)

    def test_ui_exposes_truthful_online_or_offline_mode(self):
        component = (ROOT / "templates/components/contextual_easy.html").read_text(encoding="utf-8")
        script = (ROOT / "static/js/contextual_easy.js").read_text(encoding="utf-8")
        self.assertIn('id="contextualEasyMode"', component)
        self.assertIn('openai: ["Онлайн AI"', script)
        self.assertIn('offline: ["Офлайн підказка"', script)


if __name__ == "__main__":
    unittest.main()
