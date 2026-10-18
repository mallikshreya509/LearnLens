from app.graph import build_graph
from app.schemas import Concept


def concept(name, prereqs=()):
    return Concept(
        id=name.lower().replace(" ", "-"),
        name=name,
        definition="d",
        importance="core",
        difficulty="beginner",
        prerequisites=list(prereqs),
        evidence=[],
        grounded=True,
    )


def layers(g):
    return {n.id: n.layer for n in g.nodes}


def test_chain_gets_increasing_layers():
    g = build_graph([concept("A"), concept("B", ["A"]), concept("C", ["B"])])
    assert layers(g) == {"a": 0, "b": 1, "c": 2}
    assert [(e.source, e.target) for e in g.edges] == [("a", "b"), ("b", "c")]
    assert g.study_order == ["a", "b", "c"]


def test_layer_is_the_longest_path_not_the_shortest():
    # D needs both A (layer 0) and C (layer 2), so it sits at layer 3.
    g = build_graph(
        [concept("A"), concept("B", ["A"]), concept("C", ["B"]), concept("D", ["A", "C"])]
    )
    assert layers(g)["d"] == 3


def test_no_prerequisites_means_everything_on_layer_zero():
    g = build_graph([concept("A"), concept("B")])
    assert layers(g) == {"a": 0, "b": 0}
    assert g.edges == []


def test_unknown_self_and_duplicate_prerequisites_are_ignored():
    g = build_graph([concept("A"), concept("B", ["A", "A", "B", "Nope"])])
    assert [(e.source, e.target) for e in g.edges] == [("a", "b")]
    assert g.ignored_edges == 0


def test_cycle_is_broken_and_counted():
    g = build_graph([concept("A", ["B"]), concept("B", ["A"])])
    assert len(g.edges) == 1
    assert g.ignored_edges == 1
    assert sorted(g.study_order) == ["a", "b"]  # every concept still appears exactly once
    assert sorted(layers(g).values()) == [0, 1]


def test_longer_cycle_still_yields_a_valid_order():
    g = build_graph(
        [concept("A", ["C"]), concept("B", ["A"]), concept("C", ["B"]), concept("D", ["C"])]
    )
    assert g.ignored_edges == 1
    position = {cid: i for i, cid in enumerate(g.study_order)}
    for e in g.edges:
        assert position[e.source] < position[e.target]


def test_study_order_follows_model_order_when_unconstrained():
    g = build_graph([concept("A"), concept("B"), concept("C", ["A"])])
    assert g.study_order == ["a", "b", "c"]


def test_study_order_puts_prerequisites_first_even_if_listed_later():
    g = build_graph([concept("Advanced", ["Basics"]), concept("Basics")])
    assert g.study_order == ["basics", "advanced"]
