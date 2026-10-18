"""Turn raw transcript text into numbered segments.

Supported inputs: plain text, lines starting with a timestamp ([01:23] / 01:23 / 1:02:03),
SRT and WebVTT caption files.
"""
import re

from .schemas import MAX_TRANSCRIPT_CHARS, Segment

MAX_CHARS = MAX_TRANSCRIPT_CHARS
TARGET_CHARS = 280  # merge short caption lines up to roughly this size
LONG_SEGMENT = 700  # split anything longer than this (e.g. unpunctuated auto-captions)

_TS = r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?"
_CUE_RE = re.compile(rf"^\s*{_TS}\s*-->\s*{_TS}")
_LINE_TS_RE = re.compile(rf"^\s*[\[\(]?{_TS}[\]\)]?\s*[-–—:]?\s*(.*)$")
_TAG_RE = re.compile(r"<[^>]+>")
_SENT_RE = re.compile(r"(?<=[.!?])\s+")


def _seconds(h, m, s, ms) -> float:
    total = int(h or 0) * 3600 + int(m) * 60 + int(s)
    if ms:
        total += int(ms.ljust(3, "0")[:3]) / 1000
    return float(total)


def format_ts(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    whole = int(seconds)
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _parse_cues(lines: list[str]) -> list[tuple[float | None, str]]:
    """SRT / VTT."""
    pieces: list[tuple[float | None, str]] = []
    start: float | None = None
    buf: list[str] = []
    for line in lines + [""]:  # trailing blank line flushes the last cue
        cue = _CUE_RE.match(line)
        if cue:
            if start is not None and buf:
                pieces.append((start, " ".join(buf)))
            start, buf = _seconds(*cue.groups()[:4]), []
        elif not line.strip():
            if start is not None and buf:
                pieces.append((start, " ".join(buf)))
            start, buf = None, []
        elif start is not None:
            text = _TAG_RE.sub("", line).strip()
            if text:
                buf.append(text)
    return pieces


def _parse_timestamped(lines: list[str]) -> list[tuple[float | None, str]]:
    pieces: list[list] = []
    for line in lines:
        if not line.strip():
            continue
        m = _LINE_TS_RE.match(line)
        if m:
            pieces.append([_seconds(*m.groups()[:4]), m.group(5).strip()])
        elif pieces:
            pieces[-1][1] += " " + line.strip()
        else:
            pieces.append([None, line.strip()])
    return [(s, t) for s, t in pieces if t]


def _parse_plain(text: str) -> list[tuple[float | None, str]]:
    sentences = [s.strip() for s in _SENT_RE.split(re.sub(r"\s+", " ", text)) if s.strip()]
    pieces: list[tuple[float | None, str]] = []
    buf = ""
    for sentence in sentences:
        buf = f"{buf} {sentence}".strip()
        if len(buf) >= TARGET_CHARS:
            pieces.append((None, buf))
            buf = ""
    if buf:
        pieces.append((None, buf))
    return pieces


def _merge(pieces: list[tuple[float | None, str]]) -> list[tuple[float | None, str]]:
    merged: list[tuple[float | None, str]] = []
    start: float | None = None
    buf = ""
    prev = None
    for s, t in pieces:
        t = re.sub(r"\s+", " ", t).strip()
        if not t or t == prev:  # auto-captions often repeat lines
            continue
        prev = t
        if not buf:
            start = s
        buf = f"{buf} {t}".strip()
        if len(buf) >= TARGET_CHARS:
            merged.append((start, buf))
            buf = ""
    if buf:
        merged.append((start, buf))
    return merged


def _split_long(text: str) -> list[str]:
    if len(text) <= LONG_SEGMENT:
        return [text]
    chunks, buf = [], ""
    for word in text.split(" "):
        if buf and len(buf) + 1 + len(word) > TARGET_CHARS + 70:
            chunks.append(buf)
            buf = word
        else:
            buf = f"{buf} {word}".strip()
    if buf:
        chunks.append(buf)
    return chunks


def parse_transcript(raw: str) -> list[Segment]:
    text = (raw or "").replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("Transcript is empty.")
    if len(text) > MAX_CHARS:
        raise ValueError(
            f"Transcript is too long ({len(text):,} characters). "
            f"The MVP limit is {MAX_CHARS:,}."
        )

    lines = text.split("\n")
    if any(_CUE_RE.match(line) for line in lines):
        pieces = _parse_cues(lines)
    else:
        nonblank = [line for line in lines if line.strip()]
        stamped = sum(1 for line in nonblank if _LINE_TS_RE.match(line))
        if nonblank and stamped / len(nonblank) >= 0.3:
            pieces = _parse_timestamped(lines)
        else:
            pieces = _parse_plain(text)

    segments: list[Segment] = []
    for start, body in _merge(pieces):
        for i, chunk in enumerate(_split_long(body)):
            segments.append(
                Segment(id=len(segments) + 1, start=start if i == 0 else None, text=chunk)
            )
    if not segments:
        raise ValueError("No transcript text found.")
    return segments


def render_for_prompt(segments: list[Segment]) -> str:
    out = []
    for seg in segments:
        ts = format_ts(seg.start)
        tag = f"[S{seg.id}|{ts}]" if ts else f"[S{seg.id}]"
        out.append(f"{tag} {seg.text}")
    return "\n".join(out)
