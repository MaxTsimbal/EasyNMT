"""Deterministic Task 3C.1 quiz builder grounded only in delivered lesson content."""
from __future__ import annotations

import hashlib
import re
from typing import Iterable

from easynmt_ai.lessons import Lesson

from .models import ProductionQuiz, QuizQuestion


STOPWORDS = frozenset({
    "і", "й", "та", "у", "в", "на", "до", "з", "із", "за", "для", "що", "як", "це",
    "the", "a", "an", "to", "of", "in", "on", "and", "or", "is", "are", "be", "with",
})


def _tokens(text: str, *, limit: int = 8) -> tuple[str, ...]:
    words = re.findall(r"[\w’'-]+", str(text).lower(), flags=re.UNICODE)
    result: list[str] = []
    for word in words:
        if len(word) < 3 or word in STOPWORDS or word.isdigit() or word in result:
            continue
        result.append(word)
        if len(result) >= limit:
            break
    return tuple(result)


def _unique_options(correct: str, candidates: Iterable[str]) -> tuple[str, ...]:
    values = [correct.strip()]
    for candidate in candidates:
        candidate = str(candidate or "").strip()
        if candidate and candidate not in values:
            values.append(candidate)
        if len(values) == 4:
            break
    fallbacks = (
        "Застосувати правило без перевірки умови",
        "Ігнорувати ключову ознаку завдання",
        "Вибрати відповідь лише за зовнішнім виглядом",
        "Пропустити пояснення й одразу вгадувати",
    )
    for candidate in fallbacks:
        if candidate not in values:
            values.append(candidate)
        if len(values) == 4:
            break
    return tuple(values[:4])


def _question_id(lesson: Lesson, index: int) -> str:
    return f"{lesson.curriculum_unit_id}-q{index:02d}"


