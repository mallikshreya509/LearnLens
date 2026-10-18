import random

import pytest

from app import gemini_client
from app.quiz import QuizError, generate_quiz
from app.schemas import ConceptRef, LLMEvidence, LLMQuiz, LLMQuizQuestion, Segment

SEGS = [
    Segment(id=1, start=0.0, text="A loss function is a single number that tells us how wrong the network is."),
    Segment(id=2, start=20.0, text="The learning rate controls the size of each step we take downhill."),
    Segment(id=3, start=45.0, text="Backpropagation uses the chain rule to compute all the gradients efficiently."),
]
CONCEPTS = [ConceptRef(name=n) for n in ("Loss function", "Learning rate", "Backpropagation", "Chain rule")]


def question(**over):
    base = dict(
        concept="Learning rate",
        question="What does the learning rate control?",
        options=["Step size", "Number of layers", "Dataset size", "Loss value"],
        correct_index=0,
        explanation="It sets the step size.",
        evidence=LLMEvidence(segment_id=2, quote="The learning rate controls the size of each step"),
    )
    base.update(over)
    return LLMQuizQuestion(**base)


@pytest.fixture
def fake_gemini(monkeypatch):
    holder = {}
    monkeypatch.setattr(gemini_client, "gemini_available", lambda: True)
    monkeypatch.setattr(
        gemini_client, "generate_structured", lambda schema, system, contents, temperature=0.2: holder["reply"]
    )
    return holder


def test_mock_quiz_builds_grounded_questions():
    r = generate_quiz(SEGS, CONCEPTS, count=3)
    assert r.mode == "mock"
    assert 1 <= len(r.questions) <= 3
    for q in r.questions:
        assert q.evidence.match != "unverified"
        assert q.options[q.correct_index].lower() in q.question.lower() or "_____" in q.question
        assert len(set(q.options)) == len(q.options)


def test_correct_answer_is_tracked_through_the_shuffle(fake_gemini):
    fake_gemini["reply"] = LLMQuiz(questions=[question()])
    for seed in range(20):
        r = generate_quiz(SEGS, CONCEPTS, rng=random.Random(seed))
        q = r.questions[0]
        assert q.options[q.correct_index] == "Step size"
        assert sorted(q.options) == ["Dataset size", "Loss value", "Number of layers", "Step size"]


def test_shuffle_actually_moves_the_correct_answer(fake_gemini):
    fake_gemini["reply"] = LLMQuiz(questions=[question()])
    positions = {
        generate_quiz(SEGS, CONCEPTS, rng=random.Random(s)).questions[0].correct_index for s in range(30)
    }
    assert len(positions) > 1


def test_question_with_fabricated_evidence_is_dropped(fake_gemini):
    bad = question(evidence=LLMEvidence(segment_id=2, quote="Transformers process every token in parallel"))
    fake_gemini["reply"] = LLMQuiz(questions=[question(), bad])
    r = generate_quiz(SEGS, CONCEPTS)
    assert len(r.questions) == 1
    assert r.dropped == 1


def test_invalid_questions_are_dropped(fake_gemini):
    fake_gemini["reply"] = LLMQuiz(
        questions=[
            question(correct_index=9),
            question(options=["Same", "same", "SAME", "Other"], correct_index=0),
            question(question="  "),
            question(),
        ]
    )
    r = generate_quiz(SEGS, CONCEPTS)
    assert len(r.questions) == 1
    assert r.dropped == 3


def test_duplicate_options_are_merged_and_correct_answer_survives(fake_gemini):
    fake_gemini["reply"] = LLMQuiz(
        questions=[question(options=["step size", "Step size", "Layers", "Loss value", "Data"], correct_index=1)]
    )
    q = generate_quiz(SEGS, CONCEPTS).questions[0]
    assert len(q.options) == 4
    assert q.options[q.correct_index].lower() == "step size"


def test_more_than_five_options_keeps_the_correct_one(fake_gemini):
    opts = ["A1", "B2", "C3", "D4", "E5", "F6", "G7"]
    fake_gemini["reply"] = LLMQuiz(questions=[question(options=opts, correct_index=6)])
    q = generate_quiz(SEGS, CONCEPTS).questions[0]
    assert len(q.options) == 5
    assert q.options[q.correct_index] == "G7"


def test_concept_name_is_matched_case_insensitively_and_unknown_is_none(fake_gemini):
    fake_gemini["reply"] = LLMQuiz(questions=[question(concept="learning RATE"), question(concept="Mystery")])
    qs = generate_quiz(SEGS, CONCEPTS).questions
    assert [q.concept for q in qs] == ["Learning rate", None]


def test_count_caps_the_result_and_ids_are_sequential(fake_gemini):
    fake_gemini["reply"] = LLMQuiz(questions=[question() for _ in range(4)])
    r = generate_quiz(SEGS, CONCEPTS, count=2)
    assert [q.id for q in r.questions] == ["q1", "q2"]
    assert r.dropped == 2


def test_no_usable_questions_raises(fake_gemini):
    fake_gemini["reply"] = LLMQuiz(questions=[question(correct_index=7)])
    with pytest.raises(QuizError):
        generate_quiz(SEGS, CONCEPTS)
