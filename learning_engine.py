import re
from typing import Any

PASS_SCORE = 18
MAX_SCORE = 24


def normalize_text(value: str | None) -> str:
    text = (value or "").strip().lower().replace("−", "-").replace("–", "-")
    text = text.replace(",", ".")
    text = re.sub(r"\s*([;=])\s*", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text


STOP_WORDS = {
    "а", "але", "бо", "в", "від", "до", "для", "з", "за", "і", "й", "на", "не",
    "та", "у", "що", "це", "як", "the", "a", "an", "and", "in", "is", "of", "to",
}


def meaningful_tokens(value: str | None) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zа-яіїєґ0-9-]+", normalize_text(value), flags=re.IGNORECASE)
        if len(token) > 1 and token not in STOP_WORDS
    }


def _written(question: str, answer: str, explanation: str, points: int = 2,
             accepted: list[str] | None = None, keywords: list[str] | None = None,
             placeholder: str = "Напиши свою відповідь") -> dict[str, Any]:
    return {
        "type": "written",
        "question": question,
        "answer": answer,
        "accepted": accepted or [answer],
        "keywords": keywords or [],
        "points": points,
        "explanation": explanation,
        "placeholder": placeholder,
    }


def _mc(question: str, options: list[str], answer: str, explanation: str) -> dict[str, Any]:
    return {
        "type": "choice",
        "question": question,
        "options": options,
        "answer": answer,
        "points": 1,
        "explanation": explanation,
    }


WRITTEN_BANK: dict[str, dict[int, list[dict[str, Any]]]] = {
    "math": {
        1: [
            _written("Знайди дискримінант рівняння x² - 5x + 6 = 0.", "1", "D = (-5)² - 4·1·6 = 25 - 24 = 1."),
            _written("Запиши корені рівняння x² - 5x + 6 = 0.", "2; 3", "Після D = 1 отримуємо x₁ = 2, x₂ = 3.", accepted=["2;3", "3;2", "2 3", "3 2", "x1=2 x2=3", "x₁=2 x₂=3"]),
            _written("Скільки дійсних коренів має x² + 4x + 5 = 0?", "0", "D = 16 - 20 = -4, тому дійсних коренів немає.", accepted=["0", "немає", "жодного"]),
            _written("Розв’яжи x² - 9 = 0.", "-3; 3", "x² = 9, тому x = -3 або x = 3.", accepted=["-3;3", "3;-3", "-3 3", "3 -3"]),
            _written("Розв’яжи 2x² - 8x + 6 = 0. Запиши хід розв’язання.", "x = 1; x = 3", "Поділимо на 2: x² - 4x + 3 = 0. D = 4, тому x = 1 і x = 3.", points=3, keywords=["1", "3", "d", "4"], placeholder="Запиши всі кроки та остаточну відповідь"),
            _written("Для яких x вираз x² - 6x + 9 дорівнює нулю? Поясни коротко.", "x = 3", "x² - 6x + 9 = (x - 3)², квадрат дорівнює нулю лише при x = 3.", points=3, keywords=["3", "(x-3)", "квадрат"], placeholder="Коротко поясни, як ти це зрозумів"),
            _written("Склади квадратне рівняння, корені якого 2 і 5.", "x² - 7x + 10 = 0", "(x - 2)(x - 5) = 0, після розкриття дужок маємо x² - 7x + 10 = 0.", points=3, keywords=["x", "7", "10", "0"], placeholder="Запиши рівняння"),
            _written("Розв’яжи x(x - 4) = 5 і запиши основні кроки.", "x = -1; x = 5", "x² - 4x - 5 = 0. D = 36, тому x = -1 і x = 5.", points=3, keywords=["-1", "5", "36"], placeholder="Запиши розв’язання крок за кроком"),
        ],
        2: [
            _written("Розв’яжи 3x + 7 = 22.", "5", "3x = 15, тому x = 5."),
            _written("Розв’яжи 7 - x = 2.", "5", "-x = -5, тому x = 5."),
            _written("Розв’яжи 0,5x = 4.", "8", "x = 4 : 0,5 = 8."),
            _written("Розв’яжи 3(x + 2) = 15.", "3", "x + 2 = 5, тому x = 3."),
            _written("Розв’яжи 4(2x - 1) = 3x + 16. Запиши кроки.", "4", "8x - 4 = 3x + 16, звідси 5x = 20 і x = 4.", points=3, keywords=["8x", "5x", "20", "4"]),
            _written("У першій коробці на 6 олівців більше, ніж у другій. Разом 24. Скільки в кожній?", "15 і 9", "Нехай у другій x, тоді в першій x + 6. 2x + 6 = 24, x = 9, отже 15 і 9.", points=3, keywords=["9", "15", "2x", "24"]),
            _written("Розв’яжи (x - 2)/3 = 5.", "17", "x - 2 = 15, тому x = 17.", points=3, keywords=["15", "17"]),
            _written("Знайди число, 40% якого дорівнюють 28. Запиши рівняння.", "70", "0,4x = 28, тому x = 70.", points=3, keywords=["0.4", "28", "70"]),
        ],
        3: [
            _written("Для y = 2x + 1 знайди y, якщо x = 4.", "9", "y = 2·4 + 1 = 9."),
            _written("Знайди нуль функції y = x - 6.", "6", "Нуль функції: y = 0, тому x - 6 = 0 і x = 6."),
            _written("Чи зростає функція y = -3x + 2?", "ні", "Коефіцієнт біля x від’ємний, тому функція спадає.", accepted=["ні", "спадає", "не зростає"]),
            _written("Запиши координати точки, де x = 2, y = -1.", "(2; -1)", "Спочатку записуємо x, потім y: (2; -1).", accepted=["(2;-1)", "2;-1", "2 -1"]),
            _written("Знайди рівняння прямої, що проходить через точки (0; 1) і (2; 5).", "y = 2x + 1", "k = (5 - 1)/(2 - 0) = 2, а при x = 0 маємо b = 1.", points=3, keywords=["2x", "+1", "k", "2"]),
            _written("Знайди точку перетину y = 3x - 6 з віссю Ox.", "(2; 0)", "На осі Ox y = 0: 3x - 6 = 0, x = 2.", points=3, keywords=["2", "0", "3x"]),
            _written("Порівняй y = 2x + 1 та y = 2x - 4. Чи перетинаються їх графіки?", "ні", "Кутові коефіцієнти однакові, вільні члени різні, отже прямі паралельні.", points=3, keywords=["ні", "паралель", "2"]),
            _written("Для y = -x + 5 знайди точки перетину з обома осями.", "(0; 5) і (5; 0)", "При x = 0 маємо (0; 5), при y = 0 маємо x = 5, тобто (5; 0).", points=3, keywords=["0", "5", "(0", "(5"]),
        ],
    },
    "ukrainian": {}, "history": {}, "english": {}, "none": {},
}

