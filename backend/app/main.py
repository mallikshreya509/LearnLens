import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
SAMPLE_PATH = BACKEND_DIR / "samples" / "sample_transcript.txt"

load_dotenv(BACKEND_DIR / ".env")

from .gemini_client import GeminiError, gemini_available, model_name  # noqa: E402
from .pipeline import analyze_transcript  # noqa: E402
from .qa import answer_question  # noqa: E402
from .quiz import QuizError, generate_quiz  # noqa: E402
from .tutor import plan_next_step  # noqa: E402
from .youtube import YouTubeError, fetch_transcript  # noqa: E402
from .schemas import (  # noqa: E402
    AnalysisResult,
    AnalyzeRequest,
    AskRequest,
    AskResult,
    QuizRequest,
    QuizResult,
    TutorPlan,
    TutorRequest,
    YouTubeRequest,
    YouTubeResult,
)

app = FastAPI(title="LearnLens", version="0.2.0")

# The frontend is normally served by this same app, so CORS only matters when you run
# it from a separate dev server. Set CORS_ORIGINS="http://localhost:5173,https://example.com".
_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
def health():
    live = gemini_available()
    return {
        "status": "ok",
        "mode": "gemini" if live else "mock",
        "model": model_name() if live else "offline-heuristic",
    }


@app.get("/api/sample")
def sample():
    return {
        "title": "How Neural Networks Learn (sample)",
        "transcript": SAMPLE_PATH.read_text(encoding="utf-8"),
    }


# Plain `def` handlers: FastAPI runs them in a worker thread, so blocking Gemini calls are fine.
@app.post("/api/youtube", response_model=YouTubeResult)
def youtube(req: YouTubeRequest):
    """Fetch the captions of a YouTube video as a transcript the learner can review, then analyze."""
    try:
        return fetch_transcript(req.url)
    except YouTubeError as e:
        raise HTTPException(status_code=e.status, detail=str(e))


@app.post("/api/analyze", response_model=AnalysisResult)
def analyze(req: AnalyzeRequest):
    try:
        return analyze_transcript(req.transcript, req.title)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except GeminiError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/ask", response_model=AskResult)
def ask(req: AskRequest):
    try:
        return answer_question(req.segments, req.question, req.history)
    except GeminiError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/quiz", response_model=QuizResult)
def quiz(req: QuizRequest):
    try:
        return generate_quiz(req.segments, req.concepts, req.count, req.focus)
    except (GeminiError, QuizError) as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/tutor/next", response_model=TutorPlan)
def tutor_next(req: TutorRequest):
    """Observe the learner's quiz answers and questions, find the gaps and choose one next step."""
    try:
        return plan_next_step(req)
    except (GeminiError, ValueError) as e:
        raise HTTPException(status_code=502 if isinstance(e, GeminiError) else 422, detail=str(e))


# Mounted last so the /api routes above win. Serves frontend/index.html at "/".
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
