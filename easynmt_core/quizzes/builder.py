"""Clear, deterministic and server-gradeable curriculum quiz builder."""
from __future__ import annotations

import hashlib
import re
from typing import Iterable

from easynmt_ai.lessons import Lesson

from .models import ProductionQuiz, QuizQuestion
from .task_bank import AssessmentTask, get_topic_tasks


STOPWORDS = frozenset({
    "і", "й", "та", "у", "в", "на", "до", "з", "із", "за", "для", "що", "як", "це",
    "the", "a", "an", "to", "of", "in", "on", "and", "or", "is", "are", "be", "with",
})

_GENERIC_TASK_PATTERNS = (
    r"\bвибір\s+(?:правильної|потрібної)",
    r"\bрозпізнавання\s+(?:основної|ключової|правильної)",
    r"\bзастосування\s+(?:правила|алгоритму|ознаки)",
    r"\bвиконай\s+(?:історичне|мовне|математичне|англійське)?\s*завдання\b",
    r"\bcomplete an english language task\b",
    r"\bу форматі нмт\b.*\bдистрактор",
    r"\bтема\s*:",
    r"\bобрати варіант,? що відповідає\b",
)

_GENERIC_ANSWER_PATTERNS = (
    r"\bобрано варіант\b",
    r"\bвідповідає всім визначеним ознакам\b",
    r"\bправильний варіант\b",
    r"\bзастосовано схему\b",
    r"\bпідтверджено умовою\b",
)

_TITLE_PREFIXES = (
    r"^основа теми\s*:\s*",
    r"^застосування й перевірка\s*:\s*",
    r"^головна ідея\s*:\s*",
)


