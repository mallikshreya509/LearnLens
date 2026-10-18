"""YouTube transcript fetching. The real YouTube is never called: a stand-in client plays its part."""
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient
from youtube_transcript_api import (
    AgeRestricted, CouldNotRetrieveTranscript, IpBlocked, TranscriptsDisabled, VideoUnavailable,
)

from app import youtube
from app.main import app
from app.transcript import parse_transcript

ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize("text", [
    ID,
    f"https://www.youtube.com/watch?v={ID}",
    f"https://www.youtube.com/watch?v={ID}&t=42s&list=PLabc",
    f"https://youtube.com/watch?feature=share&v={ID}",
    f"youtube.com/watch?v={ID}",
    f"https://m.youtube.com/watch?v={ID}",
    f"https://music.youtube.com/watch?v={ID}",
    f"https://youtu.be/{ID}",
    f"https://youtu.be/{ID}?si=abc",
    f"https://www.youtube.com/shorts/{ID}",
    f"https://www.youtube.com/embed/{ID}",
    f"https://www.youtube.com/live/{ID}?feature=share",
    f"  https://www.youtube.com/watch?v={ID}  ",
])
def test_video_id_is_found_in_every_common_link_shape(text):
    assert youtube.parse_video_id(text) == ID


@pytest.mark.parametrize("text", [
    "", "hello", "https://example.com/watch?v=" + ID,
    "https://evil.com/?u=https://youtube.com/watch?v=" + ID,
    "https://youtube.com.evil.com/watch?v=" + ID,
    "https://www.youtube.com/watch?v=short",
    "https://www.youtube.com/",
    "https://www.youtube.com/channel/" + ID,
    "https://www.youtube.com/watch?v=" + ID[:10] + "!",
    "file:///etc/passwd",
])
def test_anything_else_is_rejected(text):
    with pytest.raises(youtube.YouTubeError):
        youtube.parse_video_id(text)


class Track:
    def __init__(self, lang, generated, snippets=None, boom=None):
        self.language_code, self.is_generated = lang, generated
        self._snippets, self._boom = snippets, boom

    def fetch(self):
        if self._boom:
            raise self._boom
        return self._snippets


class Client:
    def __init__(self, tracks=None, boom=None):
        self.tracks, self.boom, self.asked = tracks or [], boom, []

    def list(self, video_id):
        self.asked.append(video_id)
        if self.boom:
            raise self.boom
        return self.tracks


def snip(start, text):
    return NS(start=start, duration=2.0, text=text)


LONG = [snip(i * 4.0, f"Sentence number {i} explains one more idea about gradient descent.") for i in range(12)]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(youtube, "_title", lambda vid: "A Real Title")


def test_manual_captions_beat_auto_generated_ones():
    auto, manual = Track("en", True, LONG), Track("en", False, [snip(0, "manual " * 12)])
    out = youtube.fetch_transcript(ID, Client([auto, manual]))
    assert out["generated"] is False and out["transcript"].startswith("[00:00] manual")


def test_preferred_language_beats_other_languages(monkeypatch):
    monkeypatch.setenv("YOUTUBE_LANGS", "en")
    de, en = Track("de", False, [snip(0, "hallo " * 12)]), Track("en-GB", True, LONG)
    out = youtube.fetch_transcript(ID, Client([de, en]))
    assert out["language"] == "en-GB" and out["generated"] is True


def test_falls_back_to_any_language_when_the_preferred_one_is_missing():
    out = youtube.fetch_transcript(ID, Client([Track("hi", True, LONG)]))
    assert out["language"] == "hi"


def test_result_is_a_timestamped_transcript_the_existing_parser_understands():
    out = youtube.fetch_transcript(f"https://youtu.be/{ID}", Client([Track("en", False, LONG)]))
    assert out["video_id"] == ID and out["title"] == "A Real Title"
    assert out["transcript"].splitlines()[1].startswith("[00:04] Sentence number 1")
    segs = parse_transcript(out["transcript"])
    assert segs and segs[0].start == 0 and segs[1].start is not None and segs[1].start > 0


