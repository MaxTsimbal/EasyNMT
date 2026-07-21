"""Deterministic intelligence planning for the Easy tutor.

This module improves answer quality without extra paid model calls. It derives a
small learner-memory snapshot, chooses a provider-neutral execution profile, and
normalizes stylistic filler from the final answer. Flask and SQLite remain the
authority for progress, XP, permissions, and assessment state.
"""
from __future__ import annotations

import re
from typing import Mapping, Sequence

from .schemas import LearnerMemory, LearningContext, TutorExecutionPlan
from .tutor_brain import analyze_tutor_request


_COMPLEXITY_MARKERS = (
    "доведи",
    "обґрунтуй",
    "проаналізуй",
    "порівняй",
    "чому саме",
    "покроково",
    "розв'яж",
    "розв’яж",
    "рівнян",
    "нерівн",
    "система",
    "функц",
    "ймовірн",
    "геометр",
    "граматич",
    "виправ помилки",
    "перевір розв'язання",
    "перевір розв’язання",
)
_SIMPLE_STYLE_MARKERS = (
    "простіш",
    "з нуля",
    "не розум",
    "не зрозум",
    "по кроках",
    "малими кроками",
)
_CONCISE_STYLE_MARKERS = ("коротко", "стисло", "тільки головне", "без води")
_GUIDED_STYLE_MARKERS = ("підказ", "натяк", "не кажи відповідь", "веди мене")
_DETAILED_STYLE_MARKERS = ("детально", "повністю", "розгорнуто", "кожен крок")
_RETRY_MARKERS = ("ще раз", "інакше", "все одно", "не допомогло", "досі не")
_STEP_MARKERS = ("по кроках", "покроково", "кожен крок", "не пропускай")

_GENERIC_OPENING_PATTERNS = (
    r"^\s*(?:звичайно|звісно|безумовно|авжеж)[!,.\s:–—-]*",
    r"^\s*(?:із|з)\s+задоволенням[!,.\s:–—-]*",
    r"^\s*(?:давай|давайте)\s+(?:розберемо|розглянемо|подивимося)[!,.\s:–—-]*",
    r"^\s*(?:ось|отже),?\s+(?:відповідь|пояснення)[!,.\s:–—-]*",
)
_GENERIC_CLOSINGS = (
    r"\s*(?:якщо маєш|якщо будуть|якщо є)\s+(?:ще\s+)?питанн(?:я|я,).*?$",
    r"\s*(?:звертайся|пиши),?\s+(?:якщо|коли).*?$",
    r"\s*чи є в тебе ще питання\??\s*$",
)


def _normalized_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _history_text(history: Sequence[Mapping[str, str]], *, roles: set[str] | None = None) -> str:
    parts: list[str] = []
    for item in list(history or [])[-12:]:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role", "")).strip().lower()
        if roles is not None and role not in roles:
            continue
        text = _normalized_text(item.get("text", ""))
        if text:
            parts.append(text)
    return " ".join(parts)


def _contains_any(text: str, markers: Sequence[str]) -> bool:
    return any(marker in text for marker in markers)


def infer_preferred_style(
    question: str,
    history: Sequence[Mapping[str, str]],
    *,
    response_mode: str,
    persisted_style: str = "adaptive",
) -> str:
    """Infer the learner's teaching preference from explicit recent signals."""

    current = _normalized_text(question)
    recent_user = _history_text(history, roles={"user"})
    combined = f"{recent_user} {current}".strip()

    if response_mode == "concise" or _contains_any(current, _CONCISE_STYLE_MARKERS):
        return "concise"
    if response_mode == "practice" or _contains_any(current, _GUIDED_STYLE_MARKERS):
        return "guided"
    if _contains_any(current, _SIMPLE_STYLE_MARKERS):
        return "simple"
    if _contains_any(current, _DETAILED_STYLE_MARKERS):
        return "detailed"

    persisted = str(persisted_style or "adaptive").strip().lower()
    if persisted in {"concise", "simple", "guided", "detailed"}:
        return persisted
    if _contains_any(combined, _SIMPLE_STYLE_MARKERS):
        return "simple"
    return "adaptive"


def build_learner_memory(
    context: LearningContext,
    history: Sequence[Mapping[str, str]],
    *,
    question: str,
    persisted: Mapping[str, object] | None = None,
) -> LearnerMemory:
    """Build a bounded memory snapshot from authoritative data and recent signals."""

    persisted = persisted or {}
    preferred_style = infer_preferred_style(
        question,
        history,
        response_mode=context.response_mode,
        persisted_style=str(persisted.get("preferred_style", "adaptive")),
    )
    combined = f"{_history_text(history, roles={'user'})} {_normalized_text(question)}"
    failure_count = max(0, int(persisted.get("explanation_failures", 0) or 0))
    if _contains_any(_normalized_text(question), _RETRY_MARKERS):
        failure_count += 1

    focus_topics = list(context.known_weaknesses)
    persisted_focus = str(persisted.get("last_focus", "") or "").strip()
    if persisted_focus and persisted_focus not in focus_topics:
        focus_topics.append(persisted_focus)

    recent_patterns = list(context.recent_mistakes[:5])
    needs_steps = bool(persisted.get("needs_step_by_step", False)) or _contains_any(
        combined,
        _STEP_MARKERS + _SIMPLE_STYLE_MARKERS,
    )

    continuity = ""
    if context.lesson_context and context.lesson_title:
        continuity = f"Продовжує роботу в уроці «{context.lesson_title}»."
    elif context.weak_topic:
        continuity = f"Поточний фокус: «{context.weak_topic}»."
    elif context.current_lesson:
        continuity = f"Поточний урок: {context.current_lesson}."

    return LearnerMemory(
        preferred_style=preferred_style,
        needs_step_by_step=needs_steps,
        explanation_failures=failure_count,
        focus_topics=tuple(focus_topics),
        recent_error_patterns=tuple(recent_patterns),
        continuity_note=continuity,
    )


