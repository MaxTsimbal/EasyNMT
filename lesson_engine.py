def get_worked_example(subject_key, lesson_id, lesson, details):
    """Return one human-written, step-by-step example for the lesson page."""
    examples = list(details.get('extra_examples') or [])
    fallback = examples[0] if examples else lesson.get('example', 'Розглянь приклад із теорії.')

    special = {
        ('math', 1): {
            'title': 'Розв’яжемо x² − 5x + 6 = 0',
            'intro': 'Тут зручно використати дискримінант. Не поспішай зі знаками: саме на них найчастіше гублять бал.',
            'steps': [
                {'title': 'Знаходимо коефіцієнти', 'text': 'a = 1, b = −5, c = 6. Знак біля числа входить у коефіцієнт.'},
                {'title': 'Обчислюємо дискримінант', 'text': 'D = b² − 4ac = (−5)² − 4 · 1 · 6 = 25 − 24 = 1.'},
                {'title': 'Підставляємо у формулу', 'text': 'x₁,₂ = (−b ± √D) / 2a = (5 ± 1) / 2.'},
                {'title': 'Отримуємо корені', 'text': 'x₁ = 3, x₂ = 2. Швидка перевірка: 3 · 2 = 6, а 3 + 2 = 5.'},
            ],
            'answer': 'Відповідь: 2 і 3.',
            'mistake': 'Типова помилка: записати b = 5 замість b = −5.'
        },
        ('english', 1): {
            'title': 'Обираємо Present Simple чи Present Continuous',
            'intro': 'Спочатку дивимося не на дієслово, а на ситуацію.',
            'steps': [
                {'title': 'Шукаємо підказку', 'text': 'Слово now показує, що дія відбувається просто зараз.'},
                {'title': 'Обираємо час', 'text': 'Для дії зараз потрібен Present Continuous.'},
                {'title': 'Будуємо форму', 'text': 'am / is / are + дієслово з -ing.'},
                {'title': 'Записуємо речення', 'text': 'She is reading now.'},
            ],
            'answer': 'Правильна форма: is reading.',
            'mistake': 'Типова помилка: пропустити is і написати лише reading.'
        },
    }

    if (subject_key, lesson_id) in special:
        return special[(subject_key, lesson_id)]

    return {
        'title': 'Розберімо один приклад до кінця',
        'intro': 'Спочатку визначимо, що саме перевіряє завдання, а потім пройдемо його без стрибків через кроки.',
        'steps': [
            {'title': 'Читаємо умову', 'text': lesson.get('goal', 'Визнач, що потрібно знайти або пояснити.')},
            {'title': 'Згадуємо правило', 'text': details.get('simple_explanation', lesson.get('theory', 'Використай правило з уроку.'))},
            {'title': 'Застосовуємо правило', 'text': fallback},
            {'title': 'Перевіряємо себе', 'text': 'Повернись до умови й переконайся, що відповідь справді відповідає запитанню.'},
        ],
        'answer': lesson.get('example', fallback),
        'mistake': (details.get('mistakes') or ['Не пропускай крок перевірки.'])[0],
    }
