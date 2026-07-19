from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class TutorStrategy:
    intent: str
    confidence: str
    learner_state: str
    explanation_style: str
    answer_depth: str
    should_ask_question: bool = False
    avoid_full_solution: bool = False
    retry_explanation: bool = False

    def as_prompt(self) -> str:
        lines = [
            "Внутрішня стратегія відповіді Easy:",
            f"- намір запиту: {self.intent}",
            f"- стан учня: {self.learner_state}",
            f"- спосіб пояснення: {self.explanation_style}",
            f"- глибина відповіді: {self.answer_depth}",
        ]
        if self.retry_explanation:
            lines.append("- учень уже не зрозумів попереднє пояснення: НЕ повторюй його; зміни підхід, приклад і формулювання")
        if self.should_ask_question:
            lines.append("- якщо без уточнення є ризик відповісти не на те, постав одне коротке конкретне питання")
        if self.avoid_full_solution:
            lines.append("- не видавай повний розв’язок одразу; дай наступний посильний крок або підказку")
        return "\n".join(lines)


_CONFUSION = (
    "не розум", "не зрозум", "нічого не розум", "взагалі не", "заплутав", "важко",
    "незрозуміло", "що це взагалі", "поясни простіше", "з нуля",
)
_RETRY = (
    "все одно", "ще раз", "інакше", "не допомогло", "досі не", "так і не",
)
_CHECK = (
    "перевір", "правильно", "чи вірно", "де помилка", "оцін", "бал", "моя відповідь",
)
_SOLVE = (
    "розв'яж", "розв’яж", "виріши", "обчисли", "знайди", "дай відповідь", "розв’язок",
)
_EXPLAIN = (
    "поясни", "розкажи", "що таке", "як працює", "чому", "покажи як",
)
_PRACTICE = (
    "дай завдання", "потрен", "практик", "тест", "питання", "перевір мене",
)
_SUMMARY = (
    "коротко", "стисло", "підсум", "шпаргал", "головне", "формули",
)


def _contains(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def _recent_user_text(history: Sequence[dict[str, str]]) -> str:
    parts: list[str] = []
    for item in list(history or [])[-6:]:
        if not isinstance(item, dict) or str(item.get("role", "")).lower() != "user":
            continue
        value = str(item.get("text", "")).strip().lower()
        if value:
            parts.append(value)
    return " ".join(parts)


def analyze_tutor_request(
    question: str,
    history: Sequence[dict[str, str]],
    *,
    response_mode: str = "explain",
    has_images: bool = False,
) -> TutorStrategy:
    """Fast local intent analysis. It costs no API tokens and never blocks the chat."""
    text = re.sub(r"\s+", " ", str(question or "").strip().lower())
    recent = _recent_user_text(history)

    confused = _contains(text, _CONFUSION)
    retry = _contains(text, _RETRY) or (confused and _contains(recent, _CONFUSION))

    if has_images or _contains(text, _CHECK):
        intent = "перевірити роботу та знайти точне місце помилки"
        style = "спочатку прочитати умову й кроки, потім відділити правильне від помилки"
        depth = "детальна перевірка без зайвої теорії"
        learner_state = "очікує чесного й конкретного зворотного зв’язку"
    elif _contains(text, _PRACTICE) or response_mode == "practice":
        intent = "потренувати навичку"
        style = "сократівський діалог: одне завдання або один наступний крок"
        depth = "поетапно, без передчасного розкриття відповіді"
        learner_state = "готовий працювати самостійно з підказками"
    elif _contains(text, _SUMMARY) or response_mode == "concise":
        intent = "отримати короткий орієнтир або повторення"
        style = "стисла структура з головною думкою та мінімумом прикладів"
        depth = "коротко"
        learner_state = "хоче швидко освіжити матеріал"
    elif _contains(text, _SOLVE):
        intent = "розв’язати конкретне завдання й зрозуміти хід"
        style = "покрокове розв’язання з коротким поясненням причин кожної дії"
        depth = "достатньо для самостійного повторення"
        learner_state = "потребує практичного розбору"
    elif _contains(text, _EXPLAIN) or confused:
        intent = "зрозуміти тему або правило"
        style = "пояснення від простого сенсу до формули, потім один наочний приклад"
        depth = "повно, але без енциклопедичної води"
        learner_state = "розгублений" if confused else "зацікавлений"
    else:
        intent = "відповісти на навчальний запит у його реальному контексті"
        style = "пряма природна відповідь з доречним поясненням"
        depth = "пропорційно складності запиту"
        learner_state = "нейтральний"

    if retry:
        style = "новий підхід: інша аналогія, простіші числа або візуальна логіка замість повторення"
        depth = "малими кроками з короткою перевіркою розуміння наприкінці"
        learner_state = "попереднє пояснення не спрацювало"

    ambiguous = len(text.split()) <= 2 and not has_images and not _contains(text, _CHECK + _SOLVE + _EXPLAIN + _PRACTICE)

    return TutorStrategy(
        intent=intent,
        confidence="середня" if ambiguous else "висока",
        learner_state=learner_state,
        explanation_style=style,
        answer_depth=depth,
        should_ask_question=ambiguous,
        avoid_full_solution=(response_mode == "practice" or _contains(text, ("підказ", "натяк"))),
        retry_explanation=retry,
    )
