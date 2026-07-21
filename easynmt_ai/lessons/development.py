"""Validator-backed deterministic lesson baselines for provider recovery."""
from __future__ import annotations

from typing import Any

from ..curriculum.taxonomy import load_taxonomy
from ..subjects import get_subject
from .models import LessonGenerationRequest


def deterministic_lesson_proposal(
    request: LessonGenerationRequest,
) -> dict[str, Any] | None:
    """Return reviewed or metadata-grounded structured lesson content."""

    if request.topic_id != "math.numbers.integers":
        return _subject_lesson_proposal(request)
    remaining_competencies = list(range(2, len(request.competencies) + 1)) or [1]
    return {
        "objective_overview": (
            "Навчитися впевнено порівнювати цілі числа, виконувати дії з різними "
            "знаками та перевіряти результат оцінкою і зворотною дією."
        ),
        "nmt_relevance": (
            "На НМТ цілі числа з’являються в коротких обчисленнях, виразах, "
            "координатах і текстових задачах, де помилка зі знаком одразу змінює відповідь."
        ),
        "nmt_task_types": [
            "обчислення значення числового виразу",
            "вибір правильної відповіді після перевірки знака",
        ],
        "prerequisite_reminder": {
            "needed": False,
            "explanation": "",
            "points": [],
        },
        "concepts": [
            {
                "id": "concept-number-line",
                "title": "Знак, модуль і положення на числовій прямій",
                "what": (
                    "Ціле число описується знаком і відстанню від нуля; модуль показує "
                    "цю відстань без урахування напрямку."
                ),
                "why": (
                    "Числова пряма пояснює порівняння від’ємних чисел і допомагає не "
                    "плутати більше число з більшим модулем."
                ),
                "how": (
                    "Познач нуль, визнач напрямок знака, порівняй положення чисел, а "
                    "модуль використовуй лише як відстань, а не як готову відповідь."
                ),
                "when_used": (
                    "Застосовуй перед порівнянням, додаванням чисел різних знаків і "
                    "під час роботи з координатами."
                ),
                "nmt_use": (
                    "На НМТ це дає швидку перевірку знака результату ще до точного обчислення."
                ),
                "common_confusion": (
                    "Не плутай модуль числа з самим числом: модуль −8 дорівнює 8, але −8 менше за 0."
                ),
                "competency_indices": [1],
            },
            {
                "id": "concept-sign-rules",
                "title": "Правила знаків і порядок арифметичних дій",
                "what": (
                    "Правила знаків визначають напрям результату, а порядок дій указує, "
                    "яке множення, ділення, додавання чи віднімання виконати першим."
                ),
                "why": (
                    "Окремий контроль знака й модуля зменшує кількість механічних помилок у виразах."
                ),
                "how": (
                    "Спочатку виконай дії в дужках, потім множення і ділення, далі "
                    "додавання та віднімання; для кожної дії окремо визнач знак результату."
                ),
                "when_used": (
                    "Використовуй у кожному виразі з кількома діями або двома сусідніми знаками."
                ),
                "nmt_use": (
                    "На НМТ цей алгоритм допомагає відкидати варіанти з неправильним знаком без повторного розв’язання."
                ),
                "common_confusion": (
                    "Вираз a − (−b) означає додавання b, але два мінуси не можна скорочувати поза конкретною дією."
                ),
                "competency_indices": remaining_competencies,
            },
        ],
        "worked_examples": [
            {
                "id": "example-foundation",
                "difficulty": "foundation",
                "problem": "Обчисли: −7 + 12.",
                "reasoning": (
                    "Числа мають різні знаки, тому від більшого модуля віднімаємо менший "
                    "і залишаємо знак числа з більшим модулем."
                ),
                "concept_ids": ["concept-number-line"],
                "steps": [
                    {
                        "order": 1,
                        "work": "|12| − |−7| = 12 − 7 = 5",
                        "explanation": "Порівнюємо модулі та знаходимо їхню різницю як відстань між числами.",
                    },
                    {
                        "order": 2,
                        "work": "−7 + 12 = 5",
                        "explanation": "Модуль 12 більший, тому результат отримує додатний знак.",
                    },
                ],
                "final_answer": "5",
                "verification": "На числовій прямій сім кроків ліворуч і дванадцять праворуч приводять у точку 5.",
            },
            {
                "id": "example-guided",
                "difficulty": "guided",
                "problem": "Обчисли значення виразу: 18 − (−7) · 2.",
                "reasoning": (
                    "Спочатку виконуємо множення, уважно визначаємо його знак, а потім "
                    "віднімання від’ємного числа замінюємо додаванням."
                ),
                "concept_ids": ["concept-sign-rules"],
                "steps": [
                    {
                        "order": 1,
                        "work": "(−7) · 2 = −14",
                        "explanation": "Добуток чисел із різними знаками є від’ємним, а модулі дають чотирнадцять.",
                    },
                    {
                        "order": 2,
                        "work": "18 − (−14) = 18 + 14 = 32",
                        "explanation": "Віднімання від’ємного числа рівносильне додаванню відповідного додатного числа.",
                    },
                ],
                "final_answer": "32",
                "verification": "Результат має бути більшим за 18, бо від 18 віднімають від’ємне число; 32 відповідає оцінці.",
            },
            {
                "id": "example-exam",
                "difficulty": "exam",
                "problem": (
                    "Температура була −3 °C, підвищилася на 11 °C, а потім знизилася на 5 °C. Якою вона стала?"
                ),
                "reasoning": (
                    "Перекладаємо послідовні зміни у вираз із цілими числами, виконуємо "
                    "дії зліва направо та перевіряємо напрям кожної зміни."
                ),
                "concept_ids": ["concept-number-line", "concept-sign-rules"],
                "steps": [
                    {
                        "order": 1,
                        "work": "−3 + 11 = 8",
                        "explanation": "Підвищення температури означає рух на одинадцять одиниць праворуч від мінус трьох.",
                    },
                    {
                        "order": 2,
                        "work": "8 − 5 = 3",
                        "explanation": "Зниження на п’ять градусів означає віднімання п’яти від проміжного результату.",
                    },
                ],
                "final_answer": "3 °C",
                "verification": "Загальна зміна дорівнює +6 °C, тому −3 °C + 6 °C = 3 °C.",
            },
        ],
        "common_mistakes": [
            {
                "id": "mistake-negative-order",
                "incorrect_reasoning": "Учень вважає, що −9 більше за −4, тому що модуль дев’яти більший.",
                "why_incorrect": "Серед від’ємних чисел правіше розташоване число з меншим модулем, тому −4 більше за −9.",
                "recognition": "Помилка помітна, коли порівняння модулів механічно переноситься на самі від’ємні числа.",
                "correction": "Познач обидва числа на числовій прямій і вибери те, що розташоване правіше.",
                "prevention": "Перед порівнянням від’ємних чисел окремо назви їхній знак і лише потім аналізуй модулі.",
                "concept_ids": ["concept-number-line"],
            },
            {
                "id": "mistake-double-minus",
                "incorrect_reasoning": "Учень обчислює 6 − (−2) як 6 − 2 і отримує чотири.",
                "why_incorrect": "Віднімання від’ємного числа змінює напрям на числовій прямій і перетворюється на додавання.",
                "recognition": "Результат безпідставно стає меншим, хоча віднімання від’ємного числа повинно його збільшити.",
                "correction": "Перепиши дію окремим кроком: 6 − (−2) = 6 + 2 = 8.",
                "prevention": "Не пропускай проміжний запис заміни двох сусідніх мінусів на операцію додавання.",
                "concept_ids": ["concept-sign-rules"],
            },
            {
                "id": "mistake-operation-order",
                "incorrect_reasoning": "Учень у виразі 5 + 3 · (−2) спочатку додає п’ять і три.",
                "why_incorrect": "Множення має вищий пріоритет за додавання, якщо порядок не змінено дужками.",
                "recognition": "Перший запис розв’язання виконує додавання поза дужками до множення.",
                "correction": "Спочатку обчисли 3 · (−2) = −6, а потім 5 + (−6) = −1.",
                "prevention": "Перед обчисленням підкресли множення й ділення та виконай їх раніше за додавання і віднімання.",
                "concept_ids": ["concept-sign-rules"],
            },
        ],
        "practical_tips": [
            {
                "id": "tip-estimate-sign",
                "advice": "Визнач очікуваний знак відповіді до точного обчислення.",
                "use_when": "Коли у виразі є від’ємні числа або кілька сусідніх знаків.",
                "recognition_pattern": "Знак можна передбачити за напрямом зміни або правилами множення.",
            },
            {
                "id": "tip-separate-sign-module",
                "advice": "Обчислюй модуль і визначай знак як два окремі короткі кроки.",
                "use_when": "Коли додаєш числа різних знаків або множиш кілька множників.",
                "recognition_pattern": "Помилка найчастіше виникає не в модулі, а саме у виборі знака.",
            },
            {
                "id": "tip-number-line",
                "advice": "Для сумнівного результату зроби швидку перевірку на числовій прямій.",
                "use_when": "Коли порівнюєш від’ємні числа або додаєш число невеликого модуля.",
                "recognition_pattern": "Кожне додавання задає напрям і кількість кроків від початкового числа.",
            },
        ],
        "guided_practice": [
            {
                "id": "practice-foundation",
                "difficulty": "foundation",
                "prompt": "Порівняй числа −6 і −2 та коротко поясни вибір.",
                "hint": "Уяви обидва числа на числовій прямій і знайди те, що розташоване правіше.",
                "solution_steps": [
                    "На числовій прямій число −2 розташоване правіше за −6.",
                    "Число, розташоване правіше, є більшим, тому −2 > −6.",
                ],
                "expected_answer": "−2 > −6",
                "explanation": "Серед від’ємних чисел більшим є число з меншим модулем, бо воно ближче до нуля.",
                "concept_ids": ["concept-number-line"],
            },
            {
                "id": "practice-guided",
                "difficulty": "guided",
                "prompt": "Обчисли значення виразу: −15 + 8 − (−4).",
                "hint": "Спочатку заміни віднімання від’ємного числа додаванням, а потім працюй зі знаками.",
                "solution_steps": [
                    "Переписуємо вираз: −15 + 8 + 4.",
                    "Обчислюємо зліва направо: −15 + 8 = −7, а −7 + 4 = −3.",
                ],
                "expected_answer": "−3",
                "explanation": "Ключовий крок полягає в правильній заміні подвійного мінуса та окремому контролі знака результату.",
                "concept_ids": ["concept-number-line", "concept-sign-rules"],
            },
            {
                "id": "practice-exam",
                "difficulty": "exam",
                "prompt": "На рахунку було −120 грн. Після поповнення на 200 грн списали ще 35 грн. Який баланс залишився?",
                "hint": "Запиши всі зміни одним виразом і перед обчисленням оціни, чи відповідь має бути додатною.",
                "solution_steps": [
                    "Складаємо вираз за змінами балансу: −120 + 200 − 35.",
                    "Отримуємо 80 − 35 = 45, а оцінка підтверджує додатний результат.",
                ],
                "expected_answer": "45 грн",
                "explanation": "Послідовне додавання змін зберігає їхній напрям, а попередня оцінка знака допомагає виявити помилку.",
                "concept_ids": ["concept-number-line", "concept-sign-rules"],
            },
        ],
        "recap": {
            "main_ideas": [
                "Правіше число на числовій прямій завжди більше.",
                "Знак результату й обчислення його модуля варто контролювати окремо.",
            ],
            "formulas": ["a − (−b) = a + b"],
            "warnings": [
                "Більший модуль від’ємного числа не робить саме число більшим.",
                "Множення і ділення виконуються раніше за додавання та віднімання.",
            ],
            "recognition_patterns": [
                "Два сусідні мінуси виникають під час віднімання від’ємного числа.",
                "Різні знаки доданків вимагають порівняння їхніх модулів.",
            ],
            "can_solve": [
                "Порівняти цілі числа та пояснити відповідь числовою прямою.",
                "Обчислити вираз із кількома діями та незалежно перевірити його знак.",
            ],
        },
        "assessment_transition": {
            "message": (
                "Далі перевірка вимагатиме визначити знак, дотриматися порядку дій "
                "і коротко обґрунтувати результат без використання нових правил."
            ),
            "readiness_checklist": [
                "Я правильно порівнюю додатні й від’ємні цілі числа.",
                "Я окремо визначаю знак і модуль результату.",
                "Я дотримуюся порядку арифметичних дій.",
                "Я перевіряю відповідь оцінкою або числовою прямою.",
            ],
        },
        "assessment_blueprint": {
            "covered_concept_ids": ["concept-number-line", "concept-sign-rules"],
            "question_patterns": [
                "порівняти два від’ємні цілі числа",
                "обчислити суму чисел із різними знаками",
                "застосувати правило віднімання від’ємного числа",
                "обчислити вираз із правильним порядком дій",
            ],
            "required_reasoning": [
                "пояснення вибору знака результату",
                "незалежна перевірка оцінкою або числовою прямою",
            ],
            "excluded_content": [
                "раціональні числа та інші поняття поза поточним уроком"
            ],
        },
    }


