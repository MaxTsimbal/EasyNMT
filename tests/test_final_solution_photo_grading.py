from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from werkzeug.datastructures import FileStorage

from easynmt_ai import (
    AIContext,
    AIOrchestrator,
    AttachmentRef,
    CriterionGrade,
    EngineResult,
    FinalSolutionGrade,
    FinalSolutionGradingEngine,
    FinalSolutionGradingItem,
)
from easynmt_ai.attachments import AttachmentError, delete_attachment, save_quiz_solution_upload
from easynmt_core.quizzes import (
    CurriculumQuizPhotoUnavailable,
    CurriculumQuizPhotoUnreadable,
    CurriculumQuizService,
    build_deterministic_quiz,
)
from tests.test_ai_written_grading import lesson_fixture
from tests.test_lesson_engine import FakeGateway, ai_response


def attachment(path="/tmp/easynmt-q12-test.jpg"):
    return AttachmentRef(
        id="att-q12-test",
        original_name="solution.jpg",
        mime_type="image/jpeg",
        size_bytes=1200,
        stored_path=path,
        kind="image",
    )


def grading_item(question, *, student_text=""):
    return FinalSolutionGradingItem(
        question_id=question.id,
        number=12,
        max_points=3,
        grading_mode=question.grading_mode,
        prompt=question.prompt,
        instruction=question.instruction,
        task=question.task,
        answer_format=question.answer_format,
        skill=question.skill,
        source_text=question.source_text,
        correct_answer=question.correct_answer,
        accepted_answers=question.accepted_answers,
        primary_answers=question.primary_answers,
        secondary_answers=question.secondary_answers,
        scoring_parts=question.scoring_parts,
        student_text=student_text,
    )


def grade_value(question_id, *, points=2, confidence="high", quality="clear", mode="photo"):
    criteria = tuple(
        CriterionGrade(
            label=("Метод", "Кроки", "Відповідь")[index],
            passed=index < points,
            evidence="Є потрібна частина." if index < points else "Цю частину пропущено.",
        )
        for index in range(3)
    )
    return FinalSolutionGrade(
        question_id=question_id,
        awarded_points=points,
        max_points=3,
        confidence=confidence,
        is_fully_correct=points == 3,
        image_quality=quality,
        submission_mode=mode,
        transcription="x = 4; перевірка підстановкою" if quality != "unreadable" else "",
        summary="Розв’язання містить частину правильних кроків.",
        first_error="Пропущено обґрунтування." if points < 3 else "",
        next_step="Додай перевірку фінальної відповіді.",
        criteria=criteria,
    )


def grade_payload(question_id, *, points=2, confidence="high", quality="clear", mode="photo"):
    return grade_value(
        question_id,
        points=points,
        confidence=confidence,
        quality=quality,
        mode=mode,
    ).to_dict()


class FinalSolutionEngineTests(unittest.TestCase):
    def setUp(self):
        self.quiz = build_deterministic_quiz(lesson_fixture())
        self.question = self.quiz.questions[11]
        self.context = AIContext(user_id=1, subject="math", available_tokens=1800)

    def test_item_restricts_photo_grading_to_question_twelve(self):
        item = grading_item(self.question)
        self.assertEqual(item.number, 12)
        with self.assertRaises(ValueError):
            FinalSolutionGradingItem(**{**item.__dict__, "number": 11})

    def test_engine_sends_exactly_one_image_and_strict_schema(self):
        gateway = FakeGateway(ai_response(grade_payload(self.question.id)))
        engine = FinalSolutionGradingEngine(
            AIOrchestrator(_gateway=gateway),
            model="vision-test-model",
            max_output_tokens=1700,
        )

        result = engine.grade(
            context=self.context,
            item=grading_item(self.question),
            attachment=attachment(),
        )

        self.assertTrue(result.success)
        self.assertEqual(result.value.awarded_points, 2)
        self.assertEqual(len(gateway.calls), 1)
        self.assertEqual(gateway.calls[0]["model"], "vision-test-model")
        self.assertEqual(gateway.calls[0]["attachments"], (attachment(),))
        self.assertEqual(gateway.calls[0]["response_format"]["name"], "easynmt_final_solution_grade")

    def test_engine_rejects_inconsistent_photo_metadata(self):
        payload = grade_payload(self.question.id, quality="not_provided", mode="text")
        engine = FinalSolutionGradingEngine(
            AIOrchestrator(_gateway=FakeGateway(ai_response(payload))),
        )
        result = engine.grade(
            context=self.context,
            item=grading_item(self.question),
            attachment=attachment(),
        )
        self.assertFalse(result.success)


class FakeFinalGrader:
    enabled = True
    max_output_tokens = 1800

    def __init__(self, grade):
        self.value = grade
        self.calls = []

    def grade(self, *, context, item, attachment=None):
        self.calls.append((context, item, attachment))
        return EngineResult(value=self.value)


class FinalSolutionReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.quiz = build_deterministic_quiz(lesson_fixture())
        self.question = self.quiz.questions[11]
        self.answers = {question.id: question.correct_answer for question in self.quiz.questions}

    def test_photo_only_can_complete_question_twelve_and_receive_vision_points(self):
        self.answers[self.question.id] = ""
        grader = FakeFinalGrader(grade_value(self.question.id, points=2))
        service = CurriculumQuizService(None, None, final_solution_grader=grader)

        resolved = service._resolve_question_grades(
            user_id=1,
            subject="math",
            quiz=self.quiz,
            answers=self.answers,
            final_attachment=attachment(),
        )

        final = resolved[self.question.id]
        self.assertEqual(final.earned, 2)
        self.assertEqual(final.source, "vision")
        self.assertEqual(final.submission_mode, "photo")
        self.assertNotIn("/tmp/", final.answer)
        self.assertEqual(len(grader.calls), 1)

    def test_photo_only_never_silently_becomes_zero_when_vision_is_unavailable(self):
        self.answers[self.question.id] = ""
        service = CurriculumQuizService(None, None, final_solution_grader=None)
        with self.assertRaises(CurriculumQuizPhotoUnavailable):
            service._resolve_question_grades(
                user_id=1,
                subject="math",
                quiz=self.quiz,
                answers=self.answers,
                final_attachment=attachment(),
            )

    def test_unreadable_photo_returns_to_question_twelve(self):
        self.answers[self.question.id] = ""
        grader = FakeFinalGrader(grade_value(
            self.question.id,
            points=0,
            confidence="low",
            quality="unreadable",
        ))
        service = CurriculumQuizService(None, None, final_solution_grader=grader)
        with self.assertRaises(CurriculumQuizPhotoUnreadable):
            service._resolve_question_grades(
                user_id=1,
                subject="math",
                quiz=self.quiz,
                answers=self.answers,
                final_attachment=attachment(),
            )

    def test_low_confidence_photo_with_text_uses_server_text_fallback(self):
        grader = FakeFinalGrader(grade_value(
            self.question.id,
            points=0,
            confidence="low",
            quality="partly_readable",
            mode="photo_and_text",
        ))
        service = CurriculumQuizService(None, None, final_solution_grader=grader)
        resolved = service._resolve_question_grades(
            user_id=1,
            subject="math",
            quiz=self.quiz,
            answers=self.answers,
            final_attachment=attachment(),
        )
        final = resolved[self.question.id]
        self.assertEqual(final.source, "server-text-fallback")
        self.assertEqual(final.earned, 3)
        self.assertEqual(final.submission_mode, "photo_and_text")


class FinalSolutionUploadTests(unittest.TestCase):
    def image_file(self, *, name="solution.png", size=(3200, 1800), file_type="image/png"):
        stream = BytesIO()
        image = Image.new("RGB", size, "white")
        image.save(stream, format="PNG")
        stream.seek(0)
        return FileStorage(stream=stream, filename=name, content_type=file_type)

    def test_upload_is_reencoded_downscaled_and_deleted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            saved = save_quiz_solution_upload(
                self.image_file(),
                temp_dir,
                max_bytes=6 * 1024 * 1024,
                max_dimension=1200,
            )
            self.assertEqual(saved.mime_type, "image/jpeg")
            self.assertTrue(Path(saved.stored_path).exists())
            with Image.open(saved.stored_path) as image:
                self.assertLessEqual(max(image.size), 1200)
                self.assertFalse(bool(image.getexif()))
            delete_attachment(saved)
            self.assertFalse(Path(saved.stored_path).exists())

    def test_upload_rejects_non_image_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bad = FileStorage(stream=BytesIO(b"not an image"), filename="answer.txt", content_type="text/plain")
            with self.assertRaises(AttachmentError):
                save_quiz_solution_upload(bad, temp_dir, max_bytes=1000)


class FinalSolutionUiContractTests(unittest.TestCase):
    def test_only_question_twelve_has_photo_input_and_text_is_optional(self):
        template = Path("templates/curriculum_quiz.html").read_text(encoding="utf-8")
        self.assertIn('enctype="multipart/form-data"', template)
        self.assertEqual(template.count('name="solution_photo"'), 1)
        self.assertIn('data-final-solution="true"', template)
        self.assertIn("if (card.dataset.finalSolution === 'true' && selectedPhoto())", template)
        self.assertIn("Фото обробляється тимчасово й видаляється після перевірки", template)
        self.assertIn("Easy Vision", template)

    def test_result_page_has_vision_and_photo_metadata_badges(self):
        template = Path("templates/curriculum_quiz_result.html").read_text(encoding="utf-8")
        self.assertIn("Easy Vision", template)
        self.assertIn("photo_and_text", template)
        self.assertIn("Фото частково читабельне", template)


if __name__ == "__main__":
    unittest.main()
