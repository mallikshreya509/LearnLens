from app.grounding import Grounder, build_concepts
from app.schemas import LLMConcept, LLMEvidence, Segment

SEGS = [
    Segment(id=1, start=0.0, text="A loss function is a single number that tells us how wrong the network is."),
    Segment(id=2, start=20.0, text="The learning rate controls the size of each step we take downhill."),
    Segment(id=3, start=45.0, text="Backpropagation uses the chain rule to compute all the gradients efficiently."),
]
g = Grounder(SEGS)


def test_exact_quote_is_verified_with_timestamp():
    ev = g.check(LLMEvidence(segment_id=2, quote="The learning rate controls the size of each step"))
    assert ev.match == "exact"
    assert ev.segment_id == 2
    assert ev.timestamp == "00:20"


def test_wrong_segment_id_is_corrected():
    ev = g.check(LLMEvidence(segment_id=1, quote="uses the chain rule to compute all the gradients"))
    assert ev.match == "exact"
    assert ev.segment_id == 3


def test_case_and_punctuation_are_ignored():
    ev = g.check(LLMEvidence(segment_id=1, quote="a LOSS function is a single number, that tells us"))
    assert ev.match == "exact"


def test_quote_spanning_two_segments_matches():
    ev = g.check(LLMEvidence(segment_id=1, quote="how wrong the network is. The learning rate controls"))
    assert ev.match == "exact"
    assert ev.segment_id == 1


def test_near_verbatim_quote_is_approximate():
    ev = g.check(
        LLMEvidence(segment_id=2, quote="The learning rate controls the size of every step we take downhill")
    )
    assert ev.match == "approximate"
    assert ev.segment_id == 2


def test_paraphrase_is_unverified():
    ev = g.check(LLMEvidence(segment_id=2, quote="The learning rate decides how big each downhill move is"))
    assert ev.match == "unverified"


def test_fabricated_quote_is_unverified_and_has_no_location():
    ev = g.check(
        LLMEvidence(segment_id=2, quote="Transformers use attention to process tokens in parallel")
    )
    assert ev.match == "unverified"
    assert ev.segment_id is None
    assert ev.timestamp is None


def test_build_concepts_cleans_fields_and_flags_grounding():
    concepts = build_concepts(
        [
            LLMConcept(
                name="Loss function",
                definition=" d ",
                importance="CORE",
                difficulty="weird",
                prerequisites=[],
                evidence=[LLMEvidence(segment_id=1, quote="A loss function is a single number that tells us")],
            ),
            LLMConcept(
                name="Gradient descent",
                definition="d",
                importance="core",
                difficulty="Beginner",
                prerequisites=["loss function", "Not a concept", "Gradient descent"],
                evidence=[LLMEvidence(segment_id=3, quote="totally made up statement about something else")],
            ),
        ],
        SEGS,
    )
    first, second = concepts
    assert first.importance == "core"
    assert first.difficulty == "intermediate"  # invalid value falls back
    assert first.grounded is True
    assert second.difficulty == "beginner"
    assert second.prerequisites == ["Loss function"]  # unknown + self removed, name canonicalised
    assert second.grounded is False
