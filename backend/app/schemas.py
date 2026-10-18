"""Data models.

Layers:
  * LLM* models are what we ask Gemini to return (kept simple for structured output).
  * The remaining models are what the API returns, after every quote has been
    verified against the real transcript.
  * *Request models validate what the browser sends.
"""
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

MAX_TRANSCRIPT_CHARS = 300_000


# --------------------------------------------------------------------------
# What Gemini returns
# --------------------------------------------------------------------------
class LLMEvidence(BaseModel):
    segment_id: int = Field(
        description="Integer id from the [S<id>] tag of the segment the quote comes from."
    )
    quote: str = Field(
        description="Verbatim quote copied from that segment, at most 25 words."
    )


class LLMConcept(BaseModel):
    name: str
    definition: str = Field(
        description="One or two plain-language sentences, based only on the transcript."
    )
    importance: str = Field(description="Exactly one of: core, supporting")
    difficulty: str = Field(description="Exactly one of: beginner, intermediate, advanced")
    prerequisites: list[str] = Field(
        description="Exact names of other concepts in this list to learn first. Empty if none."
    )
    evidence: list[LLMEvidence] = Field(
        description="1 to 3 verbatim quotes from the transcript supporting this concept."
    )


class LLMAnalysis(BaseModel):
    title: str
    one_sentence_summary: str
    summary: str
    key_takeaways: list[str]
    learning_objectives: list[str]
    concepts: list[LLMConcept]


class LLMAnswer(BaseModel):
    answerable: bool = Field(
        description="True only if the transcript contains enough information to answer."
    )
    answer: str = Field(
        description="The answer, or a short note that the video does not cover the question."
    )
    citations: list[LLMEvidence] = Field(
        description="1 to 3 verbatim quotes from the transcript that support the answer. "
        "Empty when answerable is false."
    )
    follow_ups: list[str] = Field(
        description="2 or 3 short follow-up questions the transcript can answer."
    )


class LLMQuizQuestion(BaseModel):
    concept: str = Field(description="Exact name of the concept being tested.")
    question: str
    options: list[str] = Field(description="Exactly 4 answer options.")
    correct_index: int = Field(description="Zero-based index of the correct option.")
    explanation: str = Field(
        description="One or two sentences on why the answer is correct, using the transcript."
    )
    evidence: LLMEvidence = Field(
        description="Verbatim quote from the transcript that proves the correct answer."
    )


class LLMQuiz(BaseModel):
    questions: list[LLMQuizQuestion]


class LLMLesson(BaseModel):
    explanation: str = Field(
        description="3-6 plain-language sentences that teach the concept, using only the transcript."
    )
    key_points: list[str] = Field(description="2-4 short takeaways.")
    citations: list[LLMEvidence] = Field(
        description="1 to 3 verbatim quotes from the transcript that the explanation relies on."
    )


# --------------------------------------------------------------------------
# What the API returns
# --------------------------------------------------------------------------
class Segment(BaseModel):
    id: int
    start: float | None = None
    text: str


class Evidence(BaseModel):
    segment_id: int | None = None
    timestamp: str | None = None
    start_seconds: float | None = None
    quote: str
    # exact: found verbatim | approximate: near-verbatim | unverified: not found in transcript
    match: str
    source_text: str | None = None


class Concept(BaseModel):
    id: str
    name: str
    definition: str
    importance: str
    difficulty: str
    prerequisites: list[str]
    evidence: list[Evidence]
    grounded: bool


class GraphNode(BaseModel):
    id: str
    layer: int  # 0 = no prerequisites; otherwise 1 + the deepest prerequisite's layer


class GraphEdge(BaseModel):
    source: str  # the prerequisite
    target: str  # the concept that needs it


class ConceptGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    study_order: list[str]  # concept ids, prerequisites always before dependents
    ignored_edges: int  # prerequisite links dropped because they formed a cycle


class AnalysisStats(BaseModel):
    segments: int
    concepts: int
    evidence_total: int
    evidence_verified: int
    grounding_score: float
    seconds: float


class AnalysisResult(BaseModel):
    mode: str  # "gemini" or "mock"
    model: str
    title: str
    one_sentence_summary: str
    summary: str
    key_takeaways: list[str]
    learning_objectives: list[str]
    concepts: list[Concept]
    graph: ConceptGraph
    segments: list[Segment]
    stats: AnalysisStats


class AskResult(BaseModel):
    mode: str
    model: str
    question: str
    # grounded: answered and at least one quote verified
    # not_covered: the transcript does not contain the answer
    # unverified: answered, but no quote could be matched to the transcript
    status: Literal["grounded", "not_covered", "unverified"]
    answer: str
    citations: list[Evidence]
    unverified_dropped: int
    follow_ups: list[str]
    seconds: float


