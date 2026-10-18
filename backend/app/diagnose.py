"""Day 3: observe and diagnose.

Turns what the learner did (quiz answers, questions asked) into a status for every concept, then
lists the gaps. This is plain code on purpose. The tutor's reasoning about the learner has to be
reproducible and testable, and the facts shown in the UI come from here, never from a model.

Statuses (see schemas.ConceptStatus)
  unseen      no quiz answers and no questions about it
  exploring   the learner asked about it but was never quizzed on it
  struggling  two or more answers, fewer than half right
  solid       the last answers (up to 3) were all right
  shaky       anything else: mixed results, or a single wrong answer
"""
from collections import Counter

from .grounding import norm
from .schemas import ConceptStatus, Gap, Progress, QuizAttempt, TutorConcept

SOLID_WINDOW = 3
STRUGGLING_BELOW = 0.5
NEEDS_WORK = ("shaky", "struggling")


def classify(results: list[bool], asked: int = 0) -> str:
    """Status from one concept's answers (oldest first) and how often the learner asked about it."""
    if not results:
        return "exploring" if asked else "unseen"
    if all(results[-SOLID_WINDOW:]):
        return "solid"
    if len(results) >= 2 and sum(results) / len(results) < STRUGGLING_BELOW:
        return "struggling"
    return "shaky"


def ordered(concepts: list[TutorConcept], study_order: list[str]) -> list[TutorConcept]:
    """Concepts in study order. Unknown ids are ignored and concepts missing from the order go last."""
    by_id = {c.id: c for c in concepts}
    seen: set[str] = set()
    out: list[TutorConcept] = []
    for cid in [*study_order, *(c.id for c in concepts)]:
        if cid in by_id and cid not in seen:
            seen.add(cid)
            out.append(by_id[cid])
    return out


def diagnose(
    concepts: list[TutorConcept],
    study_order: list[str],
    attempts: list[QuizAttempt],
    asked: list[str],
) -> list[ConceptStatus]:
    """One status per concept, in study order."""
    concepts = ordered(concepts, study_order)
    by_name = {norm(c.name): c for c in concepts}

    results: dict[str, list[bool]] = {c.id: [] for c in concepts}
    for a in attempts:
        c = by_name.get(norm(a.concept))
        if c:
            results[c.id].append(a.correct)

    padded = [f" {norm(q[:500])} " for q in asked]
    mentions: Counter[str] = Counter()
    for c in concepts:
        name = norm(c.name)
        mentions[c.id] = sum(1 for q in padded if f" {name} " in q or f" {name}s " in q)

    status = {c.id: classify(results[c.id], mentions[c.id]) for c in concepts}

    out: list[ConceptStatus] = []
    for c in concepts:
        weak = []
        for p in c.prerequisites:
            parent = by_name.get(norm(p))
            if parent and parent.id != c.id and status[parent.id] in NEEDS_WORK and parent.name not in weak:
                weak.append(parent.name)
        n, right = len(results[c.id]), sum(results[c.id])
        out.append(
            ConceptStatus(
                id=c.id,
                name=c.name,
                status=status[c.id],
                attempts=n,
                correct=right,
                accuracy=round(right / n, 3) if n else None,
                asked=mentions[c.id],
                weak_prerequisites=weak,
            )
        )
    return out


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def find_gaps(statuses: list[ConceptStatus], concepts: list[TutorConcept]) -> list[Gap]:
    """Concepts that need work, most urgent first.

    Urgent means struggling, or blocking a later concept that is not solid yet. Ties go to the lower
    accuracy, then to the earlier concept in study order.
    """
    by_name = {norm(c.name): c for c in concepts}
    state = {s.id: s for s in statuses}
    index = {s.id: i for i, s in enumerate(statuses)}

    dependents: dict[str, list[str]] = {s.id: [] for s in statuses}
    for c in concepts:
        if c.id not in state:
            continue
        for p in c.prerequisites:
            parent = by_name.get(norm(p))
            if parent and parent.id != c.id and parent.id in dependents and c.id not in dependents[parent.id]:
                dependents[parent.id].append(c.id)

    gaps: list[Gap] = []
    for s in statuses:
        if s.status not in NEEDS_WORK:
            continue
        blocks = [
            state[d].name for d in sorted(dependents[s.id], key=index.get) if state[d].status != "solid"
        ]
        sentences = [f"{s.correct} of {_plural(s.attempts, 'answer')} right."]
        if s.asked:
            sentences.append(f"You asked {_plural(s.asked, 'question')} about it.")
        if blocks:
            sentences.append(f"It is needed for {', '.join(blocks)}.")
        gaps.append(
            Gap(
                concept_id=s.id,
                concept=s.name,
                severity="high" if s.status == "struggling" or blocks else "medium",
                detail=" ".join(sentences),
                blocks=blocks,
            )
        )
    gaps.sort(key=lambda g: (g.severity != "high", state[g.concept_id].accuracy or 0.0, index[g.concept_id]))
    return gaps


def summarize(statuses: list[ConceptStatus]) -> Progress:
    counts = Counter(s.status for s in statuses)
    total = len(statuses)
    return Progress(
        total=total,
        solid=counts["solid"],
        shaky=counts["shaky"],
        struggling=counts["struggling"],
        exploring=counts["exploring"],
        unseen=counts["unseen"],
        percent=round(100 * counts["solid"] / total) if total else 0,
    )
