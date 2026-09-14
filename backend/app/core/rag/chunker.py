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


@dataclass
class Chunk:
    index: int
    text: str
    token_count: int


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
