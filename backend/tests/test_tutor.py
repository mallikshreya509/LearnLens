import pytest

from app import gemini_client
from app.schemas import LLMEvidence, LLMLesson, QuizAttempt, Segment, TutorConcept, TutorRequest
from app.tutor import plan_next_step

SEGS = [
    Segment(id=1, start=0.0, text="A loss function is a single number that tells us how wrong the network is."),
    Segment(id=2, start=20.0, text="Gradient descent uses the gradient to reduce the loss one step at a time."),
    Segment(id=3, start=45.0, text="Backpropagation computes every gradient using the chain rule."),
    Segment(id=4, start=70.0, text="Overfitting happens when a network memorizes its training data."),
]
ORDER = ["loss", "gd", "bp", "of"]


def concepts():
    return [
        TutorConcept(id="loss", name="Loss function", definition="A number for how wrong the network is."),
        TutorConcept(id="gd", name="Gradient descent", definition="Stepping downhill on the loss.", prerequisites=["Loss function"]),
        TutorConcept(id="bp", name="Backpropagation", definition="Computing gradients.", prerequisites=["Gradient descent"]),
        TutorConcept(id="of", name="Overfitting", definition="Memorizing the training data."),
    ]


def answers(name, *results, question=""):
    return [QuizAttempt(concept=name, correct=r, question=question) for r in results]


def plan(attempts=(), asked=()):
    return plan_next_step(
        TutorRequest(segments=SEGS, concepts=concepts(), study_order=ORDER, attempts=list(attempts), asked=list(asked))
    )


# --------------------------------------------------------------------------
# Decisions (mock mode, no API key)
# --------------------------------------------------------------------------
def test_no_signal_starts_with_a_diagnostic_quiz():
    p = plan()
    step = p.next_step
    assert step.action == "diagnose" and step.concept is None
    assert step.quiz.focus == [] and step.quiz.count == 5
    assert step.lesson is None
    assert p.trace[0].startswith("Observe") and p.trace[-1].startswith("Decide")
    assert p.progress.unseen == 4 and p.progress.percent == 0


def test_struggling_concept_is_retaught_then_rechecked():
    p = plan(answers("Loss function", False, False, question="Why is the loss high?"))
    step = p.next_step
    assert step.action == "reteach" and step.concept == "Loss function"
    assert step.lesson.status == "grounded" and step.lesson.citations
    assert step.lesson.citations[0].timestamp == "00:00"
    assert step.quiz.focus == ["Loss function"] and step.quiz.count == 3
    assert "3 questions" in step.cta
    assert p.gaps[0].concept == "Loss function"
    assert any(line.startswith("Teach") for line in p.trace)


def test_shaky_concept_gets_practice_without_a_lesson():
    step = plan(answers("Loss function", False)).next_step
    assert step.action == "practice" and step.concept == "Loss function"
    assert step.lesson is None
    assert step.quiz.focus == ["Loss function"]


def test_weak_prerequisite_is_the_target_not_the_symptom():
    attempts = answers("Loss function", False, True) + answers("Gradient descent", False, False)
    step = plan(attempts).next_step
    assert step.action == "review_prerequisite"
    assert step.concept == "Loss function"
    assert step.lesson is not None
    assert "Gradient descent builds on Loss function" in step.reason
    assert step.quiz.focus == ["Loss function"]


def test_root_cause_is_found_through_a_chain_of_weak_prerequisites():
    attempts = (
        answers("Loss function", False, True)
        + answers("Gradient descent", False, True)
        + answers("Backpropagation", False, False)
    )
    step = plan(attempts).next_step
    assert step.action == "review_prerequisite" and step.concept == "Loss function"


def test_a_prerequisite_loop_does_not_hang_or_crash():
    cs = [
        TutorConcept(id="a", name="A", prerequisites=["B"]),
        TutorConcept(id="b", name="B", prerequisites=["A"]),
    ]
    p = plan_next_step(
        TutorRequest(
            segments=SEGS, concepts=cs, study_order=["a", "b"],
            attempts=answers("A", False, False) + answers("B", False, False),
        )
    )
    assert p.next_step.concept in ("A", "B")


def test_gaps_come_before_new_material():
    attempts = answers("Loss function", True, True, True) + answers("Gradient descent", False)
    assert plan(attempts).next_step.action == "practice"


def test_asked_about_concepts_are_introduced_before_unseen_ones():
    step = plan(asked=["What is overfitting exactly?"]).next_step
    assert step.action == "advance" and step.concept == "Overfitting"
    assert "asked about" in step.reason
    assert step.lesson is not None
    assert step.quiz.count == 2


