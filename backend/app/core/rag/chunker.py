"""Transcript chunking.

Splits a transcript into overlapping, retrievable chunks of roughly
``chunk_target_tokens`` tokens. We approximate token counts from whitespace so
the pipeline has no dependency on a specific tokenizer (this is sufficient for
embedding-based retrieval, which is robust to a ±20% size drift).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")

# Speaker-turn labels in the ChatPRD transcript archive:
#   "Lenny (00:01:01):"  -> a named speaker starts a turn
#   "(00:01:27):"        -> timestamp-only continuation of the current speaker
# The turn text follows the label and spans one or more paragraphs until the
# next label. Labels are anchored to the start of a line and the whitespace is
# restricted to spaces/tabs (never newlines), so a timestamp-only line can never
# leak backward and mis-attach text to the previous speaker.
_TURN_LABEL_RE = re.compile(
    r"^[ \t]*(?:(?P<speaker>[^\n(][^\n]*?)[ \t]+)?"
    r"\((?P<ts>\d{1,2}:\d{2}(?::\d{2})?)\):[ \t]*",
    re.MULTILINE,
)


@dataclass
class Chunk:
    index: int
    text: str
    token_count: int


@dataclass
class SpeakerChunk:
    """A chunk that also knows which speaker/timestamp it starts at."""

    index: int
    text: str
    token_count: int
    speaker: str | None
    timestamp: str | None


def approximate_tokens(text: str) -> int:
    """Rough token count: ~1.3 tokens per whitespace word (English average)."""
    words = len(text.split())
    return max(1, int(words * 1.3))


def split_sentences(text: str) -> list[str]:
    """Split into sentences, dropping empties and normalising whitespace."""
    parts = [p.strip() for p in _SENTENCE_RE.split(text)]
    return [p for p in parts if p]


def chunk_text(
    text: str,
    target_tokens: int = 400,
    overlap_tokens: int = 80,
) -> list[Chunk]:
    """Chunk text into overlapping windows of sentences.

    Short documents return a single chunk. Long documents slide a window of
    sentences forward, carrying ``overlap_tokens`` worth of trailing sentences
    into the next chunk to preserve cross-boundary context.
    """
    text = text.strip()
    if not text:
        return []

    sentences = split_sentences(text)
    if approximate_tokens(text) <= target_tokens:
        return [Chunk(index=0, text=text, token_count=approximate_tokens(text))]

    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_tokens = 0

    def flush() -> None:
        nonlocal buffer, buffer_tokens
        if not buffer:
            return
        body = " ".join(buffer)
        chunks.append(Chunk(index=len(chunks), text=body, token_count=buffer_tokens))
        # Carry overlap: keep trailing sentences worth <= overlap_tokens.
        carry: list[str] = []
        carry_tokens = 0
        for sent in reversed(buffer):
            t = approximate_tokens(sent)
            if carry_tokens + t > overlap_tokens and carry:
                break
            carry.append(sent)
            carry_tokens += t
        buffer = list(reversed(carry))
        buffer_tokens = carry_tokens

    for sentence in sentences:
        t = approximate_tokens(sentence)
        # A single sentence longer than the target gets its own chunk.
        if t >= target_tokens and not buffer:
            chunks.append(Chunk(index=len(chunks), text=sentence, token_count=t))
            continue
        if buffer_tokens + t > target_tokens and buffer:
            flush()
        buffer.append(sentence)
        buffer_tokens += t

    flush()
    return chunks


def parse_speaker_turns(text: str) -> list[tuple[str, str, str]]:
    """Split a speaker-labelled transcript into (speaker, timestamp, turn_text).

    Supports the ChatPRD transcript archive format:

    * ``Speaker Name (HH:MM:SS):`` starts a new speaker turn, and
    * ``(HH:MM:SS):`` is a timestamp-only continuation that keeps the current
      speaker.

    Returns ``[]`` when the text has no such labels.
    """
    matches = list(_TURN_LABEL_RE.finditer(text))
    if not matches:
        return []
    turns: list[tuple[str, str, str]] = []
    current_speaker: str | None = None
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        named = (m.group("speaker") or "").strip()
        if named:
            current_speaker = named
        if current_speaker is None:
            # A timestamp-only line before any speaker is named can't be
            # attributed; skip it rather than fabricate a speaker.
            continue
        if body:
            turns.append((current_speaker, m.group("ts"), body))
    return turns


def chunk_speaker_turns(
    text: str,
    target_tokens: int = 400,
    overlap_tokens: int = 80,
) -> list[SpeakerChunk]:
    """Chunk a speaker-labelled transcript, carrying speaker + timestamp.

    Turns (including timestamp-only continuations of the same speaker) are
    concatenated into ~``target_tokens`` windows with trailing-turn overlap so
    cross-turn context is preserved, and each chunk records the speaker/timestamp
    of the turn it starts at for deep citations.
    """
    turns = parse_speaker_turns(text)
    if not turns:
        return []

    chunks: list[SpeakerChunk] = []
    buffer: list[tuple[str, str, str]] = []
    buffer_tokens = 0

    def flush() -> None:
        nonlocal buffer, buffer_tokens
        if not buffer:
            return
        body = " ".join(t for _, _, t in buffer)
        first_speaker, first_ts = buffer[0][0], buffer[0][1]
        chunks.append(
            SpeakerChunk(
                index=len(chunks),
                text=body,
                token_count=buffer_tokens,
                speaker=first_speaker,
                timestamp=first_ts,
            )
        )
        # Carry overlap: keep trailing turns worth <= overlap_tokens.
        carry: list[tuple[str, str, str]] = []
        carry_tokens = 0
        for spk, ts, turn in reversed(buffer):
            t = approximate_tokens(turn)
            if carry_tokens + t > overlap_tokens and carry:
                break
            carry.append((spk, ts, turn))
            carry_tokens += t
        buffer = list(reversed(carry))
        buffer_tokens = carry_tokens

    for spk, ts, turn in turns:
        t = approximate_tokens(turn)
        # A single over-long turn becomes its own chunk.
        if t >= target_tokens and not buffer:
            chunks.append(
                SpeakerChunk(
                    index=len(chunks),
                    text=turn,
                    token_count=t,
                    speaker=spk,
                    timestamp=ts,
                )
            )
            continue
        if buffer_tokens + t > target_tokens and buffer:
            flush()
        buffer.append((spk, ts, turn))
        buffer_tokens += t

    flush()
    return chunks