def _clean(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _human_label(value: object) -> str:
    result = _clean(value)
    for pattern in _TITLE_PREFIXES:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    return result or "ця тема"


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
    values = [_clean(correct)]
    for candidate in candidates:
        candidate = _clean(candidate)
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


def _compose_prompt(instruction: str, task: str, answer_format: str) -> str:
    return f"{_clean(instruction)}\n{_clean(task)}\nЯк відповісти: {_clean(answer_format)}"


def _question(
    lesson: Lesson,
    index: int,
    *,
    instruction: str,
    task: str,
    answer_format: str,
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
    feedback_hint: str = "Звір відповідь із правилом уроку й спробуй ще раз.",
) -> QuizQuestion:
    instruction = _clean(instruction)
    task = _clean(task)
    answer_format = _clean(answer_format)
    return QuizQuestion(
        id=_question_id(lesson, index),
        prompt=_compose_prompt(instruction, task, answer_format),
        instruction=instruction,
        task=task,
        answer_format=answer_format,
        answer_type=answer_type,
        options=options,
        correct_answer=_clean(correct_answer),
        accepted_answers=tuple(_clean(item) for item in (accepted_answers or (correct_answer,))),
        keywords=keywords or _tokens(correct_answer),
        explanation=_clean(explanation),
        points=points,
        grading_mode=grading_mode,
        primary_answers=tuple(_clean(item) for item in primary_answers),
        secondary_answers=tuple(_clean(item) for item in secondary_answers),
        feedback_hint=_clean(feedback_hint),
    )


def _is_concrete_example(example) -> bool:
    problem = _clean(getattr(example, "problem", ""))
    final_answer = _clean(getattr(example, "final_answer", ""))
    if len(problem) < 12 or len(final_answer) < 1:
        return False
    lowered_problem = problem.lower()
    lowered_answer = final_answer.lower()
    if any(re.search(pattern, lowered_problem, flags=re.IGNORECASE) for pattern in _GENERIC_TASK_PATTERNS):
        return False
    if any(re.search(pattern, lowered_answer, flags=re.IGNORECASE) for pattern in _GENERIC_ANSWER_PATTERNS):
        return False
    concrete_signal = bool(
        re.search(r"\d|[_=+−–—<>≤≥√π%°]|[«»“”\"]|\([^)]{1,80}\)", problem)
        or problem.endswith("?")
        or re.search(r"\b(?:обчисли|розв['’]?яжи|знайди|встав|complete|rewrite|read|назви|визнач|постав|відредагуй|розстав)\b", lowered_problem)
    )
    return concrete_signal


def _task_from_example(example) -> AssessmentTask:
    steps = " ".join(_clean(step.work) for step in example.steps if _clean(step.work))
    reasoning = _clean(example.reasoning)
    if steps and steps.lower() not in reasoning.lower():
        reasoning = f"{reasoning} Кроки: {steps}"
    return AssessmentTask(
        task=_clean(example.problem),
        final_answer=_clean(example.final_answer),
        reasoning=reasoning,
        verification=_clean(example.verification),
    )


def _assessment_tasks(lesson: Lesson) -> tuple[AssessmentTask, AssessmentTask, AssessmentTask]:
    """Prefer concrete lesson examples and replace only abstract placeholders."""

    result: list[AssessmentTask] = []
    seen: set[str] = set()
    for example in lesson.worked_examples:
        if not _is_concrete_example(example):
            continue
        task = _task_from_example(example)
        key = task.task.casefold()
        if key not in seen:
            result.append(task)
            seen.add(key)
        if len(result) == 3:
            return tuple(result)  # type: ignore[return-value]

    for task in get_topic_tasks(lesson.topic_id):
        key = task.task.casefold()
        if key not in seen:
            result.append(task)
            seen.add(key)
        if len(result) == 3:
            return tuple(result)  # type: ignore[return-value]
    raise ValueError(f"not enough concrete tasks for topic {lesson.topic_id}")


def build_deterministic_quiz(lesson: Lesson) -> ProductionQuiz:
    """Build a student-readable 12-question, 24-point assessment."""

    concepts = list(lesson.concepts)
    mistakes = list(lesson.common_mistakes)
    if not concepts or not mistakes:
        raise ValueError("lesson does not contain enough structured content for a production quiz")

    c1 = concepts[0]
    c2 = concepts[1 % len(concepts)]
    m1 = mistakes[0]
    m2 = mistakes[1 % len(mistakes)]
    t1, t2, t3 = _assessment_tasks(lesson)
    recap_ideas = tuple(_clean(item) for item in lesson.recap.main_ideas)
    formulas = tuple(_clean(item) for item in lesson.recap.formulas)
    c1_title = _human_label(c1.title)
    c2_title = _human_label(c2.title)

    questions: list[QuizQuestion] = [
        _question(
            lesson,
            1,
            instruction="Обери один варіант.",
            task=f"Яке пояснення найкраще передає зміст поняття «{c1_title}»?",
            answer_format="Познач одну відповідь.",
            answer_type="choice",
            options=_unique_options(c1.what, (c1.common_confusion, c2.what, m1.incorrect_reasoning)),
            correct_answer=c1.what,
            explanation=f"Правильне пояснення: {c1.what}",
            feedback_hint="Перечитай, що означає це поняття, і не плутай його з типовою помилкою.",
            points=1,
            grading_mode="choice",
        ),
        _question(
            lesson,
            2,
            instruction="Обери один варіант.",
            task=f"Який алгоритм треба застосувати, коли в завданні працює правило «{c2_title}»?",
            answer_format="Познач один алгоритм.",
            answer_type="choice",
            options=_unique_options(c2.how, (c2.common_confusion, m2.incorrect_reasoning, c1.common_confusion)),
            correct_answer=c2.how,
            explanation=f"Алгоритм із уроку: {c2.how}",
            feedback_hint="Шукай варіант, у якому є послідовність дій, а не опис помилки.",
            points=1,
            grading_mode="choice",
        ),
        _question(
            lesson,
            3,
            instruction="Обери правильне виправлення.",
            task=f"Учень зробив так: «{_clean(m1.incorrect_reasoning)}» Що треба змінити?",
            answer_format="Познач один варіант виправлення.",
            answer_type="choice",
            options=_unique_options(m1.correction, (m2.correction, m1.why_incorrect, c1.common_confusion)),
            correct_answer=m1.correction,
            explanation=f"Правильне виправлення: {m1.correction}",
            feedback_hint="Знайди варіант, який прямо усуває описану помилку.",
            points=1,
            grading_mode="choice",
        ),
        _question(
            lesson,
            4,
            instruction="Виконай коротке завдання й обери результат.",
            task=t1.task,
            answer_format="Познач один готовий результат.",
            answer_type="choice",
            options=_unique_options(t1.final_answer, (t2.final_answer, t3.final_answer, c1.common_confusion)),
            correct_answer=t1.final_answer,
            explanation=f"Правильний результат: {t1.final_answer} Пояснення: {t1.reasoning}",
            feedback_hint="Спочатку виконай завдання сам, а потім зістав результат із варіантами.",
            points=1,
            grading_mode="choice",
        ),
    ]

    c1_ideas = _idea_chunks(c1.what, c1.when_used, c1.why)
    c2_use_ideas = _idea_chunks(c2.when_used, c2.what)
    c2_form_ideas = _idea_chunks(c2.how)
    mistake_ideas = _idea_chunks(m1.incorrect_reasoning, m1.recognition, m1.why_incorrect)
    correction_ideas = _idea_chunks(m1.correction, m1.prevention)
    one_rule_answers = tuple(dict.fromkeys(item for item in (*formulas, *recap_ideas, _clean(c1.how), _clean(c2.how)) if item))
    if not one_rule_answers:
        one_rule_answers = (_clean(c1.what),)

    questions.extend([
        _question(
            lesson,
            5,
            instruction="Поясни своїми словами.",
            task=f"Коли або для чого використовують «{c1_title}»?",
            answer_format="Напиши 1–2 короткі речення. Достатньо одного правильного випадку використання.",
            answer_type="short_text",
            correct_answer=c1.what,
            accepted_answers=(c1.what, c1.when_used),
            primary_answers=c1_ideas or (_clean(c1.what),),
            explanation=f"Один із повних варіантів: {c1.what}",
            feedback_hint="Назви хоча б один правильний випадок використання. Довгий текст не потрібен.",
            points=2,
            grading_mode="concept",
        ),
        _question(
            lesson,
            6,
            instruction="Дай відповідь із двох частин.",
            task=f"Коли використовують «{c2_title}» і що треба зробити за цим правилом?",
            answer_format="1) коли використовують; 2) короткий алгоритм або форма. Кожна правильна частина дає 1 бал.",
            answer_type="short_text",
            correct_answer=f"Коли: {c2.when_used} Алгоритм: {c2.how}",
            accepted_answers=(c2.how, c2.when_used, f"{c2.when_used} {c2.how}"),
            primary_answers=c2_use_ideas or (_clean(c2.when_used),),
            secondary_answers=c2_form_ideas or (_clean(c2.how),),
            explanation=f"Приклад повної відповіді: {c2.when_used} Алгоритм: {c2.how}",
            feedback_hint="За один правильний елемент дається 1 бал. Для 2 балів напиши і випадок використання, і спосіб дії.",
            points=2,
            grading_mode="two_part",
        ),
        _question(
            lesson,
            7,
            instruction="Знайди помилку й виправ її.",
            task=f"Учень міркує так: «{_clean(m1.incorrect_reasoning)}» Поясни, що тут не так, і напиши правильний спосіб.",
            answer_format="1–2 речення: помилка + виправлення. За кожну частину дається 1 бал.",
            answer_type="short_text",
            correct_answer=f"Помилка: {m1.why_incorrect} Виправлення: {m1.correction}",
            accepted_answers=(f"{m1.incorrect_reasoning} {m1.correction}", f"{m1.why_incorrect} {m1.correction}"),
            primary_answers=mistake_ideas or (_clean(m1.why_incorrect),),
            secondary_answers=correction_ideas or (_clean(m1.correction),),
            explanation=f"Приклад повної відповіді: {m1.why_incorrect} Виправлення: {m1.correction}",
            feedback_hint="За пояснення помилки дається 1 бал, за правильне виправлення ще 1.",
            points=2,
            grading_mode="two_part",
        ),
        _question(
            lesson,
            8,
            instruction="Запиши одне правило з уроку.",
            task="Обери будь-яке одне правило, формулу або головну ідею, яку треба пам’ятати під час виконання завдань цієї теми.",
            answer_format="Одне коротке правило своїми словами. Переписувати весь урок не потрібно.",
            answer_type="short_text",
            correct_answer=one_rule_answers[0],
            accepted_answers=one_rule_answers,
            primary_answers=one_rule_answers,
            explanation=f"Один із можливих варіантів: {one_rule_answers[0]}",
            feedback_hint="Одного правильного правила достатньо. Спробуй назвати його коротко й конкретно.",
            points=2,
            grading_mode="any_valid",
        ),
    ])

    def solution_question(index: int, task: AssessmentTask) -> QuizQuestion:
        full = f"{task.reasoning} Відповідь: {task.final_answer}"
        return _question(
            lesson,
            index,
            instruction="Виконай конкретне завдання.",
            task=task.task,
            answer_format="Спочатку напиши кінцеву відповідь. Потім додай 1–2 речення: яка ознака або правило допомогли. Відповідь дає 2 бали, пояснення ще 1.",
            answer_type="long_text",
            correct_answer=full,
            accepted_answers=(full, task.final_answer),
            primary_answers=(task.final_answer,),
            secondary_answers=(task.reasoning,),
            explanation=f"Приклад повної відповіді: {full}",
            feedback_hint="Правильний кінцевий результат дає 2 бали. Для повних 3 балів додай коротке пояснення вибору правила або кроків.",
            points=3,
            grading_mode="solution",
        )

    questions.extend((
        solution_question(9, t1),
        solution_question(10, t2),
        solution_question(11, t3),
    ))

    questions.append(_question(
        lesson,
        12,
        instruction="Поясни, як перевірити результат.",
        task=f"Повернися до завдання №11: {t3.task}",
        answer_format="Назви один реальний спосіб перевірки та коротко поясни, що саме він підтвердить. Повторювати весь розв’язок не потрібно.",
        answer_type="long_text",
        correct_answer=f"Перевірка: {t3.verification} Пов’язане міркування: {t3.reasoning}",
        accepted_answers=(t3.verification, f"{t3.verification} {t3.reasoning}"),
        primary_answers=(t3.verification,),
        secondary_answers=(t3.reasoning, _clean(c2.how), _clean(c2.when_used)),
        explanation=f"Приклад перевірки: {t3.verification}",
        feedback_hint="Назви хоча б один конкретний спосіб перевірки. Ще 1 бал дається за пояснення того, що саме він підтверджує.",
        points=3,
        grading_mode="verification",
    ))

    # Keep the v1.2 identifier seed so an existing per-lesson quiz row can be
    # upgraded in place.  The schema version below forces the content refresh.
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
        schema_version="quiz.v1.3-student-clarity",
    )
