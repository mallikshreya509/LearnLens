import pytest

from app.transcript import format_ts, parse_transcript


def test_plain_text_becomes_numbered_segments():
    text = " ".join(f"This is sentence number {i} about learning." for i in range(40))
    segs = parse_transcript(text)
    assert len(segs) > 1
    assert [s.id for s in segs] == list(range(1, len(segs) + 1))
    assert all(s.start is None for s in segs)


def test_timestamped_lines_keep_their_start_times():
    def line(n):  # ~300 chars and distinct, so each line stays its own segment
        return f"topic{n} " + "alpha " * 50

    raw = f"[00:00] {line(1)}\n[00:20] {line(2)}\n[1:05] {line(3)}"
    segs = parse_transcript(raw)
    assert [s.start for s in segs] == [0.0, 20.0, 65.0]


def test_srt_cues_are_merged_and_tags_stripped():
    srt = (
        "1\n00:00:01,000 --> 00:00:03,000\nHello everyone.\n\n"
        "2\n00:00:03,500 --> 00:00:06,000\nWelcome to <i>the course</i>.\n"
    )
    segs = parse_transcript(srt)
    assert len(segs) == 1
    assert segs[0].start == 1.0
    assert segs[0].text == "Hello everyone. Welcome to the course."


def test_vtt_repeated_caption_lines_are_deduplicated():
    vtt = "WEBVTT\n\n00:00.000 --> 00:02.000\nHello there.\n\n00:02.000 --> 00:04.000\nHello there.\n"
    segs = parse_transcript(vtt)
    assert len(segs) == 1
    assert segs[0].text == "Hello there."


def test_unpunctuated_wall_of_text_is_split():
    segs = parse_transcript("word " * 600)
    assert len(segs) > 2
    assert all(len(s.text) < 700 for s in segs)


def test_empty_transcript_raises():
    with pytest.raises(ValueError):
        parse_transcript("   \n  ")


def test_format_ts():
    assert format_ts(65) == "01:05"
    assert format_ts(3725) == "1:02:05"
    assert format_ts(None) is None
