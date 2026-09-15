"""Agent routing and skill tests with a deterministic fake provider."""
from app.core.agent.agent import Agent, build_default_tools, off_topic_response
from app.core.agent.context import ToolContext
from app.core.agent.skills.ship30 import Ship30EssaySkill
from app.core.llm.base import ChatMessage, LLMProvider, LLMResponse, ToolCall
from app.core.rag import ingest
from app.core.rag.retriever import Retriever
from app.models import Artifact
from sqlalchemy import select

SAMPLE = (
    "Product-market fit means the value hypothesis is true. Validate value "
    "before growth. Use cohort analysis to see if users return on their own. "
    "The toothbrush test checks weekly usage. Retention at scale is the goal."
)


class FakeProvider(LLMProvider):
    name = "fake"
    model = "fake-model"

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple] = []

    async def complete(self, messages, tools=None):
        self.calls.append((messages, tools))
        return self.responses.pop(0)

    async def healthcheck(self):
        return True, None


async def test_agent_routes_to_search_and_grounds(db):
    await ingest.ingest_document(db, SAMPLE, title="Fit 101", episode_id="101")
    await db.commit()

    provider = FakeProvider(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="c1", name="search_transcripts", arguments={"query": "product-market fit"})],
            ),
            LLMResponse(content="Based on the transcripts, product-market fit is…"),
        ]
    )
    ctx = ToolContext(
        db=db, conversation_id="c", provider=provider, retriever=Retriever()
    )
    agent = Agent(provider)
    result = await agent.run(ctx, [ChatMessage(role="user", content="what is PMF?")])

    assert result.content
    assert result.grounded is True
    assert "search_transcripts" in result.tool_trace
    assert ctx.citations, "expected grounded citations to be recorded"


async def test_agent_passes_through_plain_answer(db):
    provider = FakeProvider([LLMResponse(content="Just a greeting.")])
    ctx = ToolContext(db=db, conversation_id="c", provider=provider, retriever=Retriever())
    result = await Agent(provider).run(ctx, [ChatMessage(role="user", content="hi")])
    assert result.content == "Just a greeting."
    assert result.grounded is False


async def test_ship30_skill_creates_artifact(db):
    await ingest.ingest_document(db, SAMPLE, title="Fit 101", episode_id="101")
    await db.commit()

    short_essay = "# The Value Hypothesis\n\nHook. Body with **bold** and bullets.\n\n- point one\n- point two\n\nThe takeaway."
    # A draft under the word floor should trigger a single expansion pass.
    expanded_essay = "# The Value Hypothesis\n\n" + " ".join(["detail"] * 1100)
    provider = FakeProvider(
        [LLMResponse(content=short_essay), LLMResponse(content=expanded_essay)]
    )
    ctx = ToolContext(
        db=db, conversation_id="conv1", provider=provider, retriever=Retriever()
    )
    skill = Ship30EssaySkill()
    result = await skill.run(ctx, topic="product-market fit")

    assert "Ship 30" in result.content
    assert result.meta and result.meta["artifact_id"]
    await db.commit()

    artifacts = (await db.execute(select(Artifact))).scalars().all()
    assert len(artifacts) == 1
    assert artifacts[0].kind == "markdown"
    # The expanded (word-count-satisfying) draft is what gets persisted.
    assert artifacts[0].content == expanded_essay
    assert len(artifacts[0].content.split()) >= 1000


async def test_ship30_skill_does_not_expand_long_essay(db):
    await ingest.ingest_document(db, SAMPLE, title="Fit 101", episode_id="101")
    await db.commit()

    long_essay = "# Long\n\n" + " ".join(["word"] * 1200)
    provider = FakeProvider([LLMResponse(content=long_essay)])
    ctx = ToolContext(
        db=db, conversation_id="conv1", provider=provider, retriever=Retriever()
    )
    result = await Ship30EssaySkill().run(ctx, topic="product-market fit")
    await db.commit()

    artifacts = (await db.execute(select(Artifact))).scalars().all()
    assert len(artifacts) == 1
    assert artifacts[0].content == long_essay
    # No expansion pass was attempted (a single provider call).
    assert len(provider.calls) == 1


def test_default_tools_include_all_capabilities():
    names = {t.name for t in build_default_tools()}
    assert {"search_transcripts", "list_sources", "write_ship30_essay", "generate_artifact"} <= names


def test_off_topic_guard_refuses_code_and_game_requests():
    assert off_topic_response("generate a tic tac toe game") is not None
    assert off_topic_response("write a python script to scrape data") is not None
    assert off_topic_response("build me a snake game") is not None
    assert off_topic_response("implement a binary search algorithm") is not None


def test_off_topic_guard_allows_product_and_growth_questions():
    assert off_topic_response("What does Lenny say about retention?") is None
    assert off_topic_response("Write a Ship 30 for 30 essay on activation") is None
    assert off_topic_response("Make an HTML checklist for onboarding") is None
    assert off_topic_response("How do I find product-market fit?") is None
    assert off_topic_response("") is None


def test_off_topic_guard_handles_punctuated_variants():
    """Hyphens/dots/spacing must all be caught (regression for the
    screenshot where the assistant returned a Tic-Tac-Toe implementation)."""
    assert off_topic_response("make me a tic-tac-toe game") is not None
    assert off_topic_response("build tic.tac.toe") is not None
    assert off_topic_response("rock-paper-scissors in python") is not None
    assert off_topic_response("guess-the-number game") is not None
    assert off_topic_response("write a todo app in react.js") is not None


def test_off_topic_guard_does_not_false_positive():
    """Legitimate product/growth and artifact requests must still pass."""
    assert off_topic_response("How do users react to my onboarding emails?") is None
    assert off_topic_response("How do I make users come back to the app?") is None
    assert off_topic_response("Make an HTML onboarding checklist") is None
    assert off_topic_response("Write a Ship 30 essay on positioning") is None


