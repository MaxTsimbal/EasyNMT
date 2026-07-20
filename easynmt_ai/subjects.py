"""Canonical subject definitions shared by AI, curriculum, and web layers.

Stored subject keys are public persistence identifiers.  They must never be
renamed in place; add a new key and an explicit migration when a future
product change requires a different identifier.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class LessonGenerationPolicy:
    """Subject-specific teaching policy consumed by the shared Lesson Engine."""

    system_role: str
    educational_tone: str
    terminology: tuple[str, ...]
    section_expectations: tuple[str, ...]
    example_style: str
    mistake_style: str
    nmt_relevance: str
    formatting_rules: tuple[str, ...]
    language_of_instruction: str = "uk"


@dataclass(frozen=True)
class LessonValidationProfile:
    """Local alignment rules applied after structural lesson validation."""

    topic_prefix: str
    positive_markers: tuple[str, ...]
    foreign_subject_markers: tuple[str, ...]
    minimum_positive_markers: int = 1


@dataclass(frozen=True)
class AssessmentProfile:
    """Reserved Task 3C contract; no assessment behavior is implemented here."""

    profile_key: str
    supported: bool = False


@dataclass(frozen=True)
class SubjectDefinition:
    """Stable product metadata for one learner-selectable subject."""

    key: str
    display_name: str
    curriculum_namespace: str
    icon: str
    description: str
    supported_language: str
    taxonomy_filename: str
    lesson_generation_policy: LessonGenerationPolicy
    validation_profile: LessonValidationProfile
    assessment_profile: AssessmentProfile
    active: bool = True

    @property
    def display_label(self) -> str:
        return f"{self.icon} {self.display_name}"

    def for_ui(self) -> dict[str, object]:
        return {
            "key": self.key,
            "name": self.display_name,
            "label": self.display_label,
            "icon": self.icon,
            "description": self.description,
            "active": self.active,
        }


def _policy(
    role: str,
    *,
    tone: str,
    terminology: tuple[str, ...],
    expectations: tuple[str, ...],
    examples: str,
    mistakes: str,
    nmt: str,
    formatting: tuple[str, ...],
) -> LessonGenerationPolicy:
    return LessonGenerationPolicy(
        system_role=role,
        educational_tone=tone,
        terminology=terminology,
        section_expectations=expectations,
        example_style=examples,
        mistake_style=mistakes,
        nmt_relevance=nmt,
        formatting_rules=formatting,
    )


_SUBJECTS = {
    "math": SubjectDefinition(
        key="math",
        display_name="Математика",
        curriculum_namespace="math",
        icon="📐",
        description="Формули, задачі, логіка",
        supported_language="uk",
        taxonomy_filename="math_v1.json",
        lesson_generation_policy=_policy(
            "досвідчений викладач математики для підготовки до НМТ",
            tone="точний, покроковий і спокійний",
            terminology=("умова", "алгоритм", "обчислення", "перевірка", "відповідь"),
            expectations=(
                "пояснювати значення формул і кожне перетворення",
                "перевіряти область допустимих значень та одиниці вимірювання",
            ),
            examples="від базового обчислення до типової прикладної задачі НМТ",
            mistakes="показувати помилки у знаках, формулах, порядку дій та перевірці",
            nmt="пов'язувати матеріал із форматами математичного блоку НМТ",
            formatting=("записувати формули однозначно", "не пропускати проміжні кроки"),
        ),
        validation_profile=LessonValidationProfile(
            topic_prefix="math.",
            positive_markers=("обчис", "формул", "рівня", "числ", "граф", "геометр", "ймовір"),
            foreign_subject_markers=("орфографічне правило", "історичне джерело", "english grammar"),
        ),
        assessment_profile=AssessmentProfile("nmt-math-v1"),
    ),
    "ukrainian": SubjectDefinition(
        key="ukrainian",
        display_name="Українська мова",
        curriculum_namespace="ukrainian",
        icon="🇺🇦",
        description="Правопис і мовні норми",
        supported_language="uk",
        taxonomy_filename="ukrainian_v1.json",
        lesson_generation_policy=_policy(
            "досвідчений викладач української мови для підготовки до НМТ",
            tone="нормативний, ясний і насичений доречними мовними прикладами",
            terminology=("мовна норма", "правило", "форма слова", "речення", "контекст"),
            expectations=(
                "розмежовувати правило, виняток і контекст уживання",
                "наводити нормативні українські приклади та контрприклади",
            ),
            examples="слова, словосполучення, речення й короткі фрагменти у форматі НМТ",
            mistakes="зіставляти ненормативний варіант із виправленням та поясненням правила",
            nmt="пояснювати, як правило перевіряють у мовному блоці НМТ",
            formatting=("позначати мовні одиниці лапками", "не вигадувати неіснуючих винятків"),
        ),
        validation_profile=LessonValidationProfile(
            topic_prefix="ukrainian.",
            positive_markers=("мов", "слово", "реченн", "правопис", "наголос", "лекс", "грамат"),
            foreign_subject_markers=("розв'язати рівняння", "лінія часу історії", "present simple tense"),
        ),
        assessment_profile=AssessmentProfile("nmt-ukrainian-v1"),
    ),
    "history": SubjectDefinition(
        key="history",
        display_name="Історія України",
        curriculum_namespace="history",
        icon="📜",
        description="Дати, постаті, події",
        supported_language="uk",
        taxonomy_filename="history_v1.json",
        lesson_generation_policy=_policy(
            "досвідчений викладач історії України для підготовки до НМТ",
            tone="фактологічний, хронологічний і причинно-наслідковий",
            terminology=("період", "подія", "дата", "діяч", "причина", "наслідок", "джерело"),
            expectations=(
                "відокремлювати підтверджені факти від інтерпретацій",
                "пов'язувати хронологію, діячів, території, джерела та наслідки",
            ),
            examples="хронологічні послідовності, робота з джерелом і встановлення відповідностей",
            mistakes="виявляти анахронізми, плутанину діячів, дат, територій і наслідків",
            nmt="пов'язувати матеріал із типовими історичними завданнями НМТ",
            formatting=("дати подавати з історичним контекстом", "не вигадувати цитат або джерел"),
        ),
        validation_profile=LessonValidationProfile(
            topic_prefix="history.",
            positive_markers=("істор", "поді", "період", "хронолог", "діяч", "джерел", "держав"),
            foreign_subject_markers=("обчисли корені", "правопис апострофа", "english verb tense"),
        ),
        assessment_profile=AssessmentProfile("nmt-history-v1"),
    ),
    "english": SubjectDefinition(
        key="english",
        display_name="Англійська мова",
        curriculum_namespace="english",
        icon="🇬🇧",
        description="Граматика, лексика й читання",
        supported_language="uk",
        taxonomy_filename="english_v1.json",
        lesson_generation_policy=_policy(
            "досвідчений викладач англійської мови для україномовних учнів НМТ",
            tone="контрастивний, практичний і комунікативний",
            terminology=("grammar", "vocabulary", "context", "sentence", "reading", "use of English"),
            expectations=(
                "пояснювати правило українською та показувати природні англійські приклади",
                "зіставляти форму, значення, маркери й контекст уживання",
            ),
            examples="короткі англійські речення, мінітексти та завдання reading/use of English",
            mistakes="пояснювати інтерференцію з українською та типові граматичні й лексичні пастки",
            nmt="показувати, як мовне явище з'являється у reading та use of English НМТ",
            formatting=("англійські приклади не перекручувати транслітерацією", "пояснення давати українською"),
        ),
        validation_profile=LessonValidationProfile(
            topic_prefix="english.",
            positive_markers=("english", "grammar", "vocabulary", "reading", "sentence", "англій", "текст"),
            foreign_subject_markers=("дискримінант рівняння", "літописне джерело", "правопис м'якого знака"),
        ),
        assessment_profile=AssessmentProfile("nmt-english-v1"),
    ),
}

SUBJECT_REGISTRY: Mapping[str, SubjectDefinition] = MappingProxyType(_SUBJECTS)
ACTIVE_SUBJECT_KEYS = tuple(key for key, item in _SUBJECTS.items() if item.active)


def get_subject(subject_key: str) -> SubjectDefinition:
    try:
        return SUBJECT_REGISTRY[str(subject_key)]
    except KeyError as exc:
        raise KeyError(f"Unknown EasyNMT subject: {subject_key}") from exc


def active_subjects() -> tuple[SubjectDefinition, ...]:
    return tuple(SUBJECT_REGISTRY[key] for key in ACTIVE_SUBJECT_KEYS)
