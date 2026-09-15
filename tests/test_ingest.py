"""Ingestion: chunking, idempotency, and retrieval end-to-end (lexical fallback)."""
from app.core.rag import ingest
from app.core.rag.retriever import Retriever
from app.models import Chunk, TranscriptSource
from sqlalchemy import func, select


SAMPLE = """\
Product-market fit is the moment a product's value hypothesis becomes true.
Teams should validate value before chasing growth. A cohort analysis shows
whether users return on their own. The toothbrush test asks if a product is
used weekly. Retention at scale is the goal, not just engagement among a tiny
loyal group. Markets change and competitors ship, so fit is a milestone.
"""


async def test_ingest_creates_source_and_chunks(db):
    stats, source = await ingest.ingest_document(
        db, SAMPLE, title="Fit 101", episode_id="101"
    )
    await db.commit()
    assert stats.sources_created == 1
    assert stats.chunks_created >= 1
    assert source is not None

    count = (await db.execute(select(func.count(Chunk.id)))).scalar_one()
    assert count == stats.chunks_created


async def test_ingest_is_idempotent(db):
    await ingest.ingest_document(db, SAMPLE, title="Fit 101")
    await db.commit()
    stats2, _ = await ingest.ingest_document(db, SAMPLE, title="Fit 101")
    await db.commit()
    assert stats2.sources_created == 0
    assert stats2.sources_skipped == 1

    total = (await db.execute(select(func.count(TranscriptSource.id)))).scalar_one()
    assert total == 1


async def test_retrieval_finds_relevant_chunk(db):
    await ingest.ingest_document(
        db, SAMPLE, title="Product-Market Fit", episode_id="101"
    )
    await db.commit()

    retriever = Retriever()
    results = await retriever.retrieve(db, "How do I know I have product-market fit?", top_k=3)
    assert results, "expected at least one retrieved chunk"
    assert results[0].title == "Product-Market Fit"
    # In tests Ollama is unreachable, so embeddings are the lexical fallback
    # vectors; retrieval may report either the vector-similarity or BM25 path.
    assert results[0].method in {"embedding", "bm25"}


async def test_retrieval_empty_corpus(db):
    retriever = Retriever()
    results = await retriever.retrieve(db, "anything")
    assert results == []


async def test_retrieval_splits_compound_query(db):
    """A compound query ("X and Y") must surface chunks for BOTH clauses, not
    let one clause dominate the merged result set."""
    await ingest.ingest_document(
        db, "Product-market fit is when users keep returning for value.",
        title="Fit episode", episode_id="fit",
    )
    await ingest.ingest_document(
        db, "Positioning is choosing a market category and a specific customer.",
        title="Positioning episode", episode_id="pos",
    )
    await db.commit()

    retriever = Retriever()
    results = await retriever.retrieve(
        db, "product-market fit and positioning", top_k=4
    )
    titles = {r.title for r in results}
    assert "Fit episode" in titles, "compound retrieval dropped the PMF clause"
    assert "Positioning episode" in titles, "compound retrieval dropped the positioning clause"


async def test_speaker_transcript_sets_chunk_metadata(db):
    text = (
        "Lenny Rachitsky (00:00:00):\nWelcome to the show.\n\n"
        "Shreyas Doshi (00:01:00):\nPre-mortems surface Tigers and Paper Tigers. "
        "Elephants are the ignored big risks that sink a launch.\n\n"
        "(00:02:00):\nAnd here is a timestamp-only continuation of the same speaker.\n"
    )
    stats, source = await ingest.ingest_document(
        db, text, title="Pre-mortems", episode_id="23", speaker="Shreyas Doshi"
    )
    await db.commit()
    assert stats.sources_created == 1

    chunks = (
        await db.execute(select(Chunk).where(Chunk.source_id == source.id))
    ).scalars().all()
    assert chunks
    assert any(c.speaker for c in chunks)
    assert any(c.timestamp for c in chunks)

    # The retriever should surface speaker/timestamp in its results.
    results = await Retriever().retrieve(db, "pre-mortems", top_k=3)
    assert results
    assert results[0].speaker
    assert results[0].timestamp


async def test_seed_samples_ingests_bundled_transcripts(db):
    """Regression: seed_samples must resolve backend/data/transcripts correctly
    and skip the directory README (a data-directory note, not a transcript)."""
    stats = await ingest.seed_samples(db)
    await db.commit()

    assert stats.errors == []
    assert stats.sources_created == 3  # three [SAMPLE] transcripts, README excluded

    rows = (await db.execute(select(TranscriptSource))).scalars().all()
    titles = {r.title for r in rows}
    assert len(titles) == 3
    assert not any("README" in t for t in titles)
    # The samples cover the demo's suggested prompt topics.
    assert any("Retention" in t for t in titles)
    assert any("Positioning" in t for t in titles)
    assert any("Product-Market Fit" in t for t in titles)