def test_next_unseen_concept_follows_the_study_order():
    step = plan(answers("Loss function", True, True, True)).next_step
    assert step.action == "advance" and step.concept == "Gradient descent"


def test_one_lucky_answer_triggers_a_double_check_when_nothing_is_left():
    attempts = []
    for c in concepts():
        attempts += answers(c.name, True)
    step = plan(attempts).next_step
    assert step.action == "check" and step.concept == "Loss function"
    assert step.quiz.count == 2


def test_everything_solid_completes_the_course():
    attempts = []
    for c in concepts():
        attempts += answers(c.name, True, True)
    p = plan(attempts)
    assert p.next_step.action == "complete"
    assert p.next_step.quiz is None and p.next_step.lesson is None
    assert p.progress.percent == 100 and p.gaps == []


def test_answers_for_unknown_concepts_are_ignored():
    assert plan(answers("Quantum tunnelling", False, False)).next_step.action == "diagnose"


def test_plan_reports_every_concept_in_study_order():
    p = plan(answers("Overfitting", True))
    assert [c.id for c in p.concepts] == ORDER
    assert p.mode == "mock"


# --------------------------------------------------------------------------
# Lessons written by Gemini (faked), and what happens when it misbehaves
# --------------------------------------------------------------------------
@pytest.fixture
def fake_gemini(monkeypatch):
    holder = {}
    monkeypatch.setattr(gemini_client, "gemini_available", lambda: True)

    def fake(schema, system, contents, temperature=0.2):
        holder["prompt"] = contents
        holder["schema"] = schema
        if isinstance(holder["reply"], Exception):
            raise holder["reply"]
        return holder["reply"]

    monkeypatch.setattr(gemini_client, "generate_structured", fake)
    return holder


STRUGGLING = answers("Loss function", False, False, question="Why is the loss high when predictions are bad?")


def test_fabricated_quotes_are_dropped_from_a_gemini_lesson(fake_gemini):
    fake_gemini["reply"] = LLMLesson(
        explanation="The loss is one number for how wrong the network is.",
        key_points=["One number", "  "],
        citations=[
            LLMEvidence(segment_id=1, quote="A loss function is a single number that tells us how wrong"),
            LLMEvidence(segment_id=2, quote="Transformers process every token in parallel"),
        ],
    )
    p = plan(STRUGGLING)
    lesson = p.next_step.lesson
    assert p.mode == "gemini"
    assert lesson.status == "grounded"
    assert len(lesson.citations) == 1 and lesson.citations[0].segment_id == 1
    assert lesson.key_points == ["One number"]


def test_a_lesson_with_only_fabricated_quotes_is_marked_unverified(fake_gemini):
    fake_gemini["reply"] = LLMLesson(
        explanation="Confident but unsupported.",
        key_points=[],
        citations=[LLMEvidence(segment_id=1, quote="Transformers process every token in parallel")],
    )
    lesson = plan(STRUGGLING).next_step.lesson
    assert lesson.status == "unverified" and lesson.citations == []


def test_if_gemini_fails_the_step_is_still_returned_without_a_lesson(fake_gemini):
    fake_gemini["reply"] = gemini_client.GeminiError("quota exceeded")
    p = plan(STRUGGLING)
    assert p.next_step.action == "reteach"
    assert p.next_step.lesson is None
    assert "quota exceeded" in p.next_step.lesson_error
    assert p.next_step.quiz.focus == ["Loss function"]
    assert "could not write the lesson" in p.trace[-1]


def test_an_empty_lesson_is_treated_as_a_failure(fake_gemini):
    fake_gemini["reply"] = LLMLesson(explanation="  ", key_points=[], citations=[])
    step = plan(STRUGGLING).next_step
    assert step.lesson is None and step.lesson_error


def test_the_prompt_carries_the_questions_the_learner_got_wrong_and_the_transcript(fake_gemini):
    fake_gemini["reply"] = LLMLesson(explanation="x", key_points=[], citations=[])
    plan(STRUGGLING)
    assert fake_gemini["schema"] is LLMLesson
    assert "CONCEPT: Loss function" in fake_gemini["prompt"]
    assert "Why is the loss high when predictions are bad?" in fake_gemini["prompt"]
    assert "[S1|00:00]" in fake_gemini["prompt"]


def test_gemini_is_not_called_for_steps_that_have_no_lesson(fake_gemini):
    fake_gemini["reply"] = AssertionError("should not be called")
    assert plan().next_step.action == "diagnose"
    assert plan(answers("Loss function", False)).next_step.action == "practice"
