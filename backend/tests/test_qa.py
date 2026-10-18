import pytest

from app import gemini_client
from app.qa import answer_question
from app.schemas import LLMAnswer, LLMEvidence, Segment, Turn

SEGS = [
    Segment(id=1, start=0.0, text="A loss function is a single number that tells us how wrong the network is."),
    Segment(id=2, start=20.0, text="The learning rate controls the size of each step we take downhill."),
    Segment(id=3, start=45.0, text="Backpropagation uses the chain rule to compute all the gradients efficiently."),
]


@pytest.fixture
def fake_gemini(monkeypatch):
    """Route answer_question through a fake Gemini that returns whatever the test sets."""
    holder = {}
    monkeypatch.setattr(gemini_client, "gemini_available", lambda: True)

    def fake(schema, system, contents, temperature=0.2):
        holder["prompt"] = contents
        return holder["reply"]

    monkeypatch.setattr(gemini_client, "generate_structured", fake)
    return holder


def test_mock_answer_cites_the_matching_segment():
    r = answer_question(SEGS, "What does the learning rate do?")
    assert r.mode == "mock"
    assert r.status == "grounded"
    assert r.citations[0].segment_id == 2
    assert r.citations[0].timestamp == "00:20"


def test_mock_answer_says_not_covered_for_unrelated_questions():
    r = answer_question(SEGS, "Who won the football world cup?")
    assert r.status == "not_covered"
    assert r.citations == []


def test_verified_citation_makes_answer_grounded(fake_gemini):
    fake_gemini["reply"] = LLMAnswer(
        answerable=True,
        answer="It sets how big each downhill step is.",
        citations=[LLMEvidence(segment_id=2, quote="The learning rate controls the size of each step")],
        follow_ups=["What if it is too large?", " "],
    )
    r = answer_question(SEGS, "What is the learning rate?")
    assert r.mode == "gemini"
    assert r.status == "grounded"
    assert r.unverified_dropped == 0
    assert r.follow_ups == ["What if it is too large?"]


def test_fabricated_citations_are_dropped_and_counted(fake_gemini):
    fake_gemini["reply"] = LLMAnswer(
        answerable=True,
        answer="Mixed.",
        citations=[
            LLMEvidence(segment_id=2, quote="The learning rate controls the size of each step"),
            LLMEvidence(segment_id=1, quote="Transformers process every token in parallel"),
        ],
        follow_ups=[],
    )
    r = answer_question(SEGS, "q?? ok")
    assert r.status == "grounded"
    assert len(r.citations) == 1
    assert r.unverified_dropped == 1


def test_answer_with_only_fabricated_citations_is_flagged_unverified(fake_gemini):
    fake_gemini["reply"] = LLMAnswer(
        answerable=True,
        answer="Confident but unsupported.",
        citations=[LLMEvidence(segment_id=1, quote="Transformers process every token in parallel")],
        follow_ups=[],
    )
    r = answer_question(SEGS, "What do transformers do?")
    assert r.status == "unverified"
    assert r.citations == []
    assert r.unverified_dropped == 1


def test_not_answerable_never_shows_citations(fake_gemini):
    fake_gemini["reply"] = LLMAnswer(
        answerable=False,
        answer="The video does not cover that.",
        citations=[LLMEvidence(segment_id=1, quote="A loss function is a single number")],
        follow_ups=[],
    )
    r = answer_question(SEGS, "What is dropout?")
    assert r.status == "not_covered"
    assert r.citations == []


def test_duplicate_citations_are_collapsed(fake_gemini):
    same = LLMEvidence(segment_id=2, quote="The learning rate controls the size of each step")
    fake_gemini["reply"] = LLMAnswer(answerable=True, answer="x", citations=[same, same], follow_ups=[])
    assert len(answer_question(SEGS, "What is the learning rate?").citations) == 1


def test_history_is_sent_to_the_model(fake_gemini):
    fake_gemini["reply"] = LLMAnswer(answerable=False, answer="n/a", citations=[], follow_ups=[])
    answer_question(
        SEGS,
        "And why does it matter?",
        [Turn(role="user", text="What is the learning rate?"), Turn(role="tutor", text="It sets the step size.")],
    )
    assert "Learner: What is the learning rate?" in fake_gemini["prompt"]
    assert "Tutor: It sets the step size." in fake_gemini["prompt"]
    assert "[S2|00:20]" in fake_gemini["prompt"]
