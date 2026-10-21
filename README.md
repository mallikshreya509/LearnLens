# LearnLens

Paste an educational video transcript, or a YouTube link, and get a study guide where every quote is checked against the source,
plus a concept map, grounded Q&A, quizzes and a tutor that finds your gaps and picks your next step.

## Features

| Feature | What it does |
|---|---|
| **Intelligent Video Summarization** | Turns a transcript (pasted, or read from a YouTube link; plain text, timestamped lines, SRT or VTT) into a one-sentence summary, a short summary, key takeaways and learning objectives. |
| **Concept Mapping** | Pulls out the key concepts, rates each for importance and difficulty, links them by prerequisite, puts them in study order and draws the map. Select a concept to see what it needs and what builds on it. |
| **AI-Generated Quizzes** | Multiple-choice questions written from the transcript, across the whole video or on one concept. Each answer comes with an explanation and the line in the video that supports it. |
| **Agentic AI Tutor** | Reads your quiz answers and questions, diagnoses each concept and chooses the next learning step: assess (check, practice, double-check, next concept), explain (re-teach with a short lesson from the video) or revise (go back to the weak prerequisite). It shows the evidence behind each choice. |
| **Timestamped Evidence Retrieval** | Concepts, answers, quiz explanations and lessons all cite quotes from the transcript. Each quote is matched to its line and timestamp, and selecting it highlights that line. Quotes that cannot be found are removed or labelled, never shown as verified. |
| **Learning Progress and Knowledge-Gap Tracking** | Records every quiz answer, shows each concept as solid, shaky or struggling, ranks the gaps with the reason for each, and colours the concept map by what needs review. **Progress is saved in the browser**, so you can close the tab and resume later without paying for a new analysis. |

Plus **Ask the video**: questions answered only from the transcript, with the lines the answer relies on.



```
learnlens/
├── Dockerfile              one container: API + frontend
├── DEPLOYMENT.md           Cloud Run deployment steps (Firebase Hosting optional)
├── .dockerignore  .gcloudignore
├── backend/                FastAPI + Gemini. All the logic lives here.
│   ├── app/
│   │   ├── main.py             routes, CORS, optionally serves ../frontend
│   │   ├── pipeline.py         analyze: transcript → concepts → graph
│   │   ├── transcript.py       text / timestamps / SRT / VTT → numbered segments
│   │   ├── youtube.py          YouTube link → captions, or Gemini listening to the video → timestamped transcript
│   │   ├── gemini_client.py    one structured-output helper + the analysis prompt
│   │   ├── grounding.py        checks every quote against the transcript
│   │   ├── graph.py            prerequisites → layers, study order (cycles removed)
│   │   ├── qa.py               grounded Q&A
│   │   ├── quiz.py             quiz generation and validation
│   │   ├── diagnose.py         tutor: quiz answers + questions → concept statuses and gaps
│   │   ├── tutor.py            tutor: decide the next step, write a lesson when one is needed
│   │   ├── mock.py             offline fallback when there is no API key
│   │   └── schemas.py          request / response / Gemini schemas
│   ├── samples/sample_transcript.txt
│   ├── tests/                  158 tests, never call Gemini or YouTube
│   ├── requirements.txt        what the app needs to run
│   ├── requirements-dev.txt    adds the test tools
│   └── .env.example
└── frontend/               Plain HTML + CSS + ES modules. No build step.
    ├── index.html
    ├── config.js               where the backend lives
    ├── css/styles.css
    └── js/                     main, api, state, store, dom, reader, overview, map, ask, quiz, tutor
```

## Run it locally

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then add your GEMINI_API_KEY
uvicorn app.main:app --reload
```

Open http://localhost:8000. The backend also serves the `frontend/` folder, so this is all you need.

**Frontend on its own server** (to keep the two truly separate):

```bash
cd frontend
python3 -m http.server 5173     # open http://localhost:5173
```

On port 5173 the frontend talks to `http://localhost:8000` automatically. For any other host, set
`window.LEARNLENS_API` in `frontend/config.js` and add the frontend's origin to `CORS_ORIGINS` in `backend/.env`.

