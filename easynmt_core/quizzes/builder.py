"""Human-friendly deterministic quiz builder grounded in delivered lesson content."""
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


def _tokens(text: str, *, limit: int = 10) -> tuple[str, ...]:
    words = re.findall(r"[\w’'+=°%./-]+", str(text).lower(), flags=re.UNICODE)
    result: list[str] = []
    for word in words:
        if len(word) < 3 or word in STOPWORDS or word.isdigit() or word in result:
            continue
        result.append(word)
        if len(result) >= limit:
            break
    return tuple(result)


def _idea_chunks(*texts: str, limit: int = 10) -> tuple[str, ...]:
    """Split reference prose into short ideas that a learner can express naturally."""

    result: list[str] = []
    for text in texts:
        clean = re.sub(r"^[^:—-]+[:—-]\s*", "", str(text or "").strip())
        parts = re.split(r"[;,.]|\b(?:і|та|або|and|or)\b", clean, flags=re.IGNORECASE)
        for part in parts:
            part = " ".join(part.strip(" :—-()[]").split())
            if len(part) < 3 or part.lower() in STOPWORDS or part in result:
                continue
            result.append(part)
            if len(result) >= limit:
                return tuple(result)
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
        "Застосувати інше правило, не перевіряючи умову",
        "Пропустити ключову ознаку в завданні",
        "Обрати форму навмання",
        "Не перевіряти отриману відповідь",
    )
    for candidate in fallbacks:
        if candidate not in values:
            values.append(candidate)
        if len(values) == 4:
            break
    return tuple(values[:4])


def _question_id(lesson: Lesson, index: int) -> str:
    return f"{lesson.curriculum_unit_id}-q{index:02d}"


def _question(
    lesson: Lesson,
    index: int,
    *,
    prompt: str,
    answer_type: str,
    correct_answer: str,
    points: int,
    options: tuple[str, ...] = (),
    accepted_answers: tuple[str, ...] = (),
    keywords: tuple[str, ...] = (),
    explanation: str,
    grading_mode: str = "concept",
    primary_answers: tuple[str, ...] = (),
    secondary_answers: tuple[str, ...] = (),
    feedback_hint: str = "Звір відповідь із правилом уроці й спробуй ще раз.",
) -> QuizQuestion:
    return QuizQuestion(
        id=_question_id(lesson, index),
        prompt=prompt,
        answer_type=answer_type,
        options=options,
        correct_answer=correct_answer,
        accepted_answers=accepted_answers or (correct_answer,),
        keywords=keywords or _tokens(correct_answer),
        explanation=explanation,
        points=points,
        grading_mode=grading_mode,
        primary_answers=primary_answers,
        secondary_answers=secondary_answers,
        feedback_hint=feedback_hint,
    )


