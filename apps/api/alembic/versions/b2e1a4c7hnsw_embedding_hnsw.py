"""embedding: ivfflat -> hnsw

Revision ID: b2e1a4c7hnsw
Revises: 9d116d69ac35
Create Date: 2026-07-09

"""
from alembic import op

revision = "b2e1a4c7hnsw"
down_revision = "9d116d69ac35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_raw_item_embedding", table_name="raw_item")
    op.create_index(
        "ix_raw_item_embedding", "raw_item", ["embedding"],
        postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_raw_item_embedding", table_name="raw_item")
    op.create_index(
        "ix_raw_item_embedding", "raw_item", ["embedding"],
        postgresql_using="ivfflat", postgresql_with={"lists": 100},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