Without a Gemini key the app runs in **offline demo mode** (a keyword heuristic, labelled in the UI) so you can
always click through the whole flow. Real analysis needs a key from https://aistudio.google.com/apikey.

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest
```


## The tutor

The loop is **observe → diagnose → decide → teach**, and it restarts whenever the learner answers or asks something.

| Step | What happens | Who does it |
|---|---|---|
| Observe | Reads every quiz answer and every question the learner asked | Browser sends it |
| Diagnose | Gives each concept a status and lists the gaps, most urgent first | Plain code (`diagnose.py`) |
| Decide | Picks one next step and writes the reason from the numbers | Plain code (`tutor.py`) |
| Teach | When the step is a lesson, writes it from the transcript and checks every quote | Gemini, then `grounding.py` |

Concept statuses: **unseen** (no signal), **exploring** (asked about, never quizzed), **struggling** (fewer than half
right over 2+ answers), **solid** (the last 3 answers were right), **shaky** (anything else).

Next steps the tutor can choose:

| Step | Kind | When |
|---|---|---|
| Check | assess | Nothing to go on yet: a short quiz across the video |
| Back to basics | revise | A struggling concept builds on a prerequisite that is also weak: fix that first |
| Re-teach | explain | A concept is struggling: a short lesson from the video, aimed at the questions missed |
| Practice | assess / revise | A concept is shaky: more questions on it |
| Next concept | assess | No gaps: move to the next concept the learner has not been checked on |
| Double-check | assess | Every answer so far is right, but one concept has only a single answer |
| Done | none | All concepts solid |

Decisions are deliberately made by code, not by the model, so each one can be explained ("How the tutor decided")
and tested. Gemini only writes lesson text, and a lesson whose quotes cannot be found in the transcript is flagged.

## What the other tabs do

| Tab | What it does | How it stays honest |
|---|---|---|
| Concept map | Prerequisites drawn top to bottom. Select a concept to see what it needs and what builds on it. | Loops in the model's prerequisite links are dropped, and the UI says how many. Quiz results tint the nodes. |
| Ask the video | Questions answered only from the transcript, with the quotes they rely on. | Every cited quote is matched to the transcript. Unmatched quotes are removed. If nothing matches, the answer is flagged. If the video doesn't cover it, it says so. |
| Quiz | Multiple choice written from the transcript, explanations with a source line, per-concept results. | Questions whose evidence isn't in the transcript are discarded. Options are de-duplicated and shuffled server-side. |

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | `mode` (`gemini` or `mock`) and model |
| GET | `/api/sample` | Sample transcript |
| POST | `/api/youtube` | `{url}` → `transcript` (timestamped lines), `title`, `language`, `generated`, `source` (`captions` or `gemini`). Errors are plain sentences |
| POST | `/api/analyze` | `{transcript, title?}` → summary, concepts, `graph`, `segments`, `stats` |
| POST | `/api/ask` | `{question, segments, history?}` → `status` (`grounded`, `not_covered`, `unverified`), `answer`, `citations`, `follow_ups` |
| POST | `/api/quiz` | `{segments, concepts:[{name, definition}], count, focus?}` → `questions` with `correct_index`, `explanation`, `evidence` |
| POST | `/api/tutor/next` | `{segments, concepts, study_order, attempts, asked}` → `progress`, per-concept `concepts` statuses, `gaps`, `trace`, `next_step` (with `lesson` when one was written) |

The backend keeps no state. The browser sends the transcript segments, quiz answers and questions with each request,
and keeps the learner's progress itself (`frontend/js/store.js`).

### Saved progress

- Pasting the same transcript again, or choosing **Resume** on the start page, restores the analysis, quiz answers,
  Q&A thread and concept-map colours without calling Gemini again.
- **Analyze again** runs a fresh analysis and clears the saved progress for that transcript, after one confirmation.
- If the browser blocks storage, the app still works and says "Not saved" at the top of the workspace.

## Config (`backend/.env`, or environment variables on Cloud Run)

| Variable | Default | Notes |
|---|---|---|
| `GEMINI_API_KEY` | none | Missing key means offline demo mode |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Any Gemini model with structured output |
| `LEARNLENS_MOCK` | `0` | `1` forces offline mode |
| `CORS_ORIGINS` | `localhost:5173` | Comma separated, only for a separate frontend host |
| `YOUTUBE_LANGS` | `en` | Preferred caption languages, comma separated. Any other language is used if none match |
| `YOUTUBE_METHOD` | `auto` | `auto` tries captions, then Gemini listening to the video. `captions` or `gemini` uses one route only |
| `YOUTUBE_GEMINI_TIMEOUT_S` | `240` | How long Gemini may take to listen to a video. Keep it under the Cloud Run request timeout (300 s) |
| `YOUTUBE_MAX_TRANSCRIPTIONS` | `2` | Videos Gemini may transcribe at once per instance. More get "try again in a minute" |
| `YOUTUBE_PROXY_URL` | none | Optional HTTP(S) proxy for caption requests, for when YouTube blocks the server's address |

## Known limits

- **Progress is saved in this browser only.** Quiz answers, the Q&A thread and the analysis are kept in
  `localStorage` (the last 5 transcripts). They do not follow the learner to another browser or device, and clearing
  site data or a private window loses them. An unfinished quiz and the tutor's plan are not saved; the plan is
  recomputed from the saved answers. Syncing across devices needs sign-in and a database (Firestore would fit).
- Transcripts up to 300,000 characters go to Gemini in one request. 
- **YouTube links use two routes.** Captions first (exact, free, but YouTube often blocks them from cloud
  servers). If that fails, Gemini listens to the video, which works from Cloud Run and for videos without
  captions, but only for **public** videos (not private or unlisted), is slower (a minute or two for long videos),
  costs tokens (about 100 per second of video, per Google's docs) and produces a machine transcript that can contain
  mistakes. The interface says which route was used. The Gemini route is a Google preview feature. It has not been
  run against real YouTube in this project's tests, so try one link on the deployed URL before a demo.
- A concept's status comes only from quiz answers and questions that name it. Reading the overview does not count.

## Future improvement plan

LearnLens is an MVP. This is what we would build next, in priority order. Items marked *(measure first)* need real-world numbers before we commit to them.

### 1. Speed and cost
Every Q&A, quiz and lesson call currently sends the full transcript to Gemini. That is simple and accurate, but slow and token-heavy on long videos.

| Improvement | Why |
|---|---|
| **Server-side cache by transcript hash** | A repeat analysis of the same video costs zero LLM calls. |
| **Retrieval for Q&A**: send only the top relevant segments, not the whole transcript | Cuts input tokens sharply on long videos. Citations stay verbatim and are still verified against the full transcript. |
| **Pre-generated quiz pool** created during analysis | Removes most separate quiz calls and the tutor's quiz round-trips. |
| **Streaming responses** | The first words appear in about a second instead of after the whole answer. |
| **Gemini context caching** *(measure first)* | Reuse an uploaded transcript across calls at a lower token price. |
| **Lower thinking budget / lighter model for simple calls** *(measure first)* | Faster follow-up questions and quiz generation. |

### 2. Long videos
- Today: transcripts over 300,000 characters (about 5 hours of speech) are rejected with a clear error.
- Next: **map-reduce analysis**. Split into overlapping chunks, extract concepts in parallel, then merge, dedupe and build the concept graph in one final call.
- Grounding stays the same: every quote is checked against the full transcript.