# Для нематематичних предметів письмові завдання перевіряються за ключовими словами.
GENERIC_WRITTEN = {
    "ukrainian": [
        ("Поясни правило своїми словами й наведи один приклад.", "Правило і доречний приклад", ["правило", "приклад"]),
        ("Запиши правильний варіант і коротко поясни вибір.", "Правильний варіант із поясненням", ["тому", "бо"]),
        ("Знайди помилку у власному прикладі та виправ її.", "Виправлений варіант", ["правильно"]),
        ("Склади одне речення, у якому працює правило з уроку.", "Коректне речення", []),
        ("Поясни, як розпізнати це правило в завданні НМТ.", "Ознака правила", ["ознака", "правило"]),
        ("Порівняй правильний і неправильний варіанти.", "Порівняння з поясненням", ["неправильно", "правильно"]),
        ("Виправ речення й обґрунтуй зміну.", "Виправлене речення", ["бо", "правило"]),
        ("Створи власне завдання на цю тему та дай відповідь.", "Власне завдання з відповіддю", ["відповідь"]),
    ],
    "history": [
        ("Назви ключову дату теми та подію, що з нею пов’язана.", "Дата і подія", []),
        ("Назви історичного діяча та одну його дію.", "Діяч і дія", []),
        ("Запиши одну причину події.", "Причина події", ["тому", "через"]),
        ("Запиши один наслідок події.", "Наслідок події", ["наслідок", "призвело"]),
        ("Побудуй короткий ланцюжок: причина → подія → наслідок.", "Логічний ланцюжок", ["→"]),
        ("Порівняй дві постаті або органи влади з теми.", "Коректне порівняння", []),
        ("Поясни значення події для України двома реченнями.", "Значення події", ["україн"]),
        ("Розмісти три події теми в правильній послідовності.", "Хронологічна послідовність", []),
    ],
    "english": [
        ("Write one correct sentence using the rule from this lesson.", "A grammatically correct sentence", []),
        ("Rewrite the sentence in the negative form.", "Correct negative sentence", ["not"]),
        ("Write a question using the grammar from the lesson.", "Correct question", ["?"]),
        ("Correct the mistake and write the full sentence.", "Corrected sentence", []),
        ("Explain in Ukrainian when this form is used.", "Correct explanation", []),
        ("Write two related sentences: one simple and one more detailed.", "Two correct sentences", []),
        ("Choose the correct tense and explain the time marker.", "Tense and marker", []),
        ("Create a short NMT-style example and provide the answer.", "Example and answer", ["answer"]),
    ],
    "none": [
        ("Напиши, що ти хочеш вивчити сьогодні.", "Навчальна ціль", []),
        ("Сформулюй одне питання до теми.", "Питання", []),
        ("Запиши один факт, який уже знаєш.", "Факт", []),
        ("Назви крок, з якого почнеш.", "Перший крок", []),
        ("Коротко поясни тему своїми словами.", "Пояснення", []),
        ("Наведи один приклад.", "Приклад", []),
        ("Запиши типову помилку.", "Помилка", []),
        ("Склади короткий план повторення.", "План", []),
    ],
}