def build_deterministic_quiz(lesson: Lesson) -> ProductionQuiz:
    """Build a clear 12-question, 24-point assessment from one lesson."""

    concepts = list(lesson.concepts)
    examples = list(lesson.worked_examples)
    mistakes = list(lesson.common_mistakes)
    tips = list(lesson.practical_tips)
    if not concepts or not examples or not mistakes:
        raise ValueError("lesson does not contain enough structured content for a production quiz")

    c1 = concepts[0]
    c2 = concepts[1 % len(concepts)]
    m1 = mistakes[0]
    m2 = mistakes[1 % len(mistakes)]
    e1 = examples[0]
    e2 = examples[1 % len(examples)]
    e3 = examples[2 % len(examples)]
    tip1 = tips[0] if tips else None
    recap_ideas = tuple(lesson.recap.main_ideas)
    formulas = tuple(lesson.recap.formulas)

    questions: list[QuizQuestion] = [
        _question(
            lesson,
            1,
            prompt=f"Що означає «{c1.title}»?",
            answer_type="choice",
            options=_unique_options(c1.what, (c1.common_confusion, c2.what, m1.incorrect_reasoning)),
            correct_answer=c1.what,
            explanation=f"Правильна відповідь: {c1.what}",
            points=1,
            grading_mode="choice",
        ),
        _question(
            lesson,
            2,
            prompt=f"Яке правило правильно описує «{c2.title}»?",
            answer_type="choice",
            options=_unique_options(c2.how, (c2.common_confusion, m2.incorrect_reasoning, c1.common_confusion)),
            correct_answer=c2.how,
            explanation=f"Правило: {c2.how}",
            points=1,
            grading_mode="choice",
        ),
        _question(
            lesson,
            3,
            prompt=f"Яке виправлення правильне для цієї помилки: «{m1.incorrect_reasoning}»?",
            answer_type="choice",
            options=_unique_options(m1.correction, (m2.correction, m1.why_incorrect, c1.common_confusion)),
            correct_answer=m1.correction,
            explanation=f"Правильне виправлення: {m1.correction}",
            points=1,
            grading_mode="choice",
        ),
        _question(
            lesson,
            4,
            prompt=f"Обери правильну відповідь до завдання: {e1.problem}",
            answer_type="choice",
            options=_unique_options(e1.final_answer, (e2.final_answer, m1.correction, c1.common_confusion)),
            correct_answer=e1.final_answer,
            explanation=f"Правильна відповідь: {e1.final_answer}",
            points=1,
            grading_mode="choice",
        ),
    ]

    c1_ideas = _idea_chunks(c1.what, c1.when_used, c1.why)
    c2_use_ideas = _idea_chunks(c2.when_used, c2.what)
    c2_form_ideas = _idea_chunks(c2.how)
    mistake_ideas = _idea_chunks(m1.incorrect_reasoning, m1.recognition)
    correction_ideas = _idea_chunks(m1.correction, m1.prevention)
    one_rule_answers = tuple(dict.fromkeys((*formulas, *recap_ideas, c1.how, c2.how)))

    questions.extend([
        _question(
            lesson,
            5,
            prompt=f"Одним-двома реченнями поясни, коли або для чого використовують «{c1.title}».",
            answer_type="short_text",
            correct_answer=c1.what,
            accepted_answers=(c1.what, c1.when_used),
            primary_answers=c1_ideas or (c1.what,),
            explanation=f"Приклад повної відповіді: {c1.what}",
            feedback_hint="Назви хоча б один правильний випадок використання. Довгий текст не потрібен.",
            points=2,
            grading_mode="concept",
        ),
        _question(
            lesson,
            6,
            prompt=f"Коли використовують «{c2.title}» і як утворюють цю форму? Напиши коротко.",
            answer_type="short_text",
            correct_answer=f"Коли: {c2.when_used} Форма: {c2.how}",
            accepted_answers=(c2.how, c2.when_used, f"{c2.when_used} {c2.how}"),
            primary_answers=c2_use_ideas or (c2.when_used,),
            secondary_answers=c2_form_ideas or (c2.how,),
            explanation=f"Приклад: {c2.when_used} Форма: {c2.how}",
            feedback_hint="За один правильний елемент дається 1 бал. Для 2 балів напиши і коли вживаємо, і як утворюємо.",
            points=2,
            grading_mode="two_part",
        ),
        _question(
            lesson,
            7,
            prompt="Назви одну типову помилку з уроку та покажи, як її виправити.",
            answer_type="short_text",
            correct_answer=f"Помилка: {m1.incorrect_reasoning} Виправлення: {m1.correction}",
            accepted_answers=(f"{m1.incorrect_reasoning} {m1.correction}",),
            primary_answers=mistake_ideas or (m1.incorrect_reasoning,),
            secondary_answers=correction_ideas or (m1.correction,),
            explanation=f"Приклад: {m1.incorrect_reasoning} Виправлення: {m1.correction}",
            feedback_hint="За названу помилку дається 1 бал, за правильне виправлення ще 1.",
            points=2,
            grading_mode="two_part",
        ),
        _question(
            lesson,
            8,
            prompt="Запиши одне правильне правило, формулу або головну ідею з уроку. Достатньо одного.",
            answer_type="short_text",
            correct_answer=one_rule_answers[0],
            accepted_answers=one_rule_answers,
            primary_answers=one_rule_answers,
            explanation=f"Один із можливих варіантів: {one_rule_answers[0]}",
            feedback_hint="Тут не треба переписувати весь урок. Одного правильного правила достатньо.",
            points=2,
            grading_mode="any_valid",
        ),
    ])

    def solution_question(index: int, example) -> QuizQuestion:
        steps = " ".join(step.work for step in example.steps)
        full = f"{example.reasoning} {steps} Відповідь: {example.final_answer}"
        return _question(
            lesson,
            index,
            prompt=(
                f"Розв’яжи завдання: {example.problem} "
                "Правильна кінцева відповідь дає 2 бали, коротке пояснення вибору правила або кроків дає ще 1 бал."
            ),
            answer_type="long_text",
            correct_answer=full,
            accepted_answers=(full, example.final_answer),
            primary_answers=(example.final_answer,),
            secondary_answers=(example.reasoning, steps, *(step.explanation for step in example.steps)),
            explanation=f"Приклад повного розв’язання: {full}",
            feedback_hint="Спочатку запиши кінцеву відповідь. Для повних 3 балів додай коротке пояснення.",
            points=3,
            grading_mode="solution",
        )

    questions.extend((
        solution_question(9, e1),
        solution_question(10, e2),
        solution_question(11, e3),
    ))

    questions.append(_question(
        lesson,
        12,
        prompt=(
            f"Поясни, як перевірити власний результат у завданні: {e3.problem} "
            "Не повторюй весь розв’язок: назви правило або ознаку та один надійний спосіб перевірки."
        ),
        answer_type="long_text",
        correct_answer=f"Перевірка: {e3.verification} Правило: {c2.how}",
        accepted_answers=(e3.verification, f"{e3.verification} {c2.how}", c2.how),
        primary_answers=(e3.verification,),
        secondary_answers=(c2.how, c2.when_used, e3.reasoning),
        explanation=f"Приклад перевірки: {e3.verification}",
        feedback_hint="Назви хоча б один реальний спосіб перевірки. Ще 1 бал дається за пов’язане правило або ознаку.",
        points=3,
        grading_mode="verification",
    ))

    fingerprint = hashlib.sha256(
        f"quiz.v1.2|{lesson.id}|{lesson.generation_metadata.request_fingerprint}".encode("utf-8")
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
        schema_version="quiz.v1.2-contextual-easy",
    )
