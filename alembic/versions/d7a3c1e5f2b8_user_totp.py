"""user totp_secret and totp_enabled

Revision ID: d7a3c1e5f2b8
Revises: c5f9e2b1a4d7
Create Date: 2026-04-28 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7a3c1e5f2b8"
down_revision: Union[str, Sequence[str], None] = "c5f9e2b1a4d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret",  sa.String(64),  nullable=True))
    op.add_column("users", sa.Column("totp_enabled", sa.Boolean(),   nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")