def build_deterministic_quiz(lesson: Lesson) -> ProductionQuiz:
    """Build an immutable 12-question, 24-point assessment from one lesson."""

    concepts = list(lesson.concepts)
    examples = list(lesson.worked_examples)
    mistakes = list(lesson.common_mistakes)
    tips = list(lesson.practical_tips)
    concepts_cycle = concepts or []
    if not concepts_cycle or not examples or not mistakes:
        raise ValueError("lesson does not contain enough structured content for a production quiz")

    c1 = concepts_cycle[0]
    c2 = concepts_cycle[1 % len(concepts_cycle)]
    m1 = mistakes[0]
    m2 = mistakes[1 % len(mistakes)]
    e1 = examples[0]
    e2 = examples[1 % len(examples)]
    tip1 = tips[0] if tips else None
    recap_ideas = list(lesson.recap.main_ideas)
    formulas = list(lesson.recap.formulas)
    can_solve = list(lesson.recap.can_solve)
    patterns = list(lesson.assessment_blueprint.question_patterns)
    reasoning = list(lesson.assessment_blueprint.required_reasoning)

    questions: list[QuizQuestion] = []

    questions.append(QuizQuestion(
        id=_question_id(lesson, 1),
        prompt=f"Яке твердження найточніше пояснює поняття «{c1.title}»?",
        answer_type="choice",
        options=_unique_options(c1.what, [c1.common_confusion, c2.what, m1.incorrect_reasoning]),
        correct_answer=c1.what,
        accepted_answers=(c1.what,),
        keywords=_tokens(c1.what),
        explanation=f"Правильне пояснення: {c1.what}",
        points=1,
    ))
    questions.append(QuizQuestion(
        id=_question_id(lesson, 2),
        prompt=f"Який крок правильно застосовує правило «{c2.title}»?",
        answer_type="choice",
        options=_unique_options(c2.how, [c2.common_confusion, m2.incorrect_reasoning, c1.common_confusion]),
        correct_answer=c2.how,
        accepted_answers=(c2.how,),
        keywords=_tokens(c2.how),
        explanation=f"Алгоритм із уроку: {c2.how}",
        points=1,
    ))
    correct_prevention = tip1.advice if tip1 else m1.prevention
    questions.append(QuizQuestion(
        id=_question_id(lesson, 3),
        prompt="Що найкраще допомагає уникнути типової помилки з цього уроку?",
        answer_type="choice",
        options=_unique_options(correct_prevention, [m1.incorrect_reasoning, m2.incorrect_reasoning, c1.common_confusion]),
        correct_answer=correct_prevention,
        accepted_answers=(correct_prevention,),
        keywords=_tokens(correct_prevention),
        explanation=f"Надійна звичка: {correct_prevention}",
        points=1,
    ))
    nmt_correct = lesson.nmt_task_types[0] if lesson.nmt_task_types else lesson.nmt_relevance
    questions.append(QuizQuestion(
        id=_question_id(lesson, 4),
        prompt="Який формат завдання найбільше відповідає матеріалу цього уроку?",
        answer_type="choice",
        options=_unique_options(nmt_correct, [m1.incorrect_reasoning, c1.common_confusion, "Завдання з теми, якої в уроці не було"]),
        correct_answer=nmt_correct,
        accepted_answers=(nmt_correct,),
        keywords=_tokens(nmt_correct),
        explanation=f"Урок готує до такого формату: {nmt_correct}",
        points=1,
    ))

    short_specs = [
        (
            f"Коротко поясни своїми словами, що означає «{c1.title}».",
            c1.what,
            tuple(dict.fromkeys((*_tokens(c1.what), *_tokens(c1.why))))[:8],
            f"У відповіді має бути зміст поняття: {c1.what}",
        ),
        (
            f"Запиши правильний спосіб застосування правила «{c2.title}».",
            c2.how,
            tuple(dict.fromkeys((*_tokens(c2.how), *_tokens(c2.when_used))))[:8],
            f"Орієнтир: {c2.how}",
        ),
        (
            "Назви одну типову помилку з уроку та коротко напиши, як її виправити.",
            f"{m1.incorrect_reasoning} Виправлення: {m1.correction}",
            tuple(dict.fromkeys((*_tokens(m1.incorrect_reasoning), *_tokens(m1.correction))))[:8],
            f"Типова помилка: {m1.incorrect_reasoning} Правильне виправлення: {m1.correction}",
        ),
        (
            "Сформулюй одну головну ідею або формулу, яку потрібно запам’ятати після уроку.",
            formulas[0] if formulas else recap_ideas[0],
            _tokens((formulas[0] if formulas else recap_ideas[0]), limit=8),
            f"Один із правильних орієнтирів: {formulas[0] if formulas else recap_ideas[0]}",
        ),
    ]
    for offset, (prompt, answer, keywords, explanation) in enumerate(short_specs, start=5):
        questions.append(QuizQuestion(
            id=_question_id(lesson, offset),
            prompt=prompt,
            answer_type="short_text",
            options=(),
            correct_answer=answer,
            accepted_answers=(answer,),
            keywords=keywords,
            explanation=explanation,
            points=2,
        ))

    long_specs = [
        (
            f"Розв’яжи або відтвори повний хід для завдання: {e1.problem}",
            f"{e1.reasoning} {' '.join(step.work for step in e1.steps)} Відповідь: {e1.final_answer}",
            tuple(dict.fromkeys((*_tokens(e1.reasoning), *(_tokens(' '.join(step.work for step in e1.steps))), *_tokens(e1.final_answer))))[:12],
            f"Еталонний хід: {e1.reasoning} {' '.join(step.work for step in e1.steps)} Відповідь: {e1.final_answer}",
        ),
        (
            f"Покажи основні кроки для завдання: {e2.problem}",
            f"{e2.reasoning} {' '.join(step.work for step in e2.steps)} Відповідь: {e2.final_answer}",
            tuple(dict.fromkeys((*_tokens(e2.reasoning), *(_tokens(' '.join(step.work for step in e2.steps))), *_tokens(e2.final_answer))))[:12],
            f"Еталонний хід: {e2.reasoning} {' '.join(step.work for step in e2.steps)} Відповідь: {e2.final_answer}",
        ),
        (
            patterns[0] if patterns else f"Склади покрокове пояснення застосування правила «{c1.title}».",
            reasoning[0] if reasoning else f"Потрібно пояснити правило, застосувати його та перевірити результат: {c1.how}",
            tuple(dict.fromkeys((*_tokens(reasoning[0] if reasoning else c1.how), *_tokens(c1.title))))[:12],
            f"Очікуваний тип міркування: {reasoning[0] if reasoning else c1.how}",
        ),
        (
            can_solve[0] if can_solve else "Поясни, як перевірити відповідь і знайти можливу помилку.",
            f"{lesson.recap.main_ideas[0]} Перевірка: {e1.verification}",
            tuple(dict.fromkeys((*_tokens(lesson.recap.main_ideas[0]), *_tokens(e1.verification))))[:12],
            f"У відповіді мають бути правило та перевірка: {lesson.recap.main_ideas[0]} {e1.verification}",
        ),
    ]
    for offset, (prompt, answer, keywords, explanation) in enumerate(long_specs, start=9):
        questions.append(QuizQuestion(
            id=_question_id(lesson, offset),
            prompt=prompt,
            answer_type="long_text",
            options=(),
            correct_answer=answer,
            accepted_answers=(answer,),
            keywords=keywords,
            explanation=explanation,
            points=3,
        ))

    fingerprint = hashlib.sha256(
        f"quiz.v1|{lesson.id}|{lesson.generation_metadata.request_fingerprint}".encode("utf-8")
    ).hexdigest()[:28]
    return ProductionQuiz(
        id=f"quiz-{fingerprint}",
        curriculum_id=lesson.curriculum_id,
        curriculum_unit_id=lesson.curriculum_unit_id,
        topic_id=lesson.topic_id,
        lesson_id=lesson.id,
        subject=lesson.subject,
        title=f"Перевірка: {lesson.title}",
        questions=tuple(questions),
    )
