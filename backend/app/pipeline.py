"""Day 1 pipeline: transcript -> summary -> concepts -> verified evidence -> concept graph."""
import time

from .gemini_client import analyze_with_gemini, gemini_available, model_name
from .graph import build_graph
from .grounding import build_concepts
from .mock import mock_analysis
from .schemas import AnalysisResult, AnalysisStats
from .transcript import parse_transcript


def analyze_transcript(raw: str, title: str | None = None) -> AnalysisResult:
    started = time.perf_counter()
    segments = parse_transcript(raw)

    if gemini_available():
        mode, model = "gemini", model_name()
        llm = analyze_with_gemini(segments, title)
    else:
        mode, model = "mock", "offline-heuristic"
        llm = mock_analysis(segments, title)

    concepts = build_concepts(llm.concepts, segments)
    graph = build_graph(concepts)
    # Show concepts in an order where prerequisites always come first.
    by_id = {c.id: c for c in concepts}
    concepts = [by_id[cid] for cid in graph.study_order]

    total = sum(len(c.evidence) for c in concepts)
    verified = sum(1 for c in concepts for e in c.evidence if e.match != "unverified")

    return AnalysisResult(
        mode=mode,
        model=model,
        title=(title or llm.title or "Untitled video").strip(),
        one_sentence_summary=llm.one_sentence_summary.strip(),
        summary=llm.summary.strip(),
        key_takeaways=[t.strip() for t in llm.key_takeaways if t.strip()],
        learning_objectives=[t.strip() for t in llm.learning_objectives if t.strip()],
        concepts=concepts,
        graph=graph,
        segments=segments,
        stats=AnalysisStats(
            segments=len(segments),
            concepts=len(concepts),
            evidence_total=total,
            evidence_verified=verified,
            grounding_score=round(verified / total, 3) if total else 0.0,
            seconds=round(time.perf_counter() - started, 2),
        ),
    )
