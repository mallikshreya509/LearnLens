"""Offline fallbacks so the app runs without an API key.

None of this is intelligent. Concepts are frequent words, answers are the best-matching
transcript sentences and quiz questions are fill-in-the-blank lines. Every response is
labelled mode="mock" and the UI shows a banner.
"""
import random
import re
from collections import Counter

from .schemas import (
    LLMAnalysis,
    LLMAnswer,
    LLMConcept,
    LLMEvidence,
    LLMLesson,
    LLMQuiz,
    LLMQuizQuestion,
    Segment,
)

_STOP = set(
    """about above after again being below between could doing during every further having
    itself little might other should their theirs there these those through under until
    where which while would really thing things going gonna right actually because before
    another around first second today video welcome small large common single number called""".split()
)
_QUESTION_STOP = set(
    """what does how why when where which who whom whose are was were the and for about explain
    tell describe mean means this that these those video transcript with from did can could
    would should into than then there their they you your our give show let make made use used
    using""".split()
)
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]{4,}")
_TOKEN = re.compile(r"[a-z][a-z'-]+")
_SENT = re.compile(r"(?<=[.!?])\s+")


def _quote(sentence: str) -> str:
    return " ".join(sentence.split()[:25])


def _stem(word: str) -> str:
    word = word.removesuffix("'s")
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


# --------------------------------------------------------------------------
# Day 1: analysis
# --------------------------------------------------------------------------
def mock_analysis(segments: list[Segment], title: str | None) -> LLMAnalysis:
    counts: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    for seg in segments:
        for w in _WORD.findall(seg.text.lower()):
            w = _stem(w)
            if w in _STOP:
                continue
            counts[w] += 1
            first_seen.setdefault(w, seg.id)

    top = sorted(counts, key=lambda w: (-counts[w], first_seen[w]))[:6]
    top.sort(key=lambda w: first_seen[w])
    seg_text = {s.id: s.text.lower() for s in segments}

    concepts: list[LLMConcept] = []
    for i, w in enumerate(top):
        evidence: list[LLMEvidence] = []
        for seg in segments:
            if w in seg.text.lower():
                sentence = next((s for s in _SENT.split(seg.text) if w in s.lower()), seg.text)
                evidence.append(LLMEvidence(segment_id=seg.id, quote=_quote(sentence)))
            if len(evidence) == 2:
                break
        # Link to the latest earlier concept mentioned in the same segment where this one first appears.
        earlier = [e for e in top[:i] if e in seg_text[first_seen[w]]]
        concepts.append(
            LLMConcept(
                name=w.capitalize(),
                definition=evidence[0].quote if evidence else "",
                importance="core" if counts[w] >= 3 else "supporting",
                difficulty="intermediate",
                prerequisites=[earlier[-1].capitalize()] if earlier else [],
                evidence=evidence,
            )
        )

    full = " ".join(s.text for s in segments)
    sentences = [s for s in _SENT.split(full) if s.strip()]
    return LLMAnalysis(
        title=title or "Untitled video",
        one_sentence_summary=_quote(sentences[0]) if sentences else "",
        summary=" ".join(sentences[:4]),
        key_takeaways=[_quote(s) for s in sentences[1:5]],
        learning_objectives=[f"Explain what the video says about {c.name.lower()}" for c in concepts[:4]],
        concepts=concepts,
    )


# --------------------------------------------------------------------------
# Day 2: Q&A
# --------------------------------------------------------------------------
def _question_terms(text: str) -> set[str]:
    return {
        _stem(w)
        for w in _TOKEN.findall(text.lower())
        if len(w) >= 3 and w not in _QUESTION_STOP
    }


def mock_answer(segments: list[Segment], question: str) -> LLMAnswer:
    terms = _question_terms(question)
    scored: list[tuple[int, int, str]] = []  # (overlap, -order, best sentence)
    for order, seg in enumerate(segments):
        best_score, best_sentence = 0, ""
        for sentence in _SENT.split(seg.text):
            score = len(terms & _question_terms(sentence))
            if score > best_score:
                best_score, best_sentence = score, sentence
        if best_score:
            scored.append((best_score, -order, best_sentence))

    if not terms or not scored:
        return LLMAnswer(
            answerable=False,
            answer="This video does not seem to cover that. Try asking about a concept from the study guide.",
            citations=[],
            follow_ups=[],
        )

    scored.sort(reverse=True)
    top = [s for s in scored[:2] if s[0] >= max(1, scored[0][0] // 2)]
    sentences = [s[2] for s in top]
    return LLMAnswer(
        answerable=True,
        answer="From the transcript: " + " ".join(sentences),
        citations=[
            LLMEvidence(segment_id=next(sg.id for sg in segments if s in sg.text), quote=_quote(s))
            for s in sentences
        ],
        follow_ups=[],
    )


# --------------------------------------------------------------------------
# Day 2: quiz
# --------------------------------------------------------------------------
def mock_quiz(
    segments: list[Segment], names: list[str], count: int, distractor_pool: list[str] | None = None
) -> LLMQuiz:
    """Fill-in-the-blank questions about `names`. Wrong options come from `distractor_pool`
    (every concept), so a quiz focused on one concept still has something to choose between."""
    questions: list[LLMQuizQuestion] = []
    for name in names:
        if len(questions) >= count:
            break
        pattern = re.compile(rf"\b{re.escape(name)}\w*", re.IGNORECASE)
        found = None
        for seg in segments:
            for sentence in _SENT.split(seg.text):
                if pattern.search(sentence) and len(sentence.split()) <= 45:
                    found = (seg.id, sentence)
                    break
            if found:
                break
        distractors = [n for n in (distractor_pool or names) if n != name]
        if not found or len(distractors) < 2:
            continue
        seg_id, sentence = found
        rng = random.Random(name)
        options = [name] + rng.sample(distractors, min(3, len(distractors)))
        questions.append(
            LLMQuizQuestion(
                concept=name,
                question="Which term completes this line from the transcript? "
                f"“{pattern.sub('_____', sentence)}”",
                options=options,
                correct_index=0,
                explanation=f"The transcript says: “{sentence}”",
                evidence=LLMEvidence(segment_id=seg_id, quote=sentence),
            )
        )
    return LLMQuiz(questions=questions)


# --------------------------------------------------------------------------
# Day 3: tutor lesson
# --------------------------------------------------------------------------
def mock_lesson(segments: list[Segment], name: str, definition: str) -> LLMLesson:
    """Reuse the Q&A matcher: the best transcript lines about the concept."""
    found = mock_answer(segments, f"What is {name}?")
    if found.answerable:
        return LLMLesson(
            explanation=found.answer.removeprefix("From the transcript: "),
            key_points=[],
            citations=found.citations,
        )
    return LLMLesson(
        explanation=definition or f"The video does not explain {name} in detail.",
        key_points=[],
        citations=[],
    )
