"""Deterministic learning engine for EasyNMT v0.9.8.

OpenAI can later replace or enrich lesson/test generation, while this module
keeps the platform usable and predictable without an API key.
"""
from __future__ import annotations

import re
from typing import Any

PASS_SCORE = 18
MAX_SCORE = 24


def normalize_answer(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    text = text.replace(",", ".")
    text = re.sub(r"\s+", " ", text)
    return text


def _choice(question: str, options: list[str], answer: str, explanation: str) -> dict[str, Any]:
    return {
        "type": "choice",
        "points": 1,
        "question": question,
        "options": options,
        "answer": answer,
        "accepted": [answer],
        "explanation": explanation,
    }


def _short(question: str, answer: str, accepted: list[str], explanation: str) -> dict[str, Any]:
    return {
        "type": "short",
        "points": 2,
        "question": question,
        "answer": answer,
        "accepted": accepted,
        "placeholder": "Напиши коротку відповідь",
        "explanation": explanation,
    }


def _solution(question: str, answer: str, accepted: list[str], keywords: list[str], explanation: str) -> dict[str, Any]:
    return {
        "type": "solution",
        "points": 3,
        "question": question,
        "answer": answer,
        "accepted": accepted,
        "keywords": keywords,
        "placeholder": "Запиши хід розв’язання і відповідь",
        "explanation": explanation,
    }


MATH_QUIZZES: dict[int, list[dict[str, Any]]] = {
    1: [
        _choice("Який запис є квадратним рівнянням?", ["2x + 3 = 0", "x² - 5x + 6 = 0", "3/x = 2", "x³ = 8"], "x² - 5x + 6 = 0", "Квадратне рівняння містить x² і має вигляд ax² + bx + c = 0, де a ≠ 0."),
        _choice("Формула дискримінанта:", ["D = b² - 4ac", "D = a² + b²", "D = 2a + b", "D = b - ac"], "D = b² - 4ac", "Спочатку визначаємо a, b, c, а потім обчислюємо D = b² - 4ac."),
        _choice("Якщо D = 0, квадратне рівняння має:", ["два різні корені", "один корінь", "жодного кореня", "безліч коренів"], "один корінь", "Коли D = 0, обидва корені збігаються."),
        _choice("У рівнянні x² - 7x + 10 = 0 коефіцієнт b дорівнює:", ["1", "-7", "7", "10"], "-7", "Коефіцієнт b стоїть біля x. Тут це -7."),
        _short("Обчисли дискримінант рівняння x² - 5x + 6 = 0.", "1", ["1", "d=1", "d = 1"], "D = (-5)² - 4·1·6 = 25 - 24 = 1."),
        _short("Знайди суму коренів рівняння x² - 5x + 6 = 0.", "5", ["5", "x1+x2=5", "x₁+x₂=5"], "За теоремою Вієта x₁ + x₂ = -b/a = 5."),
        _short("Знайди добуток коренів рівняння x² - 5x + 6 = 0.", "6", ["6", "x1*x2=6", "x₁·x₂=6"], "За теоремою Вієта x₁x₂ = c/a = 6."),
        _short("Розв’яжи x² = 49. Запиши обидва корені.", "-7; 7", ["-7;7", "-7,7", "7;-7", "7,-7", "x=-7,7", "x=±7", "+-7", "±7"], "Якщо x² = 49, то x = 7 або x = -7."),
        _solution("Розв’яжи рівняння x² - 5x + 6 = 0. Покажи основні кроки.", "x₁ = 2, x₂ = 3", ["2;3", "3;2", "x1=2 x2=3", "x₁=2 x₂=3"], ["d", "1", "2", "3"], "D = 25 - 24 = 1. x = (5 ± 1)/2, тому корені 2 і 3."),
        _solution("Розв’яжи 2x² - 8 = 0.", "x = -2 або x = 2", ["-2;2", "2;-2", "x=±2", "±2"], ["2x²", "x²", "4", "2"], "2x² = 8, тому x² = 4 і x = ±2."),
        _solution("Сторони прямокутника відрізняються на 3 см, а площа дорівнює 40 см². Знайди сторони.", "5 см і 8 см", ["5 і 8", "5;8", "8;5", "5 см і 8 см"], ["x", "x+3", "40", "5", "8"], "Нехай менша сторона x, більша x+3. Тоді x(x+3)=40, звідси x²+3x-40=0. Додатний корінь x=5, отже сторони 5 і 8 см."),
        _solution("Знайди два послідовні натуральні числа, добуток яких дорівнює 72.", "8 і 9", ["8 і 9", "8;9", "9;8"], ["x", "x+1", "72", "8", "9"], "Нехай числа x і x+1. Маємо x(x+1)=72, тобто x²+x-72=0. Натуральний корінь x=8, тому числа 8 і 9."),
    ],
    2: [
        _choice("Лінійне рівняння має вигляд:", ["ax + b = 0", "ax² + bx + c = 0", "a/x = 0", "x³ + 1 = 0"], "ax + b = 0", "У лінійному рівнянні змінна має перший степінь."),
        _choice("Що треба зробити першим у 3x + 5 = 17?", ["відняти 5 від обох частин", "поділити на 17", "додати 5", "помножити на 3"], "відняти 5 від обох частин", "Спочатку переносимо вільний член, виконуючи однакову дію з обома частинами."),
        _choice("Розв’язок рівняння 4x = 20:", ["x = 4", "x = 5", "x = 16", "x = 24"], "x = 5", "Ділимо обидві частини на 4."),
        _choice("Рівняння 0x = 7 має:", ["один корінь", "безліч коренів", "жодного кореня", "корінь 0"], "жодного кореня", "Ліва частина завжди дорівнює 0, тому рівність 0 = 7 неможлива."),
        _short("Розв’яжи 5x = 35.", "7", ["7", "x=7"], "x = 35/5 = 7."),
        _short("Розв’яжи x - 9 = 4.", "13", ["13", "x=13"], "Додаємо 9 до обох частин: x = 13."),
        _short("Розв’яжи 2x + 6 = 18.", "6", ["6", "x=6"], "2x = 12, тому x = 6."),
        _short("Розв’яжи 7 - x = 2.", "5", ["5", "x=5"], "-x = -5, тому x = 5."),
        _solution("Розв’яжи 4(x - 2) = 20.", "x = 7", ["7", "x=7"], ["4x", "8", "28", "7"], "Розкриваємо дужки: 4x - 8 = 20. Додаємо 8: 4x = 28. Отже x = 7."),
        _solution("Розв’яжи 3(2x + 1) - 5 = 16.", "x = 3", ["3", "x=3"], ["6x", "3", "2", "18"], "6x + 3 - 5 = 16, звідси 6x - 2 = 16, 6x = 18, x = 3."),
        _solution("За 4 однакові зошити заплатили 76 грн. Скільки коштує один зошит? Склади рівняння.", "19 грн", ["19", "19 грн", "x=19"], ["4x", "76", "19"], "Нехай x — ціна одного зошита. 4x = 76, тому x = 19 грн."),
        _solution("Після знижки 20 грн товар коштує 135 грн. Якою була початкова ціна?", "155 грн", ["155", "155 грн", "x=155"], ["x-20", "135", "155"], "Нехай x — початкова ціна. x - 20 = 135, тому x = 155 грн."),
    ],
    3: [
        _choice("Графік функції y = 2x + 1 є:", ["прямою", "параболою", "колом", "гіперболою"], "прямою", "Лінійна функція y = kx + b задає пряму."),
        _choice("У функції y = 3x - 4 число 3 це:", ["кутовий коефіцієнт", "нуль функції", "вільний член", "область визначення"], "кутовий коефіцієнт", "Коефіцієнт k показує нахил прямої."),
        _choice("Нуль функції це значення x, при якому:", ["y = 0", "x = 0", "y = 1", "графік не існує"], "y = 0", "Щоб знайти нуль функції, прирівнюємо y до нуля."),
        _choice("Точка (2; 5) означає:", ["x=2, y=5", "x=5, y=2", "x=2, y=2", "y=5 завжди"], "x=2, y=5", "Перша координата — x, друга — y."),
        _short("Обчисли y, якщо y = 2x + 3 і x = 4.", "11", ["11", "y=11"], "y = 2·4 + 3 = 11."),
        _short("Знайди нуль функції y = x - 7.", "7", ["7", "x=7"], "0 = x - 7, тому x = 7."),
        _short("Чому дорівнює y у точці x=0 для y=5x-2?", "-2", ["-2", "y=-2"], "Підставляємо x=0: y=-2."),
        _short("Чи належить точка (3;7) графіку y=2x+1?", "так", ["так", "yes"], "2·3+1=7, тому точка належить графіку."),
        _solution("Знайди нуль функції y = 3x - 12.", "x = 4", ["4", "x=4"], ["0", "3x", "12", "4"], "Прирівнюємо y до нуля: 3x - 12 = 0, 3x = 12, x = 4."),
        _solution("Знайди значення функції y = -2x + 5 при x = -3.", "11", ["11", "y=11"], ["-2", "-3", "6", "11"], "y = -2·(-3)+5 = 6+5 = 11."),
        _solution("Пряма проходить через точки (0;2) і (2;6). Знайди її кутовий коефіцієнт.", "2", ["2", "k=2"], ["6-2", "2-0", "4", "2"], "k=(6-2)/(2-0)=4/2=2."),
        _solution("Таксі бере 50 грн за посадку і 12 грн за кожен кілометр. Запиши функцію вартості та знайди ціну поїздки на 8 км.", "y = 12x + 50; 146 грн", ["146", "146 грн", "12x+50", "y=12x+50"], ["12x", "50", "8", "146"], "Функція: y=12x+50. Для 8 км: y=12·8+50=146 грн."),
    ],
}


def _generic_quiz(subject: str, lesson: dict[str, Any]) -> list[dict[str, Any]]:
    title = lesson["title"]
    theory = lesson["theory"]
    goal = lesson["goal"]
    return [
        _choice(f"Яка тема цього уроку?", [title, "Інша тема", "Повторення без теми", "Лише тест"], title, f"Урок присвячений темі «{title}»."),
        _choice("Що варто зробити перед тестом?", ["Розібрати пояснення і приклад", "Вгадувати", "Пропустити урок", "Не читати умову"], "Розібрати пояснення і приклад", "Тест краще проходити після пояснення та одного повного прикладу."),
        _choice("Що допомагає уникати помилок?", ["Читати умову до кінця", "Поспішати", "Пропускати кроки", "Відповідати навмання"], "Читати умову до кінця", "Уважне читання умови часто рятує від технічних помилок."),
        _choice("Коли варто переходити далі?", ["Після впевненого розуміння теми", "Одразу", "Без тесту", "Після випадкової відповіді"], "Після впевненого розуміння теми", "Наступний урок відкривається після успішного тесту."),
        _short("Напиши ключове слово або поняття з теми уроку.", title, [title], f"Ключова тема уроку: {title}."),
        _short("Сформулюй мету уроку одним коротким реченням.", goal, [goal], goal),
        _short("Напиши один факт, який запам’ятав із пояснення.", theory, [theory], theory),
        _short("Що ти перевіриш перед відповіддю?", "умову", ["умову", "умова", "прочитаю умову"], "Перед відповіддю варто ще раз перевірити умову."),
        _solution("Поясни тему своїми словами у 2–3 реченнях.", theory, [theory], [title.lower()], theory),
        _solution("Наведи власний короткий приклад до теми.", lesson.get("example", "Приклад за темою"), [lesson.get("example", "")], [], lesson.get("example", theory)),
        _solution("Опиши типову помилку й спосіб її уникнути.", "Не поспішати й перевіряти кожен крок", ["не поспішати", "перевіряти"], ["помил", "перевір"], "Найкращий захист від помилок — не пропускати кроки й перевіряти відповідь."),
        _solution("Напиши короткий підсумок уроку та відповідь, чи готовий перейти далі.", goal, [goal], ["готов"], goal),
    ]


def get_quiz(subject: str, lesson: dict[str, Any]) -> list[dict[str, Any]]:
    if subject == "math" and lesson["id"] in MATH_QUIZZES:
        questions = MATH_QUIZZES[lesson["id"]]
    else:
        questions = _generic_quiz(subject, lesson)

    prepared: list[dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        item = dict(question)
        item["id"] = f"q{index}"
        item["number"] = index
        item["stage"] = 1 if index <= 4 else 2 if index <= 8 else 3
        item["stage_name"] = {1: "База", 2: "Практика", 3: "Задачі"}[item["stage"]]
        prepared.append(item)
    return prepared


def grade_question(question: dict[str, Any], user_answer: str | None) -> tuple[int, bool, str]:
    normalized = normalize_answer(user_answer)
    accepted = [normalize_answer(value) for value in question.get("accepted", []) if value]
    correct = normalize_answer(question.get("answer"))

    if not normalized:
        return 0, False, "Відповіді немає. Повернись до умови й спробуй записати хоча б перший крок."

    is_exact = normalized == correct or normalized in accepted
    if question["type"] in {"choice", "short"}:
        return (question["points"], True, question["explanation"]) if is_exact else (0, False, question["explanation"])

    if is_exact:
        return question["points"], True, question["explanation"]

    keywords = [normalize_answer(word) for word in question.get("keywords", []) if word]
    matched = sum(1 for word in keywords if word and word in normalized)
    if keywords and matched >= max(2, len(keywords) // 2):
        partial = max(1, question["points"] - 1)
        return partial, False, "Хід думок близький до правильного, але відповідь або один із кроків треба уточнити. " + question["explanation"]

    return 0, False, question["explanation"]


def lesson_breakdown(subject: str, lesson: dict[str, Any]) -> dict[str, Any]:
    if subject == "math" and lesson["id"] == 1:
        return {
            "intro": "Квадратні рівняння здаються великими лише до того моменту, поки не звикнеш до одного порядку дій.",
            "steps": [
                {"title": "1. Знайди коефіцієнти", "text": "У рівнянні x² - 5x + 6 = 0 маємо a = 1, b = -5, c = 6. Знак біля b не губимо."},
                {"title": "2. Обчисли дискримінант", "text": "D = b² - 4ac = (-5)² - 4·1·6 = 25 - 24 = 1."},
                {"title": "3. Знайди корені", "text": "x = (-b ± √D)/(2a). Тому x = (5 ± 1)/2. Отримуємо x₁ = 2, x₂ = 3."},
                {"title": "4. Перевір", "text": "2² - 5·2 + 6 = 0 і 3² - 5·3 + 6 = 0. Обидва корені підходять."},
            ],
            "mistake": "Найчастіше губиться мінус у b. Тут b = -5, а не 5.",
            "conclusion": "Порядок завжди один: a, b, c → D → корені → перевірка.",
        }
    return {
        "intro": lesson["theory"],
        "steps": [
            {"title": "1. Прочитай умову", "text": "Визнач, що саме треба знайти й які дані вже відомі."},
            {"title": "2. Застосуй правило", "text": lesson["theory"]},
            {"title": "3. Розбери приклад", "text": lesson["example"]},
            {"title": "4. Перевір себе", "text": "Спробуй пояснити розв’язання своїми словами без підказки."},
        ],
        "mistake": "Не перескакуй через кроки. Найчастіше помилка з’являється саме там, де учень поспішає.",
        "conclusion": lesson["goal"],
    }