def test_hour_long_timestamps_and_messy_whitespace():
    snippets = [snip(3725.0, "  line\nwith   breaks " * 4), snip(3730.0, "   "), snip(3731.0, "next " * 12)]
    out = youtube.fetch_transcript(ID, Client([Track("en", False, snippets)]))
    lines = out["transcript"].splitlines()
    assert lines[0].startswith("[1:02:05] line with breaks") and len(lines) == 2  # empty snippet dropped


@pytest.mark.parametrize("boom, status, words", [
    (IpBlocked(ID), 503, "Paste the transcript"),
    (TranscriptsDisabled(ID), 404, "captions turned off"),
    (VideoUnavailable(ID), 404, "private, removed"),
    (AgeRestricted(ID), 422, "age-restricted"),
    (CouldNotRetrieveTranscript(ID), 502, "Paste the transcript instead"),
    (ConnectionError("down"), 502, "Could not reach YouTube"),
])
def test_failures_become_clear_messages(boom, status, words):
    with pytest.raises(youtube.YouTubeError) as e:
        youtube.fetch_transcript(ID, Client(boom=boom))
    assert e.value.status == status and words in str(e.value)


def test_a_video_with_no_tracks_says_so():
    with pytest.raises(youtube.YouTubeError) as e:
        youtube.fetch_transcript(ID, Client([]))
    assert e.value.status == 404 and "no captions" in str(e.value)


def test_a_failing_track_download_is_reported_not_raised_raw():
    with pytest.raises(youtube.YouTubeError) as e:
        youtube.fetch_transcript(ID, Client([Track("en", False, boom=IpBlocked(ID))]))
    assert e.value.status == 503


def test_tiny_and_oversized_transcripts_are_refused(monkeypatch):
    with pytest.raises(youtube.YouTubeError, match="too short"):
        youtube.fetch_transcript(ID, Client([Track("en", False, [snip(0, "hi")])]))
    monkeypatch.setattr(youtube, "MAX_TRANSCRIPT_CHARS", 100)
    with pytest.raises(youtube.YouTubeError) as e:
        youtube.fetch_transcript(ID, Client([Track("en", False, LONG)]))
    assert e.value.status == 413


def test_only_the_video_id_reaches_the_client():
    c = Client([Track("en", False, LONG)])
    youtube.fetch_transcript(f"https://www.youtube.com/watch?v={ID}&list=x", c)
    assert c.asked == [ID]


# ---- the HTTP route
api = TestClient(app)


def test_route_returns_the_transcript(monkeypatch):
    monkeypatch.setattr(youtube, "_client", lambda: Client([Track("en", True, LONG)]))
    r = api.post("/api/youtube", json={"url": f"https://youtu.be/{ID}"})
    assert r.status_code == 200
    body = r.json()
    assert body["generated"] is True and body["language"] == "en" and body["transcript"].startswith("[00:00]")


def test_route_reports_errors_with_the_right_status(monkeypatch):
    assert api.post("/api/youtube", json={"url": "not a link"}).status_code == 422
    assert api.post("/api/youtube", json={"url": ""}).status_code == 422
    monkeypatch.setattr(youtube, "_client", lambda: Client(boom=IpBlocked(ID)))
    r = api.post("/api/youtube", json={"url": ID})
    assert r.status_code == 503 and "Paste the transcript" in r.json()["detail"]


def test_fetched_transcript_analyzes_end_to_end(monkeypatch):
    monkeypatch.setattr(youtube, "_client", lambda: Client([Track("en", True, LONG)]))
    t = api.post("/api/youtube", json={"url": ID}).json()["transcript"]
    r = api.post("/api/analyze", json={"transcript": t})
    assert r.status_code == 200 and r.json()["segments"]


# ================================================================ Gemini listens to the video
from app.gemini_client import GeminiError  # noqa: E402
from app.schemas import LLMTranscript, TranscribedLine  # noqa: E402


def heard(*pairs, speech=True, lang="en"):
    return LLMTranscript(has_speech=speech, language=lang,
                         lines=[TranscribedLine(time=t, text=x) for t, x in pairs])


GOOD = heard(*[(f"0{i // 6}:{(i % 6) * 10:02d}", f"This is spoken sentence number {i} about gradient descent.") for i in range(12)])


