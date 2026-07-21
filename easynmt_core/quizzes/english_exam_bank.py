"""Seeded, practical English exam exercises for Task 3D.

The bank deliberately avoids abstract questions such as "explain the rule".
Every item asks the learner to choose, transform, order, correct, translate,
complete, or use language in context.  A seed selects a different but fully
server-gradeable variant for each attempt.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import random
from typing import Iterable


@dataclass(frozen=True)
class QuestionBlueprint:
    instruction: str
    task: str
    answer_format: str
    answer_type: str
    correct_answer: str
    points: int
    options: tuple[str, ...] = ()
    accepted_answers: tuple[str, ...] = ()
    explanation: str = ""
    feedback_hint: str = "Перевір форму слова, порядок слів і маркер часу."
    grading_mode: str = "exact"
    primary_answers: tuple[str, ...] = ()
    secondary_answers: tuple[str, ...] = ()
    scoring_parts: tuple[tuple[str, ...], ...] = ()
    skill: str = "English practice"
    source_text: str = ""
    input_placeholder: str = "Напиши відповідь англійською"
    review_tip: str = "Повтори правило й виконай ще 3 подібні речення."


@dataclass(frozen=True)
class GrammarCase:
    affirmative: str
    negative: str
    question: str
    gap_task: str
    gap_answer: str
    distractors: tuple[str, str, str]
    shuffled: str
    wrong: str
    corrected: str
    ukrainian: str
    note: str


@dataclass(frozen=True)
class VocabularyCase:
    gap_task: str
    gap_answer: str
    distractors: tuple[str, str, str]
    sentence: str
    shuffled: str
    ukrainian: str
    translation: str
    wrong: str
    corrected: str
    note: str


@dataclass(frozen=True)
class ReadingCase:
    text: str
    question: str
    answer: str
    distractors: tuple[str, str, str]
    false_statement: str
    corrected_statement: str
    evidence: str
    summary_task: str
    summary_answer: str
    sequence_task: str
    sequence_answer: str


@dataclass(frozen=True)
class StrategyCase:
    situation: str
    answer: str
    distractors: tuple[str, str, str]
    short_task: str
    short_answer: str
    tip: str


def _rng(topic_id: str, seed: str) -> random.Random:
    digest = hashlib.sha256(f"{topic_id}|{seed or 'canonical'}".encode("utf-8")).digest()
    return random.Random(digest)


def _pick(pool: Iterable, count: int, rng: random.Random):
    values = list(pool)
    rng.shuffle(values)
    if len(values) < count:
        raise ValueError("English exam bank does not contain enough exercises")
    return values[:count]


def _scramble_sentence(sentence: str, rng: random.Random) -> str:
    """Return slash-separated words while preserving a gradeable source sentence."""

    words = str(sentence).strip().rstrip(".?!").split()
    shuffled = list(words)
    for _ in range(8):
        rng.shuffle(shuffled)
        if shuffled != words:
            break
    return " / ".join(shuffled)


def _choice(task: str, answer: str, distractors: tuple[str, str, str], *, skill: str, note: str, source_text: str = "") -> QuestionBlueprint:
    return QuestionBlueprint(
        instruction="Обери правильний варіант.",
        task=task,
        answer_format="Познач одну відповідь: А, Б, В або Г.",
        answer_type="choice",
        correct_answer=answer,
        accepted_answers=(answer,),
        options=(answer, *distractors),
        explanation=f"Правильна відповідь: {answer} {note}",
        feedback_hint="Знайди маркер у реченні й перевір, яка форма з ним узгоджується.",
        grading_mode="choice",
        points=1,
        skill=skill,
        source_text=source_text,
        input_placeholder="",
        review_tip=f"Повтори: {note}",
    )


def _exact(instruction: str, task: str, answer: str, *, skill: str, note: str, accepted: tuple[str, ...] = (), placeholder: str = "Напиши одне речення англійською", source_text: str = "") -> QuestionBlueprint:
    return QuestionBlueprint(
        instruction=instruction,
        task=task,
        answer_format="Напиши лише готове речення. Регістр і крапка не впливають на бал.",
        answer_type="short_text",
        correct_answer=answer,
        accepted_answers=accepted or (answer,),
        primary_answers=accepted or (answer,),
        explanation=f"Еталон: {answer} {note}",
        feedback_hint="Перевір допоміжне дієслово, форму основного дієслова й порядок слів.",
        grading_mode="exact",
        points=2,
        skill=skill,
        source_text=source_text,
        input_placeholder=placeholder,
        review_tip=f"Склади ще три речення за цією схемою. {note}",
    )


def _rubric(instruction: str, task: str, parts: tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]], *, skill: str, note: str, source_text: str = "", placeholder: str = "1) ...\n2) ...\n3) ...") -> QuestionBlueprint:
    answer = "\n".join(part[0] for part in parts)
    return QuestionBlueprint(
        instruction=instruction,
        task=task,
        answer_format="Запиши три відповіді з нового рядка або в одному рядку з позначками 1), 2), 3). Кожна правильна частина дає 1 бал.",
        answer_type="long_text",
        correct_answer=answer,
        accepted_answers=(answer,),
        scoring_parts=parts,
        explanation=f"Еталон:\n{answer}\n{note}",
        feedback_hint="Перевір кожну частину окремо: у завданні є три незалежні бали.",
        grading_mode="rubric",
        points=3,
        skill=skill,
        source_text=source_text,
        input_placeholder=placeholder,
        review_tip=f"Повтори слабку частину окремо. {note}",
    )


GRAMMAR_CASES: dict[str, tuple[GrammarCase, ...]] = {
    "english.grammar.present_past": (
        GrammarCase("She visits her grandmother every Sunday.", "She does not visit her grandmother every Sunday.", "Does she visit her grandmother every Sunday?", "My brother usually ___ to school by bike.", "goes", ("is going", "went", "go"), "usually / Anna / breakfast / has / at seven", "They is playing chess now.", "They are playing chess now.", "Вона зараз читає нову книжку.", "Use Present Simple for habits and Present Continuous for actions happening now."),
        GrammarCase("They are waiting for the bus now.", "They are not waiting for the bus now.", "Are they waiting for the bus now?", "Listen! The baby ___ .", "is crying", ("cries", "cried", "cry"), "at the moment / we / a test / are writing", "He go to the gym twice a week.", "He goes to the gym twice a week.", "Ми зараз готуємо вечерю.", "Now and at the moment normally require am/is/are + verb-ing."),
        GrammarCase("Mark finished the project yesterday.", "Mark did not finish the project yesterday.", "Did Mark finish the project yesterday?", "We ___ that museum last Saturday.", "visited", ("visit", "are visiting", "have visit"), "last night / watched / I / a documentary", "Did you saw Emma yesterday?", "Did you see Emma yesterday?", "Вони купили квитки минулого тижня.", "Past Simple questions use did + base verb."),
        GrammarCase("I was doing homework at eight o’clock.", "I was not doing homework at eight o’clock.", "Was I doing homework at eight o’clock?", "When the phone rang, Tom ___ a shower.", "was taking", ("took", "is taking", "takes"), "were / when / it started / walking / we / to rain", "She were sleeping when I came home.", "She was sleeping when I came home.", "Коли я подзвонив, він дивився фільм.", "Past Continuous shows an action in progress around a past moment."),
        GrammarCase("Kate studies English every evening.", "Kate does not study English every evening.", "Does Kate study English every evening?", "Kate ___ English every evening.", "studies", ("study", "is studying", "studied"), "every evening / English / studies / Kate", "I am usually getting up at seven.", "I usually get up at seven.", "Кейт вивчає англійську щовечора.", "Frequency adverbs commonly go before the main verb."),
        GrammarCase("We were travelling when the storm began.", "We were not travelling when the storm began.", "Were we travelling when the storm began?", "While I ___ dinner, the lights went out.", "was cooking", ("cooked", "am cooking", "cook"), "the lights / while / went out / I was cooking", "While he played, his friend was reading.", "While he was playing, his friend was reading.", "Поки ми їхали, почався сніг.", "Use while with the longer background action and Past Continuous."),
        GrammarCase("The train leaves at six every morning.", "The train does not leave at six every morning.", "Does the train leave at six every morning?", "The train ___ at 6:00 every morning.", "leaves", ("is leaving", "left", "leave"), "every morning / at six / leaves / the train", "Does the train leaves at six?", "Does the train leave at six?", "Потяг відправляється о шостій щоранку.", "After does, use the base form without -s."),
    ),
    "english.grammar.perfect_future": (
        GrammarCase("I have already finished my homework.", "I have not finished my homework yet.", "Have I finished my homework yet?", "She ___ just ___ the email.", "has just sent", ("just sent", "has just send", "is just sending"), "already / have / we / seen / this film", "He have lost his keys.", "He has lost his keys.", "Вона вже закінчила проєкт.", "Present Perfect uses have/has + past participle."),
        GrammarCase("They have lived here for five years.", "They have not lived here for five years.", "Have they lived here for five years?", "We ___ each other since 2022.", "have known", ("knew", "are knowing", "has known"), "for three months / has / worked / Maya / here", "I know him since primary school.", "I have known him since primary school.", "Ми знайомі з 2022 року.", "Use since for a starting point and for for a period."),
        GrammarCase("The film had started before we arrived.", "The film had not started before we arrived.", "Had the film started before we arrived?", "By the time I got home, everyone ___ .", "had left", ("left", "has left", "was leaving"), "had / before / arrived / the lesson / started / we", "When we arrived, the train already left.", "When we arrived, the train had already left.", "До нашого приходу урок уже почався.", "Past Perfect marks the earlier of two past actions."),
        GrammarCase("I will call you tomorrow.", "I will not call you tomorrow.", "Will I call you tomorrow?", "I think our team ___ the match.", "will win", ("wins", "is winning", "won"), "will / later / you / I / text", "She will to help us.", "She will help us.", "Я подзвоню тобі завтра.", "Will is followed by the base verb without to."),
        GrammarCase("We are going to visit Lviv next month.", "We are not going to visit Lviv next month.", "Are we going to visit Lviv next month?", "Look at the sky! It ___ rain.", "is going to", ("will to", "has", "was going"), "going to / are / a new course / they / start", "He going to buy a laptop.", "He is going to buy a laptop.", "Вони збираються почати новий курс.", "Be going to needs the correct form of be."),
        GrammarCase("By Friday, I will have completed the report.", "By Friday, I will not have completed the report.", "Will I have completed the report by Friday?", "By 8 p.m., she ___ the presentation.", "will have finished", ("will finish", "has finished", "finished"), "will have / by noon / completed / we / the task", "By tomorrow, they will finished the work.", "By tomorrow, they will have finished the work.", "До п’ятниці я завершу звіт.", "Future Perfect uses will have + past participle for a deadline."),
    ),
    "english.grammar.modals_conditionals": (
        GrammarCase("You should drink more water.", "You should not drink more water.", "Should you drink more water?", "You ___ wear a seat belt in a car.", "must", ("might", "would", "could to"), "should / before bed / use / you / less screen time", "You must to show your ticket.", "You must show your ticket.", "Тобі варто більше відпочивати.", "Modal verbs are followed by the base form without to."),
        GrammarCase("Mia can solve this problem.", "Mia cannot solve this problem.", "Can Mia solve this problem?", "When he was five, he ___ read simple words.", "could", ("can", "must", "should"), "can / very well / swim / Leo", "She cans speak French.", "She can speak French.", "Лео вміє добре плавати.", "Can and could do not take -s in the third person."),
        GrammarCase("If you heat ice, it melts.", "If you do not heat ice, it does not melt.", "Does ice melt if you heat it?", "If water reaches 100°C, it ___ .", "boils", ("will boil", "boiled", "is boiling"), "if / freezes / water / reaches / it / 0°C", "If you mix blue and yellow, you will get green.", "If you mix blue and yellow, you get green.", "Якщо нагріти лід, він тане.", "Zero conditional uses Present Simple in both clauses."),
        GrammarCase("If we leave now, we will catch the bus.", "If we do not leave now, we will not catch the bus.", "Will we catch the bus if we leave now?", "If she studies tonight, she ___ ready tomorrow.", "will be", ("is", "would be", "was"), "will / if / hurry / catch / we / the train / we", "If it will rain, we will stay home.", "If it rains, we will stay home.", "Якщо ми поспішимо, то встигнемо на потяг.", "First conditional uses Present Simple after if and will in the result."),
        GrammarCase("If I had more time, I would learn Spanish.", "If I did not have more time, I would not learn Spanish.", "Would I learn Spanish if I had more time?", "If he knew the answer, he ___ us.", "would tell", ("will tell", "tells", "would told"), "would / if / travel / I / had / more money / I", "If I would be you, I would apologise.", "If I were you, I would apologise.", "Якби я мав більше часу, я б вивчав іспанську.", "Second conditional uses Past Simple after if and would + base verb."),
        GrammarCase("If they had left earlier, they would have arrived on time.", "If they had not left earlier, they would not have arrived on time.", "Would they have arrived on time if they had left earlier?", "If I had studied, I ___ the test.", "would have passed", ("would pass", "will have passed", "had passed"), "would have / if / won / trained / she / she had / more", "If he had called, I would answered.", "If he had called, I would have answered.", "Якби вони вийшли раніше, то прибули б вчасно.", "Third conditional uses had + participle and would have + participle."),
    ),
    "english.grammar.passive_reported": (
        GrammarCase("The bridge was built in 2010.", "The bridge was not built in 2010.", "Was the bridge built in 2010?", "English ___ in many countries.", "is spoken", ("speaks", "is speaking", "was speak"), "was / by local workers / repaired / the road", "The letters were send yesterday.", "The letters were sent yesterday.", "Міст збудували у 2010 році.", "Passive voice uses be + past participle."),
        GrammarCase("The results will be announced tomorrow.", "The results will not be announced tomorrow.", "Will the results be announced tomorrow?", "The winner ___ tomorrow morning.", "will be announced", ("will announce", "is announce", "announced"), "will be / next week / opened / the new library", "The package will delivered on Friday.", "The package will be delivered on Friday.", "Результати оголосять завтра.", "Future passive uses will be + past participle."),
        GrammarCase("Anna said that she was tired.", "Anna did not say that she was tired.", "Did Anna say that she was tired?", "Tom said, “I am busy.” → Tom said that he ___ busy.", "was", ("is", "were", "has"), "said / she / that / needed / help / she", "Mia said that I was late.", "Mia said that she was late.", "Анна сказала, що вона втомлена.", "In reported speech, pronouns must match the speaker."),
        GrammarCase("Leo told me that he had lost his phone.", "Leo did not tell me that he had lost his phone.", "Did Leo tell you that he had lost his phone?", "“We finished the task,” they said. → They said that they ___ the task.", "had finished", ("finished", "have finished", "were finish"), "told / had / us / she / arrived / that / Max", "She said me that she was ready.", "She told me that she was ready.", "Лео сказав мені, що загубив телефон.", "Use tell with an object: tell me/us; use say without one."),
        GrammarCase("The room is cleaned every day.", "The room is not cleaned every day.", "Is the room cleaned every day?", "These computers ___ in Japan.", "are made", ("make", "is made", "are making"), "every day / are / the windows / cleaned", "This cars are made in Germany.", "These cars are made in Germany.", "Кімнату прибирають щодня.", "The form of be agrees with the passive subject."),
        GrammarCase("The documents had been signed before noon.", "The documents had not been signed before noon.", "Had the documents been signed before noon?", "By noon, all forms ___ .", "had been checked", ("had checked", "were checking", "have been check"), "had been / before noon / checked / every form", "The work had completed before we arrived.", "The work had been completed before we arrived.", "Документи підписали ще до полудня.", "Past Perfect passive uses had been + past participle."),
    ),
    "english.grammar.nominals_determiners": (
        GrammarCase("I bought an umbrella yesterday.", "I did not buy an umbrella yesterday.", "Did I buy an umbrella yesterday?", "She wants to become ___ engineer.", "an", ("a", "the", "some"), "an / found / old map / we", "He is a honest person.", "He is an honest person.", "Я купив парасолю вчора.", "Choose a/an by sound, not only by the first letter."),
        GrammarCase("There is some juice in the fridge.", "There is not any juice in the fridge.", "Is there any juice in the fridge?", "There isn’t ___ bread left.", "any", ("some", "many", "a"), "any / do / questions / have / you", "We don’t have some milk.", "We don’t have any milk.", "У холодильнику є трохи соку.", "Any is common in negatives and questions."),
        GrammarCase("These notebooks are mine.", "These notebooks are not mine.", "Are these notebooks mine?", "This jacket belongs to her. It is ___ .", "hers", ("her", "she", "their"), "ours / these seats / are", "That phone is her.", "That phone is hers.", "Ці зошити мої.", "Possessive pronouns stand alone without a following noun."),
        GrammarCase("There are a few apples on the table.", "There are not many apples on the table.", "Are there any apples on the table?", "We have ___ time, so let’s hurry.", "little", ("few", "many", "a few"), "a few / made / mistakes / she", "There are little students in the room.", "There are few students in the room.", "У нас мало часу, тому поспішаймо.", "Use little with uncountable nouns and few with countable nouns."),
        GrammarCase("The information is useful.", "The information is not useful.", "Is the information useful?", "The news ___ surprising.", "is", ("are", "be", "were being"), "is / this advice / helpful", "These information are important.", "This information is important.", "Ця інформація корисна.", "Information and advice are uncountable and normally singular."),
        GrammarCase("Both answers are possible.", "Neither answer is possible.", "Are both answers possible?", "___ of the two routes is safe; choose another one.", "Neither", ("Both", "All", "Every"), "both / enjoyed / the students / the lesson", "Neither of the answers are correct.", "Neither of the answers is correct.", "Обидві відповіді можливі.", "Neither of is normally followed by a singular verb in formal English."),
    ),
    "english.grammar.modifiers_prepositions": (
        GrammarCase("She speaks English fluently.", "She does not speak English fluently.", "Does she speak English fluently?", "The athlete ran very ___ .", "quickly", ("quick", "quicker", "quickness"), "carefully / the instructions / read / please", "He drives very careful.", "He drives very carefully.", "Вона вільно розмовляє англійською.", "Use an adverb to describe how an action happens."),
        GrammarCase("The keys are on the table.", "The keys are not on the table.", "Are the keys on the table?", "The picture is hanging ___ the wall.", "on", ("in", "at", "between"), "under / is / the chair / the bag", "We arrived to the station at noon.", "We arrived at the station at noon.", "Ключі лежать на столі.", "Use arrive at for a specific place and arrive in for a city or country."),
        GrammarCase("This task is easier than the previous one.", "This task is not easier than the previous one.", "Is this task easier than the previous one?", "My room is ___ than yours.", "smaller", ("more small", "smallest", "small"), "than / this book / more interesting / that one / is", "Today is more hot than yesterday.", "Today is hotter than yesterday.", "Це завдання легше за попереднє.", "Short adjectives usually form the comparative with -er."),
        GrammarCase("Mount Everest is the highest mountain in the world.", "Mount Everest is not the lowest mountain in the world.", "Is Mount Everest the highest mountain in the world?", "This is ___ film I have ever seen.", "the most exciting", ("more exciting", "the exciting", "most excited"), "the / in our class / tallest / student / is / Danylo", "She is most talented player on the team.", "She is the most talented player on the team.", "Еверест є найвищою горою у світі.", "Superlatives normally use the and compare within a group."),
        GrammarCase("We met at the station at six.", "We did not meet at the station at six.", "Did we meet at the station at six?", "The lesson starts ___ Monday ___ nine o’clock.", "on Monday at nine o’clock", ("at Monday in nine o’clock", "in Monday on nine o’clock", "on Monday in nine o’clock"), "at six / on Friday / starts / the concert", "I was born at 2011.", "I was born in 2011.", "Ми зустрілися на станції о шостій.", "Use on for days, at for clock times and in for years."),
        GrammarCase("The test was surprisingly easy.", "The test was not surprisingly easy.", "Was the test surprisingly easy?", "The teacher explained the rule very ___ .", "clearly", ("clear", "clearest", "clarity"), "extremely / was / the journey / tiring", "The film was bored.", "The film was boring.", "Учитель дуже чітко пояснив правило.", "-ing adjectives describe things; -ed adjectives describe feelings."),
    ),
}


VOCABULARY_CASES: dict[str, tuple[VocabularyCase, ...]] = {
    "english.vocabulary.word_formation": (
        VocabularyCase("Be ___ when you cross the road. (CARE)", "careful", ("carefully", "careless", "caring"), "Be careful when you cross the road.", "when / careful / be / cross / you / the road", "Будь обережним, коли переходиш дорогу.", "Be careful when you cross the road.", "She answered the question very careful.", "She answered the question very carefully.", "After be use an adjective; after a verb use an adverb."),
        VocabularyCase("It is ___ to finish this in one minute. (POSSIBLE)", "impossible", ("possibility", "possibly", "unpossible"), "It is impossible to finish this in one minute.", "impossible / in one minute / it is / to finish", "Неможливо завершити це за одну хвилину.", "It is impossible to finish this in one minute.", "This plan is impossibly.", "This plan is impossible.", "The prefix im- creates the negative form of possible."),
        VocabularyCase("The project was very ___. (SUCCESS)", "successful", ("successfully", "success", "unsuccess"), "The project was very successful.", "very / successful / the project / was", "Проєкт був дуже успішним.", "The project was very successful.", "They completed the project successful.", "They completed the project successfully.", "After was very use an adjective; to modify completed use an adverb."),
        VocabularyCase("Thank you for your ___. (KIND)", "kindness", ("kindly", "kind", "unkind"), "Thank you for your kindness.", "for / thank you / kindness / your", "Дякую за твою доброту.", "Thank you for your kindness.", "Her kind made everyone smile.", "Her kindness made everyone smile.", "After a possessive determiner, a noun is usually needed."),
        VocabularyCase("The instructions were clear and ___. (HELP)", "helpful", ("helpfully", "helpless", "help"), "The instructions were clear and helpful.", "clear / were / and helpful / the instructions", "Інструкції були чіткими й корисними.", "The instructions were clear and helpful.", "The guide explained everything helpful.", "The guide explained everything helpfully.", "-ful often forms adjectives; -fully forms adverbs."),
        VocabularyCase("She spoke with great ___. (CONFIDENT)", "confidence", ("confident", "confidently", "unconfident"), "She spoke with great confidence.", "with / spoke / confidence / she / great", "Вона говорила з великою впевненістю.", "She spoke with great confidence.", "She is a confidence speaker.", "She is a confident speaker.", "Confidence is a noun; confident is an adjective."),
        VocabularyCase("The documentary was extremely ___. (INFORM)", "informative", ("information", "informatively", "informed"), "The documentary was extremely informative.", "extremely / informative / was / the documentary", "Документальний фільм був дуже пізнавальним.", "The documentary was extremely informative.", "It gave us many useful informations.", "It gave us a lot of useful information.", "Information is uncountable; informative describes something useful to learn from."),
    ),
    "english.vocabulary.collocations_phrasal": (
        VocabularyCase("We need to ___ a decision today.", "make", ("do", "take", "create"), "We need to make a decision today.", "a decision / need / make / we / to", "Нам потрібно сьогодні ухвалити рішення.", "We need to make a decision today.", "We did a difficult decision.", "We made a difficult decision.", "The fixed collocation is make a decision."),
        VocabularyCase("Can you ___ my dog this weekend?", "look after", ("look for", "look up", "look at"), "Can you look after my dog this weekend?", "my dog / look after / can you / this weekend", "Ти можеш доглянути за моїм собакою цими вихідними?", "Can you look after my dog this weekend?", "I am looking my keys.", "I am looking for my keys.", "Look after means care for; look for means try to find."),
        VocabularyCase("The match was cancelled because of ___ rain.", "heavy", ("strong", "big", "hardly"), "The match was cancelled because of heavy rain.", "because of / was cancelled / heavy rain / the match", "Матч скасували через сильний дощ.", "The match was cancelled because of heavy rain.", "There was a strong rain all night.", "There was heavy rain all night.", "English normally uses heavy rain."),
        VocabularyCase("Please ___ the lights before you leave.", "switch off", ("switch on", "turn up", "put off"), "Please switch off the lights before you leave.", "before / switch off / you leave / the lights", "Будь ласка, вимкни світло перед виходом.", "Please switch off the lights before you leave.", "Please switch the lights off them.", "Please switch the lights off.", "A pronoun goes between the verb and particle: switch them off."),
        VocabularyCase("I need to ___ this form before Friday.", "fill in", ("give up", "take off", "find out"), "I need to fill in this form before Friday.", "this form / fill in / need to / I", "Мені потрібно заповнити цю форму до п’ятниці.", "I need to fill in this form before Friday.", "Please fill this form in it.", "Please fill in this form.", "Fill in means complete a form."),
        VocabularyCase("She always ___ attention in class.", "pays", ("makes", "does", "takes"), "She always pays attention in class.", "in class / pays / attention / she / always", "Вона завжди уважна на уроці.", "She always pays attention in class.", "You should give attention to the road.", "You should pay attention to the road.", "The fixed collocation is pay attention."),
        VocabularyCase("We ___ a great time at the festival.", "had", ("made", "spent", "did"), "We had a great time at the festival.", "at the festival / had / a great time / we", "Ми чудово провели час на фестивалі.", "We had a great time at the festival.", "We made a great time there.", "We had a great time there.", "The fixed phrase is have a great time."),
    ),
}


READING_CASES: dict[str, tuple[ReadingCase, ...]] = {
    "english.reading.gist_detail": (
        ReadingCase("Mia cycles to school because it is faster than the bus and gives her daily exercise. She also enjoys avoiding the morning traffic.", "What is the main idea?", "Mia prefers cycling because it is quick, healthy and convenient.", ("Mia dislikes all public transport.", "Mia trains for a professional race every morning.", "The bus is always empty in the morning."), "Mia cycles only because the bus is too expensive.", "Mia cycles because it is faster, healthy and helps her avoid traffic.", "faster than the bus and gives her daily exercise", "Complete the summary with one word: Cycling is faster and gives Mia daily ___.", "exercise", "Put the reasons in the order used in the text: a) avoid traffic; b) get exercise; c) travel faster.", "c-b-a"),
        ReadingCase("The town museum opens at 10 a.m. on weekdays and at 11 a.m. on Sundays. Students enter free on Wednesdays if they show a school card.", "When can a student visit for free?", "On Wednesday with a school card.", ("Every Sunday before 11 a.m.", "Any weekday without identification.", "Only on Saturday afternoon."), "The museum opens at 10 a.m. every day.", "It opens at 10 a.m. on weekdays and at 11 a.m. on Sundays.", "Students enter free on Wednesdays if they show a school card", "Complete: On Sundays the museum opens at ___ a.m.", "11", "Order the information: a) Sunday opening; b) free student entry; c) weekday opening.", "c-a-b"),
        ReadingCase("Leo packed a raincoat, waterproof boots and an umbrella before leaving. The forecast had mentioned strong showers in the afternoon.", "What weather did Leo expect?", "Rainy weather with strong showers.", ("Hot and dry weather.", "Heavy snow during the night.", "A calm day without clouds."), "Leo packed sports clothes for a sunny day.", "Leo packed waterproof items because rain was expected.", "The forecast had mentioned strong showers", "Complete the summary: Leo prepared for ___ weather.", "rainy", "Order the clues: a) umbrella; b) forecast; c) waterproof boots.", "a-c-b"),
        ReadingCase("Nora joined the school robotics club in September. At first she found coding difficult, but after two months she could program a small sensor by herself.", "What changed after two months?", "Nora could program a small sensor independently.", ("Nora left the robotics club.", "The club stopped teaching coding.", "Nora became the school’s head teacher."), "Nora found coding easy from the first lesson.", "At first coding was difficult, but later Nora could program a sensor alone.", "after two months she could program a small sensor by herself", "Complete: Nora improved her ___ skills.", "coding", "Put the events in order: a) programs a sensor; b) joins the club; c) finds coding difficult.", "b-c-a"),
        ReadingCase("A new community garden opened beside the library. Residents can grow vegetables there, while the library runs free weekend workshops on composting.", "What is the text mainly about?", "A community garden and free gardening workshops.", ("A plan to close the local library.", "A private farm selling expensive vegetables.", "A competition for professional chefs."), "Only library workers may use the garden.", "Residents can grow vegetables, and the library offers free workshops.", "Residents can grow vegetables there", "Complete: The workshops teach people about ___.", "composting", "Order the details: a) workshops; b) garden location; c) growing vegetables.", "b-c-a"),
    ),
    "english.reading.cohesion_inference": (
        ReadingCase("Olena bought a new laptop last week. It was lighter than her old one, so she could carry it to school more easily.", "What does “It” refer to?", "The new laptop.", ("The school.", "Last week.", "Olena’s old bag."), "The old laptop was lighter than the new one.", "The new laptop was lighter than the old one.", "It was lighter than her old one", "Complete: The word “it” replaces the noun ___.", "laptop", "Order the ideas: a) easier to carry; b) buys laptop; c) laptop is lighter.", "b-c-a"),
        ReadingCase("Please switch off the lights when you leave the classroom. This simple habit saves energy and reduces the school’s electricity bill.", "What is the writer’s purpose?", "To give an instruction and explain why it matters.", ("To advertise new classroom lights.", "To describe a power cut at school.", "To invite students to stay after class."), "The writer asks students to leave the lights on.", "The writer asks students to switch the lights off when leaving.", "saves energy and reduces the school’s electricity bill", "Complete: Switching off lights helps save ___.", "energy", "Order the logic: a) lower bill; b) switch off lights; c) save energy.", "b-c-a"),
        ReadingCase("The streets were wet and several people carried closed umbrellas. Although no one had seen the rain, dark clouds were moving away.", "What can you infer?", "It probably rained shortly before.", ("The streets were washed by firefighters.", "It will definitely snow tonight.", "Everyone had just bought a new umbrella."), "The text directly states that it rained all day.", "The text suggests, but does not directly state, that it rained earlier.", "streets were wet ... dark clouds were moving away", "Complete: The evidence suggests earlier ___.", "rain", "Order the clues: a) moving clouds; b) wet streets; c) closed umbrellas.", "b-c-a"),
        ReadingCase("Sam checked the café door twice, but it would not open. A small sign beside the handle said, “Closed for renovation until Monday.”", "Why could Sam not enter?", "The café was closed for renovation.", ("Sam had forgotten his wallet.", "The handle belonged to another building.", "The café opened only at night."), "The café was closed because it had no customers.", "The café was closed for renovation until Monday.", "Closed for renovation until Monday", "Complete: The sign explains the café’s temporary ___.", "closure", "Order the events: a) reads sign; b) checks door; c) understands reason.", "b-a-c"),
        ReadingCase("Lina whispered during the presentation and kept looking at the clock. When the bell rang, she quickly packed her bag and ran towards the sports hall.", "What is most likely true?", "Lina was eager to get to an activity in the sports hall.", ("Lina had forgotten where the sports hall was.", "Lina wanted the presentation to continue longer.", "Lina planned to leave the school permanently."), "Lina showed no interest in the time.", "Lina repeatedly checked the time and left quickly after the bell.", "kept looking at the clock ... ran towards the sports hall", "Complete: Lina was probably in a ___.", "hurry", "Order the actions: a) runs to hall; b) checks clock; c) packs bag.", "b-c-a"),
    ),
}


STRATEGY_CASES: tuple[StrategyCase, ...] = (
    StrategyCase("You have 20 minutes left, two short tasks and one long text.", "Complete the short tasks first, then the long text, and leave time for a final check.", ("Read the long text repeatedly and leave the short tasks blank.", "Guess every answer immediately without reading.", "Spend all remaining time on the first difficult question."), "Write a three-step time plan for this situation.", "short tasks → long text → final check", "Secure quick points first and protect a few minutes for checking."),
    StrategyCase("Two options look almost identical in a reading question.", "Compare both options with the exact wording and reject unsupported information.", ("Choose the longer option.", "Choose the option with familiar vocabulary.", "Pick the first option and move on."), "What evidence should decide between the two options?", "the exact sentence or idea in the text", "The answer must be supported by the text, not by how familiar it sounds."),
    StrategyCase("You finish the English block with three minutes left.", "Check blank items, grammar markers and whether answers fit the local context.", ("Rewrite every answer in full.", "Start the entire test again from question one.", "Close the test immediately."), "Name the first two things to check.", "blank items and grammar/context markers", "A targeted scan is more useful than rereading everything."),
    StrategyCase("A gap can take either a noun or an adjective, and both options look related.", "Use the words around the gap to identify the required part of speech.", ("Choose the word with the most letters.", "Ignore the sentence and translate both options.", "Always choose the noun."), "What should you inspect directly before and after the gap?", "the surrounding words and sentence structure", "Grammar around the gap reveals the required part of speech."),
    StrategyCase("You do not know one word in a reading paragraph.", "Use the sentence, nearby contrast or example, and continue reading before deciding.", ("Stop and leave the whole text unanswered.", "Assume the word means the first Ukrainian translation you remember.", "Choose an answer without reading the next sentence."), "Write the safest next action.", "read the surrounding sentence and continue for context", "One unknown word rarely blocks the whole paragraph."),
    StrategyCase("A grammar option is correct by form but does not match the meaning of the sentence.", "Reject it because both grammar and context must fit.", ("Keep it because form is the only thing that matters.", "Choose the shortest option instead.", "Translate only the isolated verb."), "What two checks must every grammar option pass?", "grammar form and sentence meaning", "A correct form can still be wrong in context."),
    StrategyCase("You changed an answer after noticing a time marker.", "Keep the new answer only if the marker and the whole sentence support it.", ("Always return to the first answer.", "Change every answer that contains a verb.", "Ignore time markers during the final check."), "What should justify changing an answer?", "clear evidence from the marker and context", "Change answers for evidence, not anxiety."),
)


DIALOGUES: dict[str, tuple[tuple[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]], ...]] = {
    "english.grammar.present_past": (
        ("Complete the mini-dialogue. A: Where is Ben? B: He ___ (study) in the library now. A: ___ he usually ___ (study) there? B: No, he ___ (work) at home on weekdays.", (("is studying",), ("Does he usually study",), ("works",))),
        ("Complete the mini-dialogue. A: What ___ you ___ (do) yesterday? B: I ___ (visit) my cousin. A: What was she doing? B: She ___ (prepare) dinner.", (("did you do",), ("visited",), ("was preparing",))),
    ),
    "english.grammar.perfect_future": (
        ("Complete the mini-dialogue. A: ___ you ever ___ (try) sushi? B: Yes, I ___ (eat) it twice. A: Great. We ___ (go) to a Japanese café tomorrow.", (("Have you ever tried",), ("have eaten",), ("are going", "will go"))),
        ("Complete the mini-dialogue. A: Why is Maya tired? B: She ___ just ___ (finish) a long test. A: ___ she ___ (rest) now? B: Yes, and by evening she ___ (recover).", (("has just finished",), ("Is she going to rest", "Will she rest"), ("will have recovered",))),
    ),
    "english.grammar.modals_conditionals": (
        ("Complete the mini-dialogue. A: I feel ill. B: You ___ see a doctor. A: What if I have a fever? B: If it gets worse, you ___ call your parents. A: ___ I go to school tomorrow?", (("should",), ("should", "must"), ("Should",))),
        ("Complete the mini-dialogue. A: What would you do if you ___ (find) a wallet? B: I ___ take it to the police. A: And if it had an address? B: I ___ have contacted the owner directly.", (("found",), ("would",), ("would",))),
    ),
    "english.grammar.passive_reported": (
        ("Complete the mini-dialogue. A: When ___ the library ___ (open)? B: It was opened in 1998. A: Who designed it? B: The guide said that a local architect ___ designed it. A: ___ it still ___ (use) today? B: Yes.", (("was the library opened",), ("had",), ("is it still used",))),
        ("Complete the mini-dialogue. A: What did Mia say? B: She said that she ___ tired. A: Were the results ready? B: No, they ___ be announced tomorrow. A: ___ everyone informed?", (("was",), ("would", "will"), ("Was",))),
    ),
    "english.grammar.nominals_determiners": (
        ("Complete the mini-dialogue. A: Is this notebook ___? B: No, mine is blue. It may be ___. A: Do you have ___ idea whose it is?", (("yours",), ("hers", "his", "theirs"), ("any",))),
        ("Complete the mini-dialogue. A: Is there ___ milk? B: Only ___ little. A: Then buy ___ bottle on your way home.", (("any",), ("a",), ("a",))),
    ),
    "english.grammar.modifiers_prepositions": (
        ("Complete the mini-dialogue. A: When does the train leave? B: ___ Friday ___ 7:30. A: Is it ___ than the bus? B: Yes, much faster.", (("On",), ("at",), ("faster",))),
        ("Complete the mini-dialogue. A: How did Anna perform? B: She sang very ___. A: Was she the ___ performer? B: Yes, everyone listened ___.", (("beautifully", "well"), ("best",), ("carefully", "quietly"))),
    ),
}


def _grammar_blueprints(topic_id: str, seed: str) -> tuple[QuestionBlueprint, ...]:
    rng = _rng(topic_id, seed)
    cases = _pick(GRAMMAR_CASES[topic_id], 6, rng)
    skill = {
        "english.grammar.present_past": "Часи Present і Past",
        "english.grammar.perfect_future": "Perfect і Future",
        "english.grammar.modals_conditionals": "Модальні дієслова й conditionals",
        "english.grammar.passive_reported": "Passive і Reported Speech",
        "english.grammar.nominals_determiners": "Артиклі, займенники й кількість",
        "english.grammar.modifiers_prepositions": "Прислівники, порівняння й прийменники",
    }[topic_id]
    questions: list[QuestionBlueprint] = []
    for case in cases[:4]:
        questions.append(_choice(case.gap_task, case.gap_answer, case.distractors, skill=skill, note=case.note))
    questions.extend((
        _exact("Перетвори речення на заперечення.", cases[4].affirmative, cases[4].negative, skill=f"{skill}: заперечення", note=cases[4].note),
        _exact("Перетвори речення на загальне питання.", cases[5].affirmative, cases[5].question, skill=f"{skill}: питання", note=cases[5].note),
        _exact("Склади правильне речення зі слів.", _scramble_sentence(cases[0].affirmative, rng), cases[0].affirmative, skill=f"{skill}: порядок слів", note=cases[0].note),
        _exact("Знайди й виправ одну граматичну помилку.", cases[1].wrong, cases[1].corrected, skill=f"{skill}: виправлення", note=cases[1].note),
    ))
    questions.append(_rubric(
        "Заповни три пропуски.",
        "\n".join(f"{index}) {case.gap_task}" for index, case in enumerate(cases[:3], start=1)),
        tuple((case.gap_answer,) for case in cases[:3]),
        skill=f"{skill}: форми в контексті",
        note="Кожен пропуск перевіряється окремо.",
    ))
    questions.append(_rubric(
        "Виконай три різні перетворення.",
        f"1) Зроби заперечення: {cases[2].affirmative}\n2) Зроби питання: {cases[3].affirmative}\n3) Виправ: {cases[4].wrong}",
        ((cases[2].negative,), (cases[3].question,), (cases[4].corrected,)),
        skill=f"{skill}: трансформації",
        note="У кожному рядку перевір окрему граматичну схему.",
    ))
    dialogue_task, dialogue_parts = rng.choice(DIALOGUES[topic_id])
    questions.append(_rubric(
        "Заповни мінідіалог.", dialogue_task, dialogue_parts,
        skill=f"{skill}: діалог", note="Форма має відповідати репліці й контексту.",
    ))
    questions.append(_rubric(
        "Виконай фінальний мікс.",
        f"1) Зроби заперечення: {cases[5].affirmative}\n2) Зроби питання: {cases[5].affirmative}\n3) Виправ помилку: {cases[5].wrong}",
        ((cases[5].negative,), (cases[5].question,), (cases[5].corrected,)),
        skill=f"{skill}: повний цикл",
        note="Усі три рядки перевіряють різні дії з тією самою граматичною темою.",
    ))
    return tuple(questions)


def _vocabulary_blueprints(topic_id: str, seed: str) -> tuple[QuestionBlueprint, ...]:
    rng = _rng(topic_id, seed)
    cases = _pick(VOCABULARY_CASES[topic_id], 6, rng)
    skill = "Word formation" if topic_id.endswith("word_formation") else "Collocations і phrasal verbs"
    questions: list[QuestionBlueprint] = [
        _choice(case.gap_task, case.gap_answer, case.distractors, skill=skill, note=case.note)
        for case in cases[:4]
    ]
    questions.extend((
        _exact("Встав правильне слово або словосполучення.", cases[4].gap_task, cases[4].gap_answer, skill=f"{skill}: форма в реченні", note=cases[4].note, placeholder="Напиши тільки слово або словосполучення"),
        _exact("Склади речення зі слів.", _scramble_sentence(cases[5].sentence, rng), cases[5].sentence, skill=f"{skill}: порядок слів", note=cases[5].note),
        _exact("Переклади речення англійською.", cases[0].ukrainian, cases[0].translation, skill=f"{skill}: переклад", note=cases[0].note),
        _exact("Виправ лексичну або словотвірну помилку.", cases[1].wrong, cases[1].corrected, skill=f"{skill}: виправлення", note=cases[1].note),
    ))
    questions.append(_rubric(
        "Заповни три пропуски.",
        "\n".join(f"{i}) {case.gap_task}" for i, case in enumerate(cases[:3], start=1)),
        tuple((case.gap_answer,) for case in cases[:3]),
        skill=f"{skill}: серія пропусків", note="Перевір частину мови або сталість словосполучення.",
    ))
    questions.append(_rubric(
        "Виправ три речення.",
        "\n".join(f"{i}) {case.wrong}" for i, case in enumerate(cases[2:5], start=1)),
        tuple((case.corrected,) for case in cases[2:5]),
        skill=f"{skill}: редактор", note="У кожному реченні є одна цільова помилка.",
    ))
    questions.append(_rubric(
        "Заверши мінідіалог трьома відповідями.",
        f"A: We need help with today’s task.\nB: 1) {cases[0].gap_task}\nA: And what should I say next?\nB: 2) {cases[1].gap_task}\nA: One more example?\nB: 3) {cases[2].gap_task}",
        tuple((case.gap_answer,) for case in cases[:3]),
        skill=f"{skill}: у діалозі", note="Добирай слово за всім реченням, а не окремим перекладом.",
    ))
    questions.append(_rubric(
        "Виконай три практичні дії.",
        f"1) Переклади: {cases[3].ukrainian}\n2) Склади зі слів: {_scramble_sentence(cases[4].sentence, rng)}\n3) Виправ: {cases[5].wrong}",
        ((cases[3].translation,), (cases[4].sentence,), (cases[5].corrected,)),
        skill=f"{skill}: комбінована практика", note="Кожна відповідь має власний формат.",
    ))
    return tuple(questions)


def _reading_blueprints(topic_id: str, seed: str) -> tuple[QuestionBlueprint, ...]:
    rng = _rng(topic_id, seed)
    cases = _pick(READING_CASES[topic_id], 5, rng)
    skill = "Main idea і details" if topic_id.endswith("gist_detail") else "Cohesion і inference"
    questions: list[QuestionBlueprint] = []
    for case in cases[:4]:
        questions.append(_choice(case.question, case.answer, case.distractors, skill=skill, note="Спирайся лише на текст.", source_text=case.text))
    questions.extend((
        _exact("Дай коротку відповідь за текстом.", cases[4].question, cases[4].answer, skill=f"{skill}: коротка відповідь", note="Відповідь має бути підтверджена текстом.", source_text=cases[4].text),
        _exact("Виправ хибне твердження за текстом.", cases[0].false_statement, cases[0].corrected_statement, skill=f"{skill}: перевірка факту", note="Не додавай інформацію, якої немає в уривку.", source_text=cases[0].text),
        _exact("Віднови порядок подій або деталей.", cases[1].sequence_task, cases[1].sequence_answer, skill=f"{skill}: послідовність", note="Запиши лише послідовність літер через дефіс.", placeholder="Наприклад: b-a-c", source_text=cases[1].text),
        _exact("Випиши найкоротший доказ із тексту.", cases[2].question, cases[2].evidence, skill=f"{skill}: evidence", note="Достатньо ключової фрази з уривка.", accepted=(cases[2].evidence, cases[2].answer), placeholder="Коротка фраза з тексту", source_text=cases[2].text),
    ))
    focus = cases[0]
    questions.append(_rubric(
        "Дай три відповіді за одним уривком.",
        f"Текст: {focus.text}\n1) {focus.question}\n2) Виправ: {focus.false_statement}\n3) {focus.summary_task}",
        ((focus.answer,), (focus.corrected_statement,), (focus.summary_answer,)),
        skill=f"{skill}: комплексне читання", note="Кожна відповідь повинна мати опору в уривку.", source_text=focus.text,
    ))
    questions.append(_rubric(
        "Віднови зміст трьох уривків.",
        "\n".join(f"{i}) {case.summary_task}" for i, case in enumerate(cases[1:4], start=1)),
        tuple((case.summary_answer,) for case in cases[1:4]),
        skill=f"{skill}: summary", note="Встав слово, яке точно узгоджується зі змістом.",
    ))
    questions.append(_rubric(
        "Проведи коротку перевірку читання.",
        f"1) Для уривка 1 запиши порядок: {cases[2].sequence_task}\n2) Для уривка 2 виправ твердження: {cases[3].false_statement}\n3) Для уривка 3 дай відповідь: {cases[4].question}",
        ((cases[2].sequence_answer,), (cases[3].corrected_statement,), (cases[4].answer,)),
        skill=f"{skill}: три навички", note="Не змішуй інформацію між уривками.",
    ))
    questions.append(_rubric(
        "Знайди опору для трьох висновків.",
        f"1) Текст: {cases[0].text}\nПитання: {cases[0].question}\n2) Текст: {cases[1].text}\nПитання: {cases[1].question}\n3) Текст: {cases[2].text}\nПитання: {cases[2].question}",
        ((cases[0].evidence,), (cases[1].evidence,), (cases[2].evidence,)),
        skill=f"{skill}: пошук доказу", note="Копіювати весь текст не потрібно, лише ключову фразу.",
    ))
    return tuple(questions)


def _integrated_blueprints(seed: str) -> tuple[QuestionBlueprint, ...]:
    rng = _rng("english.integrated.use_of_english", seed)
    all_cases = [case for cases in GRAMMAR_CASES.values() for case in cases]
    selected = _pick(all_cases, 8, rng)
    skill = "Use of English"
    questions: list[QuestionBlueprint] = [
        _choice(case.gap_task, case.gap_answer, case.distractors, skill=skill, note=case.note)
        for case in selected[:4]
    ]
    questions.extend((
        _exact("Перетвори речення на заперечення.", selected[4].affirmative, selected[4].negative, skill=f"{skill}: negative", note=selected[4].note),
        _exact("Перетвори речення на питання.", selected[5].affirmative, selected[5].question, skill=f"{skill}: question", note=selected[5].note),
        _exact("Склади речення зі слів.", _scramble_sentence(selected[6].affirmative, rng), selected[6].affirmative, skill=f"{skill}: word order", note=selected[6].note),
        _exact("Виправ помилку.", selected[7].wrong, selected[7].corrected, skill=f"{skill}: correction", note=selected[7].note),
    ))
    questions.append(_rubric(
        "Заповни три пропуски різних типів.",
        "\n".join(f"{i}) {case.gap_task}" for i, case in enumerate(selected[:3], start=1)),
        tuple((case.gap_answer,) for case in selected[:3]),
        skill=f"{skill}: mixed gaps", note="Спочатку визнач граматичний сигнал кожного речення.",
    ))
    questions.append(_rubric(
        "Виконай три трансформації.",
        f"1) Negative: {selected[2].affirmative}\n2) Question: {selected[3].affirmative}\n3) Correct: {selected[4].wrong}",
        ((selected[2].negative,), (selected[3].question,), (selected[4].corrected,)),
        skill=f"{skill}: mixed transformations", note="Не перенось допоміжне дієслово з одного часу в інший.",
    ))
    questions.append(_rubric(
        "Пройди мінісерію з трьох пропусків.",
        f"1) {selected[0].gap_task}\n2) {selected[1].gap_task}\n3) {selected[5].gap_task}",
        ((selected[0].gap_answer,), (selected[1].gap_answer,), (selected[5].gap_answer,)),
        skill=f"{skill}: mini text", note="Кожен пропуск має окремий контекстний маркер.",
    ))
    questions.append(_rubric(
        "Виконай фінальний комбінований блок.",
        f"1) Зроби заперечення: {selected[6].affirmative}\n2) Зроби питання: {selected[6].affirmative}\n3) Виправ помилку: {selected[7].wrong}",
        ((selected[6].negative,), (selected[6].question,), (selected[7].corrected,)),
        skill=f"{skill}: production", note="У кожному рядку є окрема практична дія.",
    ))
    return tuple(questions)


def _strategy_blueprints(seed: str) -> tuple[QuestionBlueprint, ...]:
    rng = _rng("english.integrated.nmt_strategy", seed)
    cases = _pick(STRATEGY_CASES, 7, rng)
    skill = "NMT strategy"
    questions: list[QuestionBlueprint] = [
        _choice(case.situation, case.answer, case.distractors, skill=skill, note=case.tip)
        for case in cases[:4]
    ]
    questions.extend((
        _exact("Дай коротку стратегію.", cases[4].short_task, cases[4].short_answer, skill=f"{skill}: evidence", note=cases[4].tip, accepted=(cases[4].short_answer, cases[4].answer)),
        _exact("Запиши наступний безпечний крок.", cases[5].short_task, cases[5].short_answer, skill=f"{skill}: next step", note=cases[5].tip, accepted=(cases[5].short_answer, cases[5].answer)),
        _exact("Склади короткий план.", cases[0].short_task, cases[0].short_answer, skill=f"{skill}: time plan", note=cases[0].tip, accepted=(cases[0].short_answer, cases[0].answer), placeholder="Крок 1 → крок 2 → крок 3"),
        _exact("Назви критерій перевірки.", cases[1].short_task, cases[1].short_answer, skill=f"{skill}: checking", note=cases[1].tip, accepted=(cases[1].short_answer, cases[1].answer)),
    ))
    questions.append(_rubric(
        "Створи план останніх п’яти хвилин.",
        "Запиши три дії в правильному порядку: 1) що перевірити спочатку; 2) що звірити в реченнях; 3) що зробити перед відправленням.",
        (("blank items", "unanswered items", "пропущені завдання"), ("grammar markers", "context markers", "маркери часу і контекст"), ("final check", "submit after checking", "остаточна перевірка")),
        skill=f"{skill}: final check", note="План має бути коротким і виконуваним.",
    ))
    questions.append(_rubric(
        "Розбери три ризикові ситуації.",
        f"1) {cases[2].situation}\n2) {cases[3].situation}\n3) {cases[6].situation}",
        ((cases[2].answer,), (cases[3].answer,), (cases[6].answer,)),
        skill=f"{skill}: decisions", note="Для кожної ситуації потрібна окрема дія.",
    ))
    questions.append(_rubric(
        "Склади мініалгоритм вибору відповіді.",
        "1) Що перевірити в умові?\n2) З чим зіставити варіант?\n3) Коли відкинути варіант?",
        (("marker", "key word", "ключову ознаку", "маркер"), ("text", "context", "rule", "текстом", "контекстом", "правилом"), ("unsupported", "does not fit", "не підтверджено", "не підходить")),
        skill=f"{skill}: answer algorithm", note="Алгоритм має спиратися на доказ, а не на здогад.",
    ))
    questions.append(_rubric(
        "Зроби особистий протокол перевірки.",
        "Запиши три короткі правила, які ти застосуєш у наступному тесті: для часу, для складного варіанта і для фінальної перевірки.",
        (("time", "timer", "час", "план часу"), ("evidence", "context", "доказ", "контекст"), ("blank", "marker", "check", "пропуски", "перевірка")),
        skill=f"{skill}: personal protocol", note="Кожне правило повинно описувати конкретну дію.",
    ))
    return tuple(questions)


def build_english_blueprints(topic_id: str, seed: str = "") -> tuple[QuestionBlueprint, ...]:
    """Return one 12-question, 24-point practical English variant."""

    if topic_id in GRAMMAR_CASES:
        result = _grammar_blueprints(topic_id, seed)
    elif topic_id in VOCABULARY_CASES:
        result = _vocabulary_blueprints(topic_id, seed)
    elif topic_id in READING_CASES:
        result = _reading_blueprints(topic_id, seed)
    elif topic_id == "english.integrated.use_of_english":
        result = _integrated_blueprints(seed)
    elif topic_id == "english.integrated.nmt_strategy":
        result = _strategy_blueprints(seed)
    else:
        raise KeyError(f"No English exam blueprint for topic: {topic_id}")
    if len(result) != 12 or [item.points for item in result] != [1] * 4 + [2] * 4 + [3] * 4:
        raise ValueError("English exam blueprint violates the 12-question contract")
    return result
