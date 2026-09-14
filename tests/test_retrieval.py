"""Unit tests for the chunker and lexical embedding fallback."""
from app.core.rag.chunker import (
    approximate_tokens,
    chunk_speaker_turns,
    chunk_text,
    parse_speaker_turns,
    split_sentences,
)
from app.core.rag.embedder import EmbeddingService, lexical_vector


def test_split_sentences():
    text = "First sentence. Second sentence! Third?"
    assert len(split_sentences(text)) == 3


def test_short_text_single_chunk():
    chunks = chunk_text("A very short transcript.", target_tokens=400)
    assert len(chunks) == 1
    assert chunks[0].index == 0


def test_long_text_multiple_chunks_and_overlap():
    sentences = [f"This is sentence number {i} about product and growth topics." for i in range(60)]
    text = " ".join(sentences)
    chunks = chunk_text(text, target_tokens=120, overlap_tokens=25)
    assert len(chunks) > 1
    # Chunks are ordered and non-empty.
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert all(c.text.strip() for c in chunks)


def test_lexical_vector_shape_and_stability():
    dim = 768
    v1 = lexical_vector("retention and activation metrics", dim)
    v2 = lexical_vector("retention and activation metrics", dim)
    assert len(v1) == dim
    assert v1 == v2  # deterministic


def test_cosine_similarity():
    a = lexical_vector("product market fit value hypothesis", 64)
    b = lexical_vector("product market fit value hypothesis", 64)
    c = lexical_vector("completely unrelated topic", 64)
    assert EmbeddingService.cosine(a, b) > 0.9
    assert EmbeddingService.cosine(a, c) < EmbeddingService.cosine(a, b)


def test_parse_speaker_turns():
    text = (
        "**Lenny Rachitsky** (00:00:00):\nWelcome to the show.\n\n"
        "**Shreyas Doshi** (00:01:00):\nPre-mortems surface Tigers and Paper Tigers.\n\n"
        "**Lenny Rachitsky** (00:02:30):\nAnd Elephants.\n"
    )
    turns = parse_speaker_turns(text)
    assert len(turns) == 3
    assert turns[0][0] == "Lenny Rachitsky"
    assert turns[1][0] == "Shreyas Doshi"
    assert turns[1][1] == "00:01:00"


def test_chunk_speaker_turns_carries_metadata():
    text = (
        "**Lenny Rachitsky** (00:00:00):\n"
        + "Sentence one about product strategy. " * 3
        + "\n\n**Shreyas Doshi** (00:01:00):\n"
        + "Sentence two about pre-mortems. " * 3
    )
    chunks = chunk_speaker_turns(text, target_tokens=40, overlap_tokens=10)
    assert chunks
    assert chunks[0].speaker == "Lenny Rachitsky"
    assert chunks[0].timestamp == "00:00:00"
    assert all(c.text.strip() for c in chunks)


def test_parse_speaker_turns_empty_without_labels():
    assert parse_speaker_turns("Just a normal paragraph with no speaker labels.") == []
    assert chunk_speaker_turns("Plain text without labels.") == []
