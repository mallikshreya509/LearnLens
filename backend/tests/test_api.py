from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def analyzed():
    sample = client.get("/api/sample").json()["transcript"]
    return client.post("/api/analyze", json={"transcript": sample}).json()


def test_health_reports_mock_mode():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["mode"] == "mock"


def test_frontend_is_served_at_root():
    r = client.get("/")
    assert r.status_code == 200
    assert "LearnLens" in r.text
    assert client.get("/js/main.js").status_code == 200


def test_sample_transcript_analyzes_end_to_end():
    data = analyzed()
    assert data["mode"] == "mock"
    assert data["concepts"] and data["segments"]
    assert data["stats"]["evidence_total"] > 0
    # mock quotes are copied from the transcript, so all must verify
    assert data["stats"]["evidence_verified"] == data["stats"]["evidence_total"]


def test_analysis_includes_a_consistent_graph():
    data = analyzed()
    graph = data["graph"]
    ids = [c["id"] for c in data["concepts"]]
    assert [n["id"] for n in graph["nodes"]] == ids or sorted(n["id"] for n in graph["nodes"]) == sorted(ids)
    assert graph["study_order"] == ids  # concepts are returned in study order
    known = set(ids)
    assert all(e["source"] in known and e["target"] in known for e in graph["edges"])


def test_too_short_transcript_is_rejected():
    r = client.post("/api/analyze", json={"transcript": "too short"})
    assert r.status_code == 422


def test_ask_returns_a_cited_answer():
    data = analyzed()
    r = client.post(
        "/api/ask",
        json={"question": "What is the learning rate?", "segments": data["segments"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "grounded"
    assert body["citations"] and body["citations"][0]["timestamp"]


def test_ask_validates_input():
    segs = analyzed()["segments"]
    assert client.post("/api/ask", json={"question": "hi", "segments": segs}).status_code == 422
    assert client.post("/api/ask", json={"question": "What is dropout?", "segments": []}).status_code == 422
    bad_role = {"question": "What is dropout?", "segments": segs, "history": [{"role": "robot", "text": "x"}]}
    assert client.post("/api/ask", json=bad_role).status_code == 422


def test_quiz_returns_verified_questions():
    data = analyzed()
    r = client.post(
        "/api/quiz",
        json={
            "segments": data["segments"],
            "concepts": [{"name": c["name"], "definition": c["definition"]} for c in data["concepts"]],
            "count": 3,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["questions"]
    for q in body["questions"]:
        assert 0 <= q["correct_index"] < len(q["options"])
        assert q["evidence"]["match"] != "unverified"


def test_quiz_rejects_bad_count():
    data = analyzed()
    body = {"segments": data["segments"], "concepts": [{"name": "Weight"}], "count": 99}
    assert client.post("/api/quiz", json=body).status_code == 422


def tutor_payload(data, attempts=(), asked=()):
    return {
        "segments": data["segments"],
        "concepts": [
            {"id": c["id"], "name": c["name"], "definition": c["definition"], "prerequisites": c["prerequisites"]}
            for c in data["concepts"]
        ],
        "study_order": data["graph"]["study_order"],
        "attempts": list(attempts),
        "asked": list(asked),
    }


def test_tutor_starts_with_a_diagnostic_quiz():
    r = client.post("/api/tutor/next", json=tutor_payload(analyzed()))
    assert r.status_code == 200
    body = r.json()
    assert body["next_step"]["action"] == "diagnose"
    assert body["next_step"]["quiz"] == {"focus": [], "count": 5}
    assert body["progress"]["unseen"] == body["progress"]["total"]


def test_tutor_reteaches_a_struggling_concept_with_a_checked_lesson():
    data = analyzed()
    first = data["concepts"][0]["name"]
    attempts = [{"concept": first, "correct": False, "question": "Why?"}] * 2
    r = client.post("/api/tutor/next", json=tutor_payload(data, attempts))
    assert r.status_code == 200
    step = r.json()["next_step"]
    assert step["action"] == "reteach" and step["concept"] == first
    assert step["lesson"]["citations"] and step["lesson"]["citations"][0]["match"] != "unverified"
    assert step["quiz"]["focus"] == [first]
    assert r.json()["gaps"][0]["concept"] == first


def test_tutor_validates_input():
    data = analyzed()
    ok = tutor_payload(data)
    assert client.post("/api/tutor/next", json={**ok, "concepts": []}).status_code == 422
    assert client.post("/api/tutor/next", json={**ok, "segments": []}).status_code == 422
    assert client.post("/api/tutor/next", json={**ok, "attempts": [{"concept": "x"}]}).status_code == 422
    assert client.post("/api/tutor/next", json={**ok, "asked": ["q" * 501]}).status_code == 422


def test_quiz_focused_on_one_concept_still_has_four_options():
    data = analyzed()
    target = data["concepts"][1]["name"]
    r = client.post(
        "/api/quiz",
        json={
            "segments": data["segments"],
            "concepts": [{"name": c["name"], "definition": c["definition"]} for c in data["concepts"]],
            "count": 3,
            "focus": [target],
        },
    )
    assert r.status_code == 200
    questions = r.json()["questions"]
    assert questions and all(q["concept"] == target for q in questions)
    assert all(len(q["options"]) == 4 for q in questions)