def build_quiz(subject: str, lesson_id: int, choice_questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    choices = []
    for q in choice_questions[:4]:
        choices.append(_mc(q["question"], list(q["options"]), q["answer"], q.get("explanation", f"Зверни увагу: правильна відповідь — {q['answer']}.")))
    while len(choices) < 4:
        choices.append(_mc("Що найкраще зробити після пояснення теми?", ["Спробувати завдання самостійно", "Пропустити тему", "Вгадати відповідь"], "Спробувати завдання самостійно", "Після пояснення спробуй виконати завдання самостійно. Так ти одразу побачиш, що вже зрозумів."))

    written = WRITTEN_BANK.get(subject, {}).get(lesson_id)
    if not written:
        generic = GENERIC_WRITTEN.get(subject, GENERIC_WRITTEN["none"])
        written = []
        for index, (question, answer, keywords) in enumerate(generic):
            points = 2 if index < 4 else 3
            written.append(_written(question, answer, "Перевір, чи відповідь конкретна й спирається на правило з уроку.", points=points, keywords=keywords, placeholder="Напиши свою відповідь своїми словами"))
    return choices + written[:8]


def grade_question(question: dict[str, Any], user_answer: str | None) -> tuple[int, bool, str]:
    points = int(question.get("points", 1))
    answer = normalize_text(user_answer)
    if not answer:
        return 0, False, "Відповіді немає. Повернися до умови й запиши хоча б перший крок."

    if question.get("type") == "choice":
        correct = answer == normalize_text(question.get("answer"))
        return (points if correct else 0), correct, question.get("explanation", "")

    accepted = [normalize_text(item) for item in question.get("accepted", [])]
    if answer in accepted:
        return points, True, question.get("explanation", "")

    keywords = [normalize_text(item) for item in question.get("keywords", []) if item]
    matched = sum(1 for keyword in keywords if keyword in answer)
    if keywords:
        ratio = matched / len(keywords)
        earned = round(points * ratio)
        if ratio >= 0.75:
            return max(1, earned), earned == points, question.get("explanation", "")
        if ratio >= 0.35:
            return max(1, earned), False, "Напрям правильний, але відповідь неповна. " + question.get("explanation", "")

    # Without an explicit rubric, require evidence from the reference answer.
    # Length alone must never award points for unrelated prose.
    if not keywords:
        reference_tokens = set().union(*(meaningful_tokens(item) for item in question.get("accepted", [])))
        answer_tokens = meaningful_tokens(answer)
        if reference_tokens:
            overlap = len(reference_tokens & answer_tokens) / len(reference_tokens)
            if overlap >= 0.8:
                return points, True, question.get("explanation", "")
            if overlap >= 0.5:
                return max(1, points // 2), False, "Відповідь частково правильна. " + question.get("explanation", "")

    return 0, False, question.get("explanation", "Перевір правило й спробуй ще раз.")
