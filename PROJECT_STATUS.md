# EasyNMT Project Status

Version: v0.9.8 Stable

## Готово
- Responsive Cosmic Tutor UI
- Стабільний Dashboard
- Мобільне off-canvas меню
- Постійна Liquid Glass кнопка чату
- OpenAI Responses API інтеграція в `ai_service.py`
- Demo fallback без API-ключа

## Для ввімкнення OpenAI
Додати в Railway Variables: `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_DAILY_LIMIT`.

## Learning Engine v0.9.8

Готово:
- послідовне відкриття уроків;
- тест 12 питань (4 + 4 + 4);
- письмові відповіді для питань 5–12;
- оцінювання 24 бали, прохід 18;
- детальний розбір одного прикладу;
- детальний розбір відповідей після тесту;
- fallback-режим без OpenAI API.

OpenAI буде підключено як інтелектуальний двигун для персоналізації пояснень, генерації завдань і семантичної перевірки письмових відповідей. Остаточне відкриття уроків лишається під контролем Flask.