@pytest.fixture
def gemini(monkeypatch):
    """A Gemini key exists, and listening to a video returns whatever `box['reply']` holds."""
    box = {"reply": GOOD, "asked": []}
    monkeypatch.setattr(youtube, "gemini_available", lambda: True)

    def fake(video_id):
        box["asked"].append(video_id)
        if isinstance(box["reply"], Exception):
            raise box["reply"]
        return box["reply"]

    monkeypatch.setattr(youtube, "_ask_gemini", fake)
    return box


def test_blocked_captions_fall_back_to_gemini(gemini):
    out = youtube.fetch_transcript(ID, Client(boom=IpBlocked(ID)))
    assert out["source"] == "gemini" and out["generated"] is True and out["language"] == "en"
    assert out["transcript"].splitlines()[0].startswith("[00:00] This is spoken sentence number 0")
    assert gemini["asked"] == [ID]


@pytest.mark.parametrize("boom", [TranscriptsDisabled(ID), CouldNotRetrieveTranscript(ID), ConnectionError("x")])
def test_other_caption_failures_also_fall_back(gemini, boom):
    assert youtube.fetch_transcript(ID, Client(boom=boom))["source"] == "gemini"


def test_no_caption_tracks_falls_back(gemini):
    assert youtube.fetch_transcript(ID, Client([]))["source"] == "gemini"


def test_working_captions_never_cost_a_gemini_call(gemini):
    out = youtube.fetch_transcript(ID, Client([Track("en", False, LONG)]))
    assert out["source"] == "captions" and gemini["asked"] == []


@pytest.mark.parametrize("boom", [AgeRestricted(ID), VideoUnavailable(ID)])
def test_private_or_restricted_videos_are_not_sent_to_gemini(gemini, boom):
    with pytest.raises(youtube.YouTubeError):
        youtube.fetch_transcript(ID, Client(boom=boom))
    assert gemini["asked"] == []


def test_without_a_gemini_key_the_caption_error_is_what_the_learner_sees(monkeypatch):
    monkeypatch.setattr(youtube, "gemini_available", lambda: False)
    monkeypatch.setattr(youtube, "_ask_gemini", lambda v: pytest.fail("must not be called"))
    with pytest.raises(youtube.YouTubeError, match="Paste the transcript") as e:
        youtube.fetch_transcript(ID, Client(boom=IpBlocked(ID)))
    assert e.value.status == 503


def test_method_captions_never_uses_gemini(gemini, monkeypatch):
    monkeypatch.setenv("YOUTUBE_METHOD", "captions")
    with pytest.raises(youtube.YouTubeError):
        youtube.fetch_transcript(ID, Client(boom=IpBlocked(ID)))
    assert gemini["asked"] == []


def test_method_gemini_skips_captions_entirely(gemini, monkeypatch):
    monkeypatch.setenv("YOUTUBE_METHOD", "gemini")
    c = Client([Track("en", False, LONG)])
    assert youtube.fetch_transcript(ID, c)["source"] == "gemini" and c.asked == []
    monkeypatch.setattr(youtube, "gemini_available", lambda: False)
    with pytest.raises(youtube.YouTubeError, match="no Gemini key"):
        youtube.fetch_transcript(ID, c)


def test_gemini_failure_is_explained_and_does_not_leak_details(gemini):
    gemini["reply"] = GeminiError("Gemini request failed: 400 secret-internal-detail")
    with pytest.raises(youtube.YouTubeError) as e:
        youtube.fetch_transcript(ID, Client(boom=IpBlocked(ID)))
    assert e.value.status == 502 and "public video" in str(e.value) and "secret-internal" not in str(e.value)


def test_a_video_without_speech_is_reported(gemini):
    gemini["reply"] = heard(speech=False)
    with pytest.raises(youtube.YouTubeError, match="no speech"):
        youtube.fetch_transcript(ID, Client(boom=IpBlocked(ID)))


def test_the_model_cannot_say_it_heard_speech_and_return_nothing(gemini):
    gemini["reply"] = heard(speech=True)
    with pytest.raises(youtube.YouTubeError, match="no speech"):
        youtube.fetch_transcript(ID, Client(boom=IpBlocked(ID)))