# Compatibility alias for Task 3B callers. New code uses the production name.
development_lesson_proposal = deterministic_lesson_proposal


def _seed(values: tuple[str, ...], index: int, fallback: str) -> str:
    return values[index] if index < len(values) else fallback


def _subject_lesson_proposal(
    request: LessonGenerationRequest,
) -> dict[str, Any] | None:
    """Build a validator-backed local lesson from authoritative topic metadata.

    This fallback intentionally teaches the curriculum metadata rather than
    pretending to possess provider-only detail.  Its examples and diagnostic
    language vary by subject and incorporate subject-owned topic seeds.
    """

    try:
        subject = get_subject(request.subject)
        taxonomy_topic = load_taxonomy(request.subject).topic(request.topic_id)
    except (KeyError, OSError, ValueError):
        return None
    if not request.topic_id.startswith(f"{subject.curriculum_namespace}."):
        return None
    # A deterministic fallback may only expand application-owned taxonomy
    # metadata.  Reject caller-invented or stale identity fields instead of
    # fabricating a plausible-looking lesson for the wrong topic.
    if (
        request.title != taxonomy_topic.title_uk
        or request.description != taxonomy_topic.description_uk
        or request.objectives != taxonomy_topic.learning_objectives
        or request.competencies != taxonomy_topic.competencies
    ):
        return None

    vocabulary = request.topic_vocabulary or (
        request.title,
        request.competencies[0],
    )
    vocabulary_text = ", ".join(vocabulary[:6])
    objective = request.objectives[0]
    second_objective = (
        request.objectives[1]
        if len(request.objectives) > 1
        else f"Застосовувати тему «{request.title}» у типовому завданні НМТ."
    )
    second_indices = tuple(range(2, len(request.competencies) + 1)) or (1,)
    prerequisite_titles = [item.title for item in request.prerequisites]

    subject_copy = {
        "math": {
            "marker": "математичне обчислення, формула або логічна модель",
            "what": "математичне правило",
            "how": "Запиши дані, обери правило або формулу, виконай перетворення без пропусків і перевір результат незалежною дією.",
            "problem": "Розв’яжи математичне завдання",
            "evidence": "обчислення й перевірка",
            "formula": "умова → математична модель → обчислення → перевірка",
        },
        "ukrainian": {
            "marker": "мовна норма, слово й речення в українському контексті",
            "what": "мовне правило",
            "how": "Визнач мовну одиницю, назви норму, перевір контекст, зістав нормативний варіант із контрприкладом і поясни вибір.",
            "problem": "Проаналізуй слово або речення",
            "evidence": "мовне правило й контекст",
            "formula": "мовна одиниця → умова правила → нормативна форма → контекстна перевірка",
        },
        "history": {
            "marker": "історична подія, період, діяч, джерело та причинно-наслідковий зв’язок",
            "what": "історичний зв’язок",
            "how": "Установи період і територію, розташуй події в хронології, зістав діяча або джерело та сформулюй підтверджений наслідок.",
            "problem": "Виконай історичне завдання",
            "evidence": "хронологія й історичне джерело",
            "formula": "період → подія → діяч або джерело → причина → наслідок",
        },
        "english": {
            "marker": "English grammar, vocabulary, sentence context and reading evidence",
            "what": "English language pattern",
            "how": "Read the whole sentence, identify the grammar or vocabulary cue, choose the natural English form and verify it against the wider context.",
            "problem": "Complete an English language task",
            "evidence": "grammar cue, vocabulary and reading context",
            "formula": "context → language cue → English form → meaning check",
        },
    }[request.subject]

    concepts = [
        {
            "id": "concept-foundation",
            "title": f"Основа теми: {request.title}",
            "what": (
                f"Цей блок пояснює {subject_copy['what']} для теми «{request.title}». "
                f"Ключова лексика: {vocabulary_text}. {request.description}"
            ),
            "why": (
                f"Основа потрібна, щоб розпізнати {subject_copy['marker']} і не "
                "обирати відповідь лише за зовнішньою схожістю."
            ),
            "how": subject_copy["how"],
            "when_used": (
                "Використовуй цей алгоритм одразу після читання умови та перед "
                "порівнянням запропонованих відповідей."
            ),
            "nmt_use": (
                f"У НМТ ця основа допомагає виконати завдання на {objective.casefold()}"
            ),
            "common_confusion": (
                "Типова плутанина виникає, коли учень помічає одну знайому ознаку, "
                "але не перевіряє решту умов і контекст."
            ),
            "competency_indices": [1],
        },
        {
            "id": "concept-application",
            "title": f"Застосування й перевірка: {request.title}",
            "what": (
                f"Застосування поєднує поняття {vocabulary_text} у послідовне "
                f"розв’язання; очікуваний результат — {second_objective.casefold()}"
            ),
            "why": (
                f"Поетапна перевірка через {subject_copy['evidence']} відсіює "
                "дистрактори, що відтворюють лише частину правильного міркування."
            ),
            "how": (
                f"Працюй за схемою «{subject_copy['formula']}», після кожного кроку "
                "зіставляй проміжний висновок з умовою й не додавай непідтверджених даних."
            ),
            "when_used": (
                "Застосовуй для повного прикладу, завдання з кількома ознаками та "
                "фінальної перевірки перед вибором відповіді."
            ),
            "nmt_use": (
                "На НМТ цей контроль особливо корисний, коли кілька варіантів "
                "виглядають правдоподібно, але лише один відповідає всім умовам."
            ),
            "common_confusion": (
                "Не замінюй перевірку повторенням першої думки: використай іншу "
                "ознаку, контекст, джерело або зворотну дію."
            ),
            "competency_indices": list(second_indices),
        },
    ]

    example_fallbacks = (
        f"{subject_copy['problem']} на розпізнавання основної ознаки теми «{request.title}».",
        f"{subject_copy['problem']} з двома пов’язаними ознаками: {vocabulary_text}.",
        f"{subject_copy['problem']} у форматі НМТ із правдоподібними дистракторами.",
    )
    difficulties = ("foundation", "guided", "exam")
    worked_examples = []
    for index, difficulty in enumerate(difficulties):
        seed = _seed(request.example_seeds, index, example_fallbacks[index])
        worked_examples.append({
            "id": f"example-{difficulty}",
            "difficulty": difficulty,
            "problem": f"{seed}. Тема: {request.title}.",
            "reasoning": (
                f"Спочатку визначаємо, яку ознаку теми перевіряє завдання, і "
                f"співвідносимо її з поняттями {vocabulary_text}; потім плануємо перевірку."
            ),
            "concept_ids": [
                "concept-foundation"
                if index == 0
                else "concept-application"
            ],
            "steps": [
                {
                    "order": 1,
                    "work": f"Виділено умову та ключові поняття: {vocabulary_text}.",
                    "explanation": (
                        "Цей крок відокремлює дані завдання від схожих, але "
                        "непотрібних відомостей або дистракторів."
                    ),
                },
                {
                    "order": 2,
                    "work": f"Застосовано схему: {subject_copy['formula']}.",
                    "explanation": (
                        "Послідовна схема дає обґрунтований результат і показує, "
                        "яку саме умову підтверджено на кожному етапі."
                    ),
                },
            ],
            "final_answer": (
                "Обрано варіант, що відповідає всім визначеним ознакам поточної теми."
            ),
            "verification": (
                f"Відповідь повторно перевірено через {subject_copy['evidence']}; "
                "вона не потребує фактів або правил поза уроком."
            ),
        })
    worked_examples[-1]["concept_ids"] = ["concept-foundation", "concept-application"]

    mistake_fallbacks = (
        "учень визначає відповідь за одним знайомим словом і не читає повну умову",
        "учень пропускає проміжний крок та не може пояснити отриманий висновок",
        "учень перевіряє відповідь тим самим способом і не помічає первинної помилки",
    )
    common_mistakes = []
    for index in range(3):
        seed = _seed(request.common_mistake_seeds, index, mistake_fallbacks[index])
        common_mistakes.append({
            "id": f"mistake-{index + 1}",
            "incorrect_reasoning": f"Помилковий підхід: {seed}.",
            "why_incorrect": (
                f"Такий підхід не перевіряє всі поняття {vocabulary_text} та може "
                "підтвердити дистрактор замість правильної відповіді."
            ),
            "recognition": (
                "Помилку видно, коли в поясненні немає посилання на конкретну "
                "умову, правило, контекст або незалежний доказ."
            ),
            "correction": (
                f"Повернися до схеми «{subject_copy['formula']}» і запиши "
                "пропущений зв’язок окремим кроком."
            ),
            "prevention": (
                "Перед остаточною відповіддю назви дві різні ознаки, які її "
                "підтверджують, і одну ознаку, що відкидає найближчий дистрактор."
            ),
            "concept_ids": ["concept-foundation", "concept-application"],
        })

    return {
        "objective_overview": (
            f"Мета уроку — {objective.casefold()} Після пояснення учень зможе "
            f"використати поняття {vocabulary_text} у контрольованій послідовності."
        ),
        "nmt_relevance": (
            f"Для НМТ тема «{request.title}» важлива, бо перевіряє не механічне "
            f"впізнавання, а {subject_copy['marker']}. Завдання вимагає обрати "
            "відповідь, підтверджену правилом, контекстом і самоперевіркою."
        ),
        "nmt_task_types": [
            f"розпізнати ключову ознаку теми «{request.title}»",
            f"застосувати {subject_copy['evidence']} для відкидання дистрактора",
        ],
        "prerequisite_reminder": {
            "needed": bool(prerequisite_titles),
            "explanation": (
                "Перед уроком віднови тільки потрібні попередні теми: "
                + ", ".join(prerequisite_titles)
                + ". Вони дають поняття для першого кроку поточного алгоритму."
                if prerequisite_titles
                else ""
            ),
            "points": (
                [
                    f"Пригадай основну ознаку теми «{prerequisite_titles[0]}».",
                    "Перевір, як попереднє поняття використовується в першому кроці нового завдання.",
                ]
                if prerequisite_titles
                else []
            ),
        },
        "concepts": concepts,
        "worked_examples": worked_examples,
        "common_mistakes": common_mistakes,
        "practical_tips": [
            {
                "id": "tip-read-condition",
                "advice": "Спочатку назви, яку саме ознаку перевіряє умова.",
                "use_when": "Перед переглядом варіантів відповіді в завданні НМТ.",
                "recognition_pattern": "Ключові слова умови вказують на правило, контекст або потрібний тип доказу.",
            },
            {
                "id": "tip-eliminate",
                "advice": "Відкидай дистрактор конкретною суперечною ознакою.",
                "use_when": "Коли два варіанти виглядають близькими або частково правильними.",
                "recognition_pattern": "Неправильний варіант порушує хоча б одну умову поточної теми.",
            },
            {
                "id": "tip-verify",
                "advice": f"Перевір відповідь через {subject_copy['evidence']} іншим способом.",
                "use_when": "Після отримання відповіді та перед остаточним вибором у тесті.",
                "recognition_pattern": "Незалежна перевірка підтверджує той самий висновок без повторення первинної помилки.",
            },
        ],
        "guided_practice": [
            {
                "id": "practice-foundation",
                "difficulty": "foundation",
                "prompt": f"Сформулюй власними словами основну ознаку теми «{request.title}» і назви одне ключове поняття.",
                "hint": f"Спирайся на поняття {vocabulary[0]} та поясни не лише назву, а й його роль у темі.",
                "solution_steps": [
                    f"Названо ключове поняття {vocabulary[0]} та його зміст у межах поточної теми.",
                    "Пояснено, яку ознаку або зв’язок це поняття допомагає розпізнати в завданні.",
                ],
                "expected_answer": f"Відповідь має точно пояснювати поняття {vocabulary[0]} і його роль у темі «{request.title}».",
                "explanation": "Правильна відповідь містить конкретну ознаку теми, а не лише повторює її назву.",
                "concept_ids": ["concept-foundation"],
            },
            {
                "id": "practice-guided",
                "difficulty": "guided",
                "prompt": f"Застосуй схему «{subject_copy['formula']}» до нового короткого прикладу з теми «{request.title}».",
                "hint": "Спочатку назви ознаку з умови, потім правило або контекст, який її підтверджує.",
                "solution_steps": [
                    "Виділено ключову ознаку й відкинуто відомості, які не впливають на висновок.",
                    f"Застосовано схему «{subject_copy['formula']}» і записано обґрунтований результат.",
                ],
                "expected_answer": "Послідовний висновок із посиланням на конкретну ознаку та правило поточної теми.",
                "explanation": "Зараховується лише відповідь, у якій видно зв’язок між умовою, правилом і висновком.",
                "concept_ids": ["concept-foundation", "concept-application"],
            },
            {
                "id": "practice-exam",
                "difficulty": "exam",
                "prompt": f"Поясни, як у завданні НМТ з теми «{request.title}» відкинути найближчий дистрактор і перевірити відповідь.",
                "hint": f"Знайди суперечну ознаку, а потім використай {subject_copy['evidence']} як незалежну перевірку.",
                "solution_steps": [
                    "Названо конкретну умову, якій дистрактор не відповідає.",
                    f"Остаточну відповідь повторно підтверджено через {subject_copy['evidence']} іншим способом.",
                ],
                "expected_answer": "Дистрактор відкинуто конкретною суперечністю, а правильний варіант підтверджено незалежною перевіркою.",
                "explanation": "Такий підхід перевіряє не впізнавання слова, а повний доказ відповідності відповіді умові.",
                "concept_ids": ["concept-foundation", "concept-application"],
            },
        ],
        "recap": {
            "main_ideas": [
                f"Тема «{request.title}» спирається на поняття {vocabulary_text}.",
                f"Результат має підтверджувати {subject_copy['evidence']}, а не лише знайоме формулювання.",
            ],
            "formulas": [subject_copy["formula"]],
            "warnings": [
                "Не обирай відповідь за одним словом або першою впізнаною ознакою.",
                "Не додавай до умови фактів чи правил, яких немає в поточному уроці.",
            ],
            "recognition_patterns": [
                "Умова називає ознаку, яку треба пов’язати з правилом або контекстом.",
                "Правильний варіант витримує основну й незалежну перевірку.",
            ],
            "can_solve": [
                f"Розпізнати базову ознаку теми «{request.title}».",
                "Пояснити вибір і відкинути дистрактор двома різними доказами.",
            ],
        },
        "assessment_transition": {
            "message": (
                f"Наступна перевірка охоплюватиме тільки тему «{request.title}», "
                "її ключові поняття та алгоритм самоперевірки без нового матеріалу."
            ),
            "readiness_checklist": [
                f"Я можу пояснити поняття {vocabulary[0]} власними словами.",
                "Я визначаю ознаку, яку перевіряє умова завдання.",
                "Я обґрунтовую кожний проміжний крок.",
                "Я перевіряю відповідь незалежним способом і відкидаю дистрактор.",
            ],
        },
        "assessment_blueprint": {
            "covered_concept_ids": ["concept-foundation", "concept-application"],
            "question_patterns": [
                "розпізнати ключову ознаку в короткій умові",
                "відновити пропущений крок алгоритму",
                "знайти й виправити типову помилку",
                "обрати відповідь та підтвердити її незалежною ознакою",
            ],
            "required_reasoning": [
                "посилання на конкретне правило або контекст",
                "незалежна перевірка та пояснення відкинутого дистрактора",
            ],
            "excluded_content": [
                "поняття наступних curriculum units і будь-які правила поза поточною темою"
            ],
        },
    }
