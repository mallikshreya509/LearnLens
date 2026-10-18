import pytest

from app.diagnose import classify, diagnose, find_gaps, ordered, summarize
from app.schemas import QuizAttempt, TutorConcept


def C(cid, name, *prereqs):
    return TutorConcept(id=cid, name=name, prerequisites=list(prereqs))


def A(name, *results):
    return [QuizAttempt(concept=name, correct=r) for r in results]


@pytest.mark.parametrize(
    "results, asked, expected",
    [
        ([], 0, "unseen"),
        ([], 2, "exploring"),
        ([True], 0, "solid"),
        ([False], 0, "shaky"),  # one wrong answer is not enough to call it struggling
        ([True, True, True], 0, "solid"),
        ([False, True], 0, "shaky"),
        ([True, False], 0, "shaky"),  # exactly half right is shaky, not struggling
        ([False, False], 0, "struggling"),
        ([True, False, False], 0, "struggling"),
        ([False, False, True], 0, "struggling"),
        ([False, False, True, True, True], 0, "solid"),  # the last three decide
        ([True, True, False], 0, "shaky"),
        ([False], 5, "shaky"),  # quiz answers beat questions asked
    ],
)
def test_classify(results, asked, expected):
    assert classify(results, asked) == expected


def test_ordered_drops_unknown_ids_and_appends_missing_concepts():
    cs = [C("a", "A"), C("b", "B"), C("c", "C")]
    assert [c.id for c in ordered(cs, ["c", "zzz", "a"])] == ["c", "a", "b"]
    assert [c.id for c in ordered(cs, [])] == ["a", "b", "c"]


def test_attempts_match_names_ignoring_case_and_punctuation_and_unknown_names_are_ignored():
    cs = [C("loss", "Loss function"), C("gd", "Gradient descent")]
    attempts = A("  LOSS  function ", False, False) + A("Not a concept", True)
    st = {s.id: s for s in diagnose(cs, ["loss", "gd"], attempts, [])}
    assert st["loss"].status == "struggling"
    assert (st["loss"].attempts, st["loss"].correct, st["loss"].accuracy) == (2, 0, 0.0)
    assert st["gd"].status == "unseen"


def test_questions_are_counted_per_concept_including_plurals():
    cs = [C("w", "Weight"), C("lr", "Learning rate")]
    asked = ["What are weights?", "How does the learning rate matter?", "Why is the learning rate so small?", "hi"]
    st = {s.id: s for s in diagnose(cs, ["w", "lr"], [], asked)}
    assert st["w"].asked == 1 and st["w"].status == "exploring"
    assert st["lr"].asked == 2


def test_weak_prerequisites_are_listed_by_name():
    cs = [C("a", "Loss"), C("b", "Gradient", "Loss"), C("c", "Backprop", "Gradient", "Loss", "Backprop")]
    attempts = A("Loss", False, False) + A("Gradient", True, False) + A("Backprop", False)
    st = {s.id: s for s in diagnose(cs, ["a", "b", "c"], attempts, [])}
    assert st["a"].weak_prerequisites == []
    assert st["b"].weak_prerequisites == ["Loss"]
    assert st["c"].weak_prerequisites == ["Gradient", "Loss"]  # itself is ignored


def test_solid_prerequisites_are_not_weak():
    cs = [C("a", "Loss"), C("b", "Gradient", "Loss")]
    st = diagnose(cs, ["a", "b"], A("Loss", True, True) + A("Gradient", False), [])
    assert st[1].weak_prerequisites == []


def test_gaps_are_ranked_and_list_what_they_block():
    cs = [C("a", "Loss"), C("b", "Gradient", "Loss"), C("c", "Backprop", "Gradient"), C("d", "Dropout")]
    attempts = (
        A("Loss", True, False)          # shaky, blocks Gradient (not solid)
        + A("Gradient", False, False)   # struggling
        + A("Dropout", False)           # shaky, blocks nothing
    )
    st = diagnose(cs, ["a", "b", "c", "d"], attempts, [])
    gaps = find_gaps(st, cs)
    assert [g.concept for g in gaps] == ["Gradient", "Loss", "Dropout"]
    assert [g.severity for g in gaps] == ["high", "high", "medium"]
    by = {g.concept: g for g in gaps}
    assert by["Loss"].blocks == ["Gradient"]
    assert by["Gradient"].blocks == ["Backprop"]
    assert by["Dropout"].blocks == []
    assert by["Loss"].detail == "1 of 2 answers right. It is needed for Gradient."


def test_a_blocked_concept_that_is_solid_does_not_count_as_blocked():
    cs = [C("a", "Loss"), C("b", "Gradient", "Loss")]
    st = diagnose(cs, ["a", "b"], A("Loss", False) + A("Gradient", True, True), [])
    gap = find_gaps(st, cs)[0]
    assert gap.blocks == [] and gap.severity == "medium"


def test_gap_detail_mentions_questions_asked():
    cs = [C("a", "Loss")]
    st = diagnose(cs, ["a"], A("Loss", False, False, True), ["Why is the loss so high?"])
    assert find_gaps(st, cs)[0].detail == "1 of 3 answers right. You asked 1 question about it."


def test_summarize_counts_every_status():
    cs = [C(str(i), n) for i, n in enumerate(["A", "B", "C", "D", "E"])]
    attempts = A("A", True, True) + A("B", False) + A("C", False, False)
    p = summarize(diagnose(cs, [c.id for c in cs], attempts, ["tell me about d"]))
    assert (p.total, p.solid, p.shaky, p.struggling, p.exploring, p.unseen) == (5, 1, 1, 1, 1, 1)
    assert p.percent == 20
