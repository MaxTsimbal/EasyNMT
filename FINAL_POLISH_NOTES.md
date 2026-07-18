# EasyNMT v0.9.9.9 Final Polish

У цій збірці виконано фінальний UX-пакет перед початком розробки v1.0 Beta.

## Основні зміни

1. Welcome Screen: кнопка «Почнемо» піднята вище на ПК і телефоні.
2. Loading Experience: додано фірмову космічну заставку з роботом Easy. Вона працює не тільки під час першого завантаження, а й між сторінками.
3. Focus Mode на уроках: у верхньому меню залишається лише «Кабінет».
4. Профіль і меню: службові посилання та вихід перенесено туди, де користувач очікує їх знайти.
5. Easy під час уроку: додано боковий чат із контекстом теми уроку.
6. Пояснення на аркуші: функція отримала більшу та помітнішу кнопку.
7. Mobile Sidebar: меню більше не повинно відкриватися самостійно після переходів або повернення з кешу браузера.

## Перевірка після заміни файлів

- Відкрити Welcome Screen на ПК та телефоні.
- Натиснути «Почнемо» й перевірити нову заставку переходу.
- Відкрити урок і натиснути кнопку Easy справа внизу.
- Надіслати одне тестове запитання.
- На телефоні кілька разів перейти між «Огляд», «Сьогодні», «Уроки» та «Профіль» і переконатися, що бокове меню залишається закритим.


## Final mobile clarity hotfix
- Loader mascot and text no longer use animated sub-pixel scaling on phones.
- Lesson header is fixed to the very top of the app viewport.
- Easy lesson chat composer stays visible above iOS browser chrome and mobile navigation.
- Notebook previous/next controls moved below the paper explanation.
- Dashboard Easy launcher pseudo-elements removed to prevent an empty oval.
- Mobile drawer is force-closed after page restore and visibility changes.