async def test_agent_short_circuits_off_topic_without_calling_model(db):
    provider = FakeProvider([LLMResponse(content="should not be used")])
    ctx = ToolContext(db=db, conversation_id="c", provider=provider, retriever=Retriever())
    result = await Agent(provider).run(
        ctx, [ChatMessage(role="user", content="generate a tic tac toe game")]
    )
    assert result.grounded is False
    assert "Lenny Growth Assistant" in result.content
    assert provider.calls == [], "off-topic requests must not invoke the LLM"


async def test_agent_refuses_direct_code_answer(db):
    """Defense in depth: if the model returns a code block directly (no tool
    use), the agent swaps in the branded refusal instead of surfacing code."""
    provider = FakeProvider([
        LLMResponse(
            content="Here is some code:\n\n```python\nprint('hello')\n```"
        )
    ])
    ctx = ToolContext(db=db, conversation_id="c", provider=provider, retriever=Retriever())
    result = await Agent(provider).run(
        ctx, [ChatMessage(role="user", content="show me an example")]
    )
    assert "Lenny Growth Assistant" in result.content
    assert result.grounded is False
    assert "print" not in result.content


async def test_agent_force_grounds_when_model_skips_search(db):
    """Regression: if a (local) model answers without invoking search, the agent
    must still retrieve and re-answer so the response is grounded, not a vague
    "I'm unable to find the information" reply."""
    await ingest.ingest_document(db, SAMPLE, title="Fit 101", episode_id="101")
    await db.commit()

    provider = FakeProvider(
        [
            LLMResponse(content="I'm unable to find the information you requested."),
            LLMResponse(content="Product-market fit means the value hypothesis is true."),
        ]
    )
    ctx = ToolContext(db=db, conversation_id="c", provider=provider, retriever=Retriever())
    result = await Agent(provider).run(
        ctx, [ChatMessage(role="user", content="what is product-market fit?")]
    )

    assert result.grounded is True
    assert ctx.citations, "force-grounding must retrieve and attach citations"
    assert "value hypothesis" in result.content


async def test_agent_falls_back_to_grounded_answer_when_model_is_generic(db):
    """Regression: a weak local model can answer with generic advice even after
    retrieval. The agent must substitute a verbatim, source-tagged answer rather
    than returning un-grounded fluff (the "product-market fit" screenshot)."""
    await ingest.ingest_document(db, SAMPLE, title="Fit 101", episode_id="101")
    await db.commit()

    generic = (
        "Based on the search results, here are some general guidelines: "
        "customer validation, revenue growth, customer retention, market size, "
        "and competitive advantage."
    )
    provider = FakeProvider(
        [
            LLMResponse(content=generic),  # first pass: no search
            LLMResponse(content=generic),  # forced re-answer: still generic
        ]
    )
    ctx = ToolContext(db=db, conversation_id="c", provider=provider, retriever=Retriever())
    result = await Agent(provider).run(
        ctx,
        [ChatMessage(role="user", content="How do I know I've found product-market fit?")],
    )

    assert result.grounded is True
    assert ctx.citations
    # The generic answer must be replaced by the source-tagged fallback.
    assert "customer validation" not in result.content
    assert "Fit 101" in result.content


async def test_agent_grounds_when_search_tool_call_fails(db):
    """Regression: a local model can call search_transcripts with a malformed
    query (so the tool collects no citations) and then answer generically. The
    agent must still deterministically retrieve and ground the answer instead of
    letting the generic response escape (the 'query parameter format' screenshot)."""
    await ingest.ingest_document(db, SAMPLE, title="Fit 101", episode_id="101")
    await db.commit()

    generic = (
        "It seems like the search_transcripts function requires a specific format. "
        "Signs of product-market fit include growth, engagement, and revenue."
    )
    provider = FakeProvider(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="search_transcripts",
                        arguments={"query": {"nested": "bad"}},
                    )
                ],
            ),
            LLMResponse(content=generic),  # model gives up and answers generically
            LLMResponse(content=generic),  # deterministic re-answer is still generic
        ]
    )
    ctx = ToolContext(db=db, conversation_id="c", provider=provider, retriever=Retriever())
    result = await Agent(provider).run(
        ctx,
        [ChatMessage(role="user", content="How do I know I've found product-market fit?")],
    )

    assert result.grounded is True
    assert ctx.citations
    assert "Fit 101" in result.content
    # The generic preamble (not the verbatim source) must have been replaced.
    assert "specific format" not in result.content
    assert "Signs of product-market fit include" not in result.content


async def test_agent_does_not_fallback_when_model_cites_speaker(db):
    """Regression: the fallback must not replace a good answer that cites the
    source by guest name (a common citation form) instead of a [n] marker."""
    await ingest.ingest_document(
        db,
        SAMPLE,
        title="When to invest in new channels | Adam Grenier",
        episode_id="adam-grenier",
        speaker="Adam Grenier",
    )
    await db.commit()

    good = "Adam Grenier advises assuming you no longer have product-market fit."
    provider = FakeProvider(
        [
            LLMResponse(content="Product-market fit is important."),  # no search
            LLMResponse(content=good),  # deterministic re-answer, cited by guest name
        ]
    )
    ctx = ToolContext(db=db, conversation_id="c", provider=provider, retriever=Retriever())
    result = await Agent(provider).run(
        ctx,
        [ChatMessage(role="user", content="What does Lenny say about product-market fit?")],
    )

    assert result.grounded is True
    assert ctx.citations
    # The speaker-cited answer must be kept, not replaced by the verbatim fallback.
    assert result.content == good
    assert "Here's what Lenny's Podcast says" not in result.content