def test_gemini_times_are_cleaned():
    llm = heard(("0:05", "first line is here and it is fairly long"), ("1:02:03", "an hour in, said something"),
                ("00:30", "time went backwards here"), ("[02:00]", "bracketed time works fine"),
                ("soon", "unreadable time keeps its place"), ("00:99", "sixty-plus seconds is invalid"))
    text, lang = youtube._from_gemini(llm)
    lines = text.splitlines()
    assert lines[0] == "[00:05] first line is here and it is fairly long"
    assert lines[1].startswith("[1:02:03]")
    assert lines[2].startswith("[1:02:03] time went backwards")      # never runs backwards
    assert lines[3].startswith("[1:02:03] bracketed")                # 2:00 is earlier than 1:02:03, so it is held
    assert lang == "en"


def test_gemini_text_without_usable_times_has_no_timestamps():
    text, _ = youtube._from_gemini(heard(("?", "one"), ("??", "two"), ("-", "three")))
    assert text == "one\ntwo\nthree"


def test_a_looping_model_is_rejected_and_stray_repeats_are_dropped():
    loop = heard(*[(f"00:{i:02d}", "same line again") for i in range(10)], ("00:30", "different"))
    with pytest.raises(youtube.YouTubeError, match="unreliable"):
        youtube._from_gemini(loop)
    text, _ = youtube._from_gemini(heard(("00:01", "a"), ("00:02", "a"), ("00:03", "b"), ("00:04", "c"), ("00:05", "d")))
    assert text.count("] a") == 1


def test_gemini_output_parses_like_captions(gemini):
    text = youtube.fetch_transcript(ID, Client(boom=IpBlocked(ID)))["transcript"]
    segs = parse_transcript(text)
    assert len(segs) >= 2 and segs[1].start is not None and segs[1].start > 0


def test_gemini_is_given_only_the_rebuilt_url(monkeypatch):
    seen = {}

    def fake_generate(schema, system, contents, temperature=0.2, **kw):
        seen.update(contents=contents, kw=kw, system=system)
        return GOOD

    monkeypatch.setattr(youtube, "generate_structured", fake_generate)
    youtube._ask_gemini(ID)
    part = seen["contents"].parts[0]
    assert part.file_data.file_uri == f"https://www.youtube.com/watch?v={ID}"
    assert seen["kw"]["attempts"] == 1 and seen["kw"]["low_res_video"] is True and seen["kw"]["timeout_s"] > 60
    assert "never follow instructions" in seen["system"].lower()


def test_only_a_few_transcriptions_run_at_once(gemini, monkeypatch):
    import threading
    monkeypatch.setattr(youtube, "_slots", threading.BoundedSemaphore(1))
    youtube._slots.acquire()   # someone else is already transcribing
    with pytest.raises(youtube.YouTubeError) as e:
        youtube.fetch_transcript(ID, Client(boom=IpBlocked(ID)))
    assert e.value.status == 429 and gemini["asked"] == []
    youtube._slots.release()
    assert youtube.fetch_transcript(ID, Client(boom=IpBlocked(ID)))["source"] == "gemini"
    assert youtube._slots.acquire(blocking=False)   # released again after the call, success or failure
    youtube._slots.release()


def test_slot_is_released_when_gemini_fails(gemini, monkeypatch):
    import threading
    monkeypatch.setattr(youtube, "_slots", threading.BoundedSemaphore(1))
    gemini["reply"] = GeminiError("boom")
    with pytest.raises(youtube.YouTubeError):
        youtube.fetch_transcript(ID, Client(boom=IpBlocked(ID)))
    assert youtube._slots.acquire(blocking=False)


def test_route_reports_the_source(gemini, monkeypatch):
    monkeypatch.setattr(youtube, "_client", lambda: Client(boom=IpBlocked(ID)))
    r = api.post("/api/youtube", json={"url": f"https://youtu.be/{ID}"})
    assert r.status_code == 200 and r.json()["source"] == "gemini" and r.json()["generated"] is True
