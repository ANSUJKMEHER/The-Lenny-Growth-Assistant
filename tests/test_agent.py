"""Agent routing and skill tests with a deterministic fake provider."""
from app.core.agent.agent import Agent, build_default_tools
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

    essay_md = "# The Value Hypothesis\n\nHook. Body with **bold** and bullets.\n\n- point one\n- point two\n\nThe takeaway."
    provider = FakeProvider([LLMResponse(content=essay_md)])
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
    assert "Value Hypothesis" in artifacts[0].content


def test_default_tools_include_all_capabilities():
    names = {t.name for t in build_default_tools()}
    assert {"search_transcripts", "list_sources", "write_ship30_essay", "generate_artifact"} <= names