class QuizQuestion(BaseModel):
    id: str
    concept: str | None
    question: str
    options: list[str]
    correct_index: int
    explanation: str
    evidence: Evidence


class QuizResult(BaseModel):
    mode: str
    model: str
    questions: list[QuizQuestion]
    dropped: int  # generated questions discarded because their evidence was not in the transcript
    seconds: float


ConceptStatusName = Literal["unseen", "exploring", "shaky", "struggling", "solid"]
TutorAction = Literal[
    "diagnose", "reteach", "review_prerequisite", "practice", "check", "advance", "complete"
]


class ConceptStatus(BaseModel):
    id: str
    name: str
    # unseen: no signal yet | exploring: asked about, never quizzed | shaky: partly right
    # struggling: mostly wrong over 2+ answers | solid: the last answers (up to 3) were all right
    status: ConceptStatusName
    attempts: int
    correct: int
    accuracy: float | None  # correct / attempts, None before the first answer
    asked: int  # questions the learner asked that mention this concept
    weak_prerequisites: list[str]  # names of prerequisites that are shaky or struggling


class Gap(BaseModel):
    concept_id: str
    concept: str
    severity: Literal["high", "medium"]
    detail: str
    blocks: list[str]  # names of concepts that build on this one and are not solid yet


class Lesson(BaseModel):
    explanation: str
    key_points: list[str]
    citations: list[Evidence]
    status: Literal["grounded", "unverified"]  # unverified: no quote could be matched


class QuizTarget(BaseModel):
    focus: list[str]  # concept names, empty = all concepts
    count: int


class NextStep(BaseModel):
    action: TutorAction
    concept_id: str | None
    concept: str | None
    title: str
    reason: str  # the evidence behind the choice, in plain words
    lesson: Lesson | None = None
    lesson_error: str | None = None
    quiz: QuizTarget | None = None
    cta: str


class Progress(BaseModel):
    total: int
    solid: int
    shaky: int
    struggling: int
    exploring: int
    unseen: int
    percent: int


class TutorPlan(BaseModel):
    mode: str
    model: str
    progress: Progress
    concepts: list[ConceptStatus]  # in study order
    gaps: list[Gap]
    trace: list[str]  # observe, diagnose, decide
    next_step: NextStep
    seconds: float


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------
def _limit_segments(segments: list[Segment]) -> list[Segment]:
    if sum(len(s.text) for s in segments) > MAX_TRANSCRIPT_CHARS:
        raise ValueError(f"Transcript is longer than {MAX_TRANSCRIPT_CHARS:,} characters.")
    return segments


class AnalyzeRequest(BaseModel):
    transcript: str = Field(min_length=50)
    title: str | None = None


class TranscribedLine(BaseModel):
    time: str   # when the line starts: MM:SS, or H:MM:SS after the first hour
    text: str


class LLMTranscript(BaseModel):
    """What Gemini returns when it listens to a video."""
    has_speech: bool
    language: str   # language code of the speech, such as "en"
    lines: list[TranscribedLine]


class YouTubeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=300)


class YouTubeResult(BaseModel):
    video_id: str
    title: str | None = None
    transcript: str
    language: str
    generated: bool  # True when the text is machine-made: YouTube's automatic captions, or Gemini's transcription
    source: Literal["captions", "gemini"] = "captions"  # where the text came from


class Turn(BaseModel):
    role: Literal["user", "tutor"]
    text: str = Field(max_length=4000)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    segments: list[Segment] = Field(min_length=1)
    history: list[Turn] = Field(default_factory=list, max_length=12)

    _check = field_validator("segments")(_limit_segments)


class ConceptRef(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    definition: str = Field(default="", max_length=1000)


class QuizRequest(BaseModel):
    segments: list[Segment] = Field(min_length=1)
    concepts: list[ConceptRef] = Field(min_length=1, max_length=30)
    count: int = Field(default=5, ge=1, le=10)
    focus: list[str] = Field(default_factory=list, max_length=10)

    _check = field_validator("segments")(_limit_segments)


class TutorConcept(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    definition: str = Field(default="", max_length=1000)
    prerequisites: list[str] = Field(default_factory=list, max_length=20)


class QuizAttempt(BaseModel):
    concept: str = Field(min_length=1, max_length=200)  # concept name
    correct: bool
    question: str = Field(default="", max_length=600)


class TutorRequest(BaseModel):
    segments: list[Segment] = Field(min_length=1)
    concepts: list[TutorConcept] = Field(min_length=1, max_length=30)
    study_order: list[str] = Field(default_factory=list, max_length=60)  # concept ids
    attempts: list[QuizAttempt] = Field(default_factory=list, max_length=300)  # oldest first
    asked: list[Annotated[str, Field(max_length=500)]] = Field(default_factory=list, max_length=100)

    _check = field_validator("segments")(_limit_segments)
