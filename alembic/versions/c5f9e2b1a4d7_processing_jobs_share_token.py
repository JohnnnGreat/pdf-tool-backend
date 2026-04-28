"""processing_jobs share_token and result_expires_at

Revision ID: c5f9e2b1a4d7
Revises: b2e1f4a8c3d9
Create Date: 2026-04-27 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5f9e2b1a4d7"
down_revision: Union[str, Sequence[str], None] = "b2e1f4a8c3d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("processing_jobs", sa.Column("share_token", sa.String(64), nullable=True))
    op.add_column("processing_jobs", sa.Column("result_expires_at", sa.DateTime(), nullable=True))
    op.create_index("ix_processing_jobs_share_token", "processing_jobs", ["share_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_share_token", table_name="processing_jobs")
    op.drop_column("processing_jobs", "result_expires_at")
    op.drop_column("processing_jobs", "share_token")
