import re
import unicodedata


def _clean(value):
    text = unicodedata.normalize('NFKC', str(value or '')).lower().strip()
    text = text.replace('−', '-').replace('–', '-').replace('—', '-')
    text = re.sub(r'\s+', ' ', text)
    return text


def build_twelve_question_quiz(raw_questions, subject_key, lesson_id):
    """Build a stable 12-question fallback quiz.

    Questions 1-4 are multiple choice, 5-8 short written answers,
    and 9-12 ask for a written solution. OpenAI can later replace the
    fallback content while keeping this exact schema.
    """
    if not raw_questions:
        raw_questions = [{
            'question': 'Що варто зробити після пояснення теми?',
            'options': ['виконати практику', 'закрити урок', 'пропустити тест'],
            'answer': 'виконати практику',
            'explanation': 'Після пояснення потрібна коротка практика, щоб перевірити розуміння.'
        }]

    source = list(raw_questions)
    result = []
    stage_names = {1: 'Розігрів', 2: 'Практика', 3: 'Задачі'}

    for index in range(12):
        original = dict(source[index % len(source)])
        number = index + 1
        stage = 1 if number <= 4 else 2 if number <= 8 else 3
        qtype = 'choice' if stage == 1 else 'short' if stage == 2 else 'solution'
        answer = str(original.get('answer', '')).strip()
        prompt = str(original.get('question', 'Питання')).strip()

        if stage == 2:
            prompt = f"{prompt} Запиши відповідь самостійно."
        elif stage == 3:
            prompt = f"{prompt} Покажи основні кроки й напиши кінцеву відповідь."

        result.append({
            'id': f'{subject_key}_{lesson_id}_{number}',
            'number': number,
            'stage': stage,
            'stage_name': stage_names[stage],
            'type': qtype,
            'question': prompt,
            'options': list(original.get('options') or []),
            'answer': answer,
            'explanation': original.get('explanation') or (
                f"Правильна відповідь: {answer}. Порівняй її зі своїм записом і перевір крок, де з'явилася різниця."
            ),
            'points': stage,
        })

    return result


def grade_written_answer(user_answer, correct_answer):
    """Conservative fallback grading used before OpenAI is connected.

    It accepts an exact normalized answer or a final answer that clearly
    contains the expected value. The AI grader can later provide richer
    feedback without changing routes or templates.
    """
    user = _clean(user_answer)
    correct = _clean(correct_answer)

    if not user:
        return False
    if user == correct:
        return True

    compact_user = re.sub(r'[^a-zа-яіїєґ0-9.,=+\-/]', '', user)
    compact_correct = re.sub(r'[^a-zа-яіїєґ0-9.,=+\-/]', '', correct)

    if compact_correct and compact_correct in compact_user:
        return True

    # Accept common forms such as "x = 4" when the expected answer is "4".
    if re.fullmatch(r'-?\d+(?:[.,]\d+)?', compact_correct):
        numbers = re.findall(r'-?\d+(?:[.,]\d+)?', compact_user)
        return compact_correct.replace(',', '.') in {n.replace(',', '.') for n in numbers}

    return False
