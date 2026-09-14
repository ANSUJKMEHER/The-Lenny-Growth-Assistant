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