def build_execution_plan(
    *,
    question: str,
    history: Sequence[Mapping[str, str]],
    context: LearningContext,
    has_images: bool,
) -> TutorExecutionPlan:
    """Choose a cost-aware execution profile for one tutor turn."""

    clean = _normalized_text(question)
    word_count = len(clean.split())
    strategy = analyze_tutor_request(
        question,
        history,
        response_mode=context.response_mode,
        has_images=has_images,
    )

    score = 0
    score += min(3, word_count // 45)
    marker_hits = sum(1 for marker in _COMPLEXITY_MARKERS if marker in clean)
    score += min(4, marker_hits)
    score += 1 if any(char in clean for char in "=√^∑∫<>±") else 0
    score += 1 if clean.count("?") > 1 or clean.count(";") > 1 else 0
    score += 1 if strategy.retry_explanation else 0
    score += 2 if has_images else 0
    score = max(0, min(10, score))

    if has_images:
        profile = "vision"
        effort = "medium" if score >= 4 else "low"
        verbosity = "medium"
        tokens = 1400
    elif context.response_mode == "concise" and score <= 3:
        profile = "fast"
        effort = "minimal"
        verbosity = "low"
        tokens = 480
    elif score >= 5 or strategy.intent.startswith("розв’язати") or "перевірити роботу" in strategy.intent:
        profile = "deep"
        effort = "medium" if score < 8 else "high"
        verbosity = "high" if context.response_mode == "explain" else "medium"
        tokens = 1700
    elif score <= 1 and context.response_mode != "practice":
        profile = "fast"
        effort = "minimal"
        verbosity = "low" if word_count <= 20 else "medium"
        tokens = 650
    else:
        profile = "balanced"
        effort = "low"
        verbosity = "medium"
        tokens = 1000

    available = int(context.available_tokens or tokens)
    tokens = min(tokens, max(96, available))
    return TutorExecutionPlan(
        profile=profile,
        reasoning_effort=effort,
        verbosity=verbosity,
        max_output_tokens=tokens,
        complexity_score=score,
        intent=strategy.intent,
    )


def learner_memory_prompt(memory: LearnerMemory) -> str:
    """Render memory as concise pedagogical instructions, not as user-facing text."""

    style_labels = {
        "adaptive": "підлаштуйся під складність запиту",
        "concise": "відповідай стисло й без другорядних відступів",
        "simple": "почни з простого сенсу, використовуй малі кроки",
        "guided": "веди підказками й не забирай роботу в учня",
        "detailed": "пояснюй кожен важливий перехід і перевіряй логіку",
    }
    lines = [
        "Навчальна пам’ять Easy:",
        f"- бажаний стиль: {style_labels[memory.preferred_style]}",
    ]
    if memory.needs_step_by_step:
        lines.append("- учневі корисно бачити рішення малими послідовними кроками")
    if memory.explanation_failures:
        lines.append(
            "- попередні пояснення інколи не спрацьовували: зміни підхід, приклад і формулювання"
        )
    if memory.focus_topics:
        lines.append(f"- теми для особливої уваги: {', '.join(memory.focus_topics)}")
    if memory.recent_error_patterns:
        lines.append("- врахуй недавні помилки, але не переказуй їх дослівно без потреби")
    if memory.continuity_note:
        lines.append(f"- безперервність: {memory.continuity_note}")
    return "\n".join(lines)


def execution_plan_prompt(plan: TutorExecutionPlan) -> str:
    depth = {
        "fast": "коротка пряма відповідь",
        "balanced": "достатнє пояснення з одним сильним прикладом",
        "deep": "уважний покроковий розбір із самоперевіркою",
        "vision": "спочатку чесно прочитай видиме, потім перевір кроки",
    }[plan.profile]
    return (
        "План цієї відповіді Easy:\n"
        f"- навчальна мета: {plan.intent}\n"
        f"- формат: {depth}\n"
        "- не показуй внутрішнє міркування; показуй лише зрозумілі навчальні кроки"
    )


def strip_generic_opening(text: str) -> str:
    value = str(text or "").strip()
    for pattern in _GENERIC_OPENING_PATTERNS:
        value = re.sub(pattern, "", value, count=1, flags=re.IGNORECASE)
    return value.lstrip(" ,.:;\n")


def polish_tutor_answer(text: object, *, response_mode: str = "explain") -> str:
    """Remove canned filler while preserving mathematical and educational content."""

    value = str(text or "").replace("\r\n", "\n").strip()
    value = strip_generic_opening(value)
    for pattern in _GENERIC_CLOSINGS:
        value = re.sub(pattern, "", value, count=1, flags=re.IGNORECASE | re.DOTALL).rstrip()
    value = re.sub(r"\n{3,}", "\n\n", value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    if response_mode == "concise":
        value = re.sub(r"\n\s*(?:Підсумок|Висновок):?\s*", "\n", value, flags=re.IGNORECASE)
    return value.strip()
