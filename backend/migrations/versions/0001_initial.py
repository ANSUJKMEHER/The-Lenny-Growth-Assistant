"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "transcript_sources",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("episode_id", sa.String(128), nullable=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("speaker", sa.String(255), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("content_hash", name="uq_source_hash"),
    )
    op.create_index("ix_transcript_sources_episode_id", "transcript_sources", ["episode_id"])
    op.create_index("ix_transcript_sources_content_hash", "transcript_sources", ["content_hash"])

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(32),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    op.create_table(
        "chunks",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(32),
            sa.ForeignKey("transcript_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("speaker", sa.String(128), nullable=True),
        sa.Column("timestamp", sa.String(16), nullable=True),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_chunks_source_id", "chunks", ["source_id"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(32),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            sa.String(32),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_artifacts_conversation_id", "artifacts", ["conversation_id"])
    op.create_index("ix_artifacts_message_id", "artifacts", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_artifacts_message_id", table_name="artifacts")
    op.drop_index("ix_artifacts_conversation_id", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_chunks_source_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_table("messages")
    op.drop_table("app_settings")
    op.drop_index("ix_transcript_sources_content_hash", table_name="transcript_sources")
    op.drop_index("ix_transcript_sources_episode_id", table_name="transcript_sources")
    op.drop_table("transcript_sources")
    op.drop_table("conversations")
