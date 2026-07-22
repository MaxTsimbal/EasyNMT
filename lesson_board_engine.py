"""Builds step-by-step 'notebook' explanations for Mentory lessons."""
from __future__ import annotations

from typing import Any


def build_lesson_board(subject: str, lesson: dict[str, Any], details: dict[str, Any]) -> dict[str, Any]:
    lesson_id = int(lesson.get("id", 1))
    if subject == "math" and lesson_id == 1:
        return {
            "intro": "Почнемо з самого початку. Квадратне рівняння — це рівняння, у якому є x². Наше завдання — знайти значення x, за яких ліва частина дорівнює нулю.",
            "task": "x² − 5x + 6 = 0",
            "steps": [
                {
                    "title": "Спочатку впізнаємо тип рівняння",
                    "lines": ["Бачимо x², тому це квадратне рівняння.", "Загальний вигляд: ax² + bx + c = 0"],
                    "note": "Зверни увагу: a не може дорівнювати нулю. Інакше x² зникне.",
                },
                {
                    "title": "Виписуємо коефіцієнти",
                    "lines": ["a = 1", "b = −5", "c = 6"],
                    "note": "Число перед x² не написане, але воно є: 1·x². Мінус перед 5 належить до коефіцієнта b.",
                },
                {
                    "title": "Знаходимо дискримінант",
                    "lines": ["D = b² − 4ac", "D = (−5)² − 4 · 1 · 6", "D = 25 − 24", "D = 1"],
                    "note": "Число −5 беремо в дужки. Тоді (−5)² = 25.",
                },
                {
                    "title": "Знаходимо перший корінь",
                    "lines": ["x₁ = (−b − √D) / 2a", "x₁ = (5 − 1) / 2", "x₁ = 4 / 2", "x₁ = 2"],
                    "note": "У формулі стоїть −b. Якщо b = −5, тоді −b = 5.",
                },
                {
                    "title": "Знаходимо другий корінь",
                    "lines": ["x₂ = (−b + √D) / 2a", "x₂ = (5 + 1) / 2", "x₂ = 6 / 2", "x₂ = 3"],
                    "note": "Формули відрізняються лише знаком перед √D: спочатку мінус, потім плюс.",
                },
                {
                    "title": "Перевіряємо відповідь",
                    "lines": ["Для x = 2: 2² − 5·2 + 6 = 4 − 10 + 6 = 0", "Для x = 3: 3² − 5·3 + 6 = 9 − 15 + 6 = 0", "Відповідь: 2; 3"],
                    "note": "Обидва числа перетворили рівняння на правильну рівність, отже корені знайдено правильно.",
                },
            ],
        }

    theory_points = list(details.get("theory_points") or [])
    formulas = list(details.get("formulas") or [])
    examples = list(details.get("extra_examples") or [])
    summary = list(details.get("summary_points") or [])
    steps = []
    source = summary or theory_points or [lesson.get("theory", "Розберемо головну ідею теми.")]
    for index, line in enumerate(source[:6], start=1):
        extra = examples[index - 1] if index - 1 < len(examples) else ""
        steps.append({
            "title": f"Крок {index}",
            "lines": [line] + ([extra] if extra and extra != line else []),
            "note": formulas[index - 1] if index - 1 < len(formulas) else "Не поспішай. Переконайся, що розумієш, навіщо потрібна ця дія.",
        })
    return {
        "intro": details.get("simple_explanation") or lesson.get("theory", "Почнемо з основи й поступово дійдемо до повного розв’язання."),
        "task": lesson.get("example", "Розберемо приклад разом."),
        "steps": steps,
    }
