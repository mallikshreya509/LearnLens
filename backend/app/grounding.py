"""Evidence grounding.

LLMs sometimes invent or slightly rewrite quotes. Every quote Gemini returns is
checked against the real transcript, so the UI can show which evidence is
verified and the tutor (Day 3) can trust it.
"""
import re
from difflib import SequenceMatcher

from .schemas import Concept, Evidence, LLMConcept, LLMEvidence, Segment
from .transcript import format_ts

APPROX_THRESHOLD = 0.8
ALLOWED_IMPORTANCE = {"core", "supporting"}
ALLOWED_DIFFICULTY = {"beginner", "intermediate", "advanced"}
_NORM_RE = re.compile(r"[\W_]+")


def norm(text: str) -> str:
    """Lowercase and strip punctuation/whitespace differences."""
    return _NORM_RE.sub(" ", text.lower()).strip()


class Grounder:
    def __init__(self, segments: list[Segment]):
        self.by_id = {s.id: s for s in segments}
        normalized = [norm(s.text) for s in segments]
        # (first_segment_id, text, is_pair): every single segment plus every adjacent
        # pair, so quotes that straddle a segment boundary still match. Single
        # segments always rank ahead of pairs so the reported location is the
        # segment the quote actually lives in.
        self._windows: list[tuple[int, str, bool]] = []
        for i, seg in enumerate(segments):
            self._windows.append((seg.id, normalized[i], False))
        for i in range(len(segments) - 1):
            self._windows.append((segments[i].id, f"{normalized[i]} {normalized[i + 1]}", True))

    def check(self, ev: LLMEvidence) -> Evidence:
        quote = ev.quote.strip()
        nq = norm(quote)
        hint = ev.segment_id if ev.segment_id in self.by_id else None

        if len(nq) >= 8:
            padded = f" {nq} "
            # Single segments first, then pairs; within each, the model's own pick first.
            ordered = sorted(self._windows, key=lambda w: (w[2], w[0] != hint))

            # 1. Exact match.
            for seg_id, text, _ in ordered:
                if padded in f" {text} ":
                    return self._make(seg_id, quote, "exact")

            # 2. Near-verbatim match (a word or two changed). A pair of segments must
            # beat the best single segment by a clear margin to be preferred.
            qwords = set(nq.split())
            best_cov, best_id = 0.0, None
            for seg_id, text, is_pair in ordered:
                if len(qwords & set(text.split())) / len(qwords) < 0.5:
                    continue
                blocks = SequenceMatcher(None, nq, text, autojunk=False).get_matching_blocks()
                coverage = sum(b.size for b in blocks) / len(nq)
                if coverage > best_cov + (0.05 if is_pair else 1e-9):
                    best_cov, best_id = coverage, seg_id
            if best_id is not None and best_cov >= APPROX_THRESHOLD:
                return self._make(best_id, quote, "approximate")

        return self._make(None, quote, "unverified")

    def _make(self, seg_id: int | None, quote: str, match: str) -> Evidence:
        seg = self.by_id.get(seg_id) if seg_id is not None else None
        return Evidence(
            segment_id=seg.id if seg else None,
            timestamp=format_ts(seg.start) if seg else None,
            start_seconds=seg.start if seg else None,
            quote=quote,
            match=match,
            source_text=seg.text if seg else None,
        )


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "concept"


def build_concepts(llm_concepts: list[LLMConcept], segments: list[Segment]) -> list[Concept]:
    grounder = Grounder(segments)
    names = {c.name.strip().lower(): c.name.strip() for c in llm_concepts if c.name.strip()}
    concepts: list[Concept] = []
    used_ids: set[str] = set()

    for c in llm_concepts:
        name = c.name.strip()
        if not name:
            continue
        base = _slug(name)
        cid, n = base, 2
        while cid in used_ids:
            cid, n = f"{base}-{n}", n + 1
        used_ids.add(cid)

        prerequisites: list[str] = []
        for p in c.prerequisites:
            canon = names.get(p.strip().lower())
            if canon and canon != name and canon not in prerequisites:
                prerequisites.append(canon)

        evidence = [grounder.check(e) for e in c.evidence if e.quote.strip()]
        importance = c.importance.strip().lower()
        difficulty = c.difficulty.strip().lower()
        concepts.append(
            Concept(
                id=cid,
                name=name,
                definition=c.definition.strip(),
                importance=importance if importance in ALLOWED_IMPORTANCE else "supporting",
                difficulty=difficulty if difficulty in ALLOWED_DIFFICULTY else "intermediate",
                prerequisites=prerequisites,
                evidence=evidence,
                grounded=any(e.match != "unverified" for e in evidence),
            )
        )
    return concepts
