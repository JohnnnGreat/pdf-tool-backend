"""user verification tokens and monthly quota counter

Revision ID: b2e1f4a8c3d9
Revises: 4daa33bf6db0
Create Date: 2026-04-27 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2e1f4a8c3d9"
down_revision: Union[str, Sequence[str], None] = "4daa33bf6db0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Email verification
    op.add_column("users", sa.Column("verification_token", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("verification_token_expires_at", sa.DateTime(), nullable=True))

    # Password reset
    op.add_column("users", sa.Column("reset_token", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("reset_token_expires_at", sa.DateTime(), nullable=True))

    # Monthly quota counter
    op.add_column("users", sa.Column("monthly_operations", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("ops_reset_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

    # Indexes for token lookups
    op.create_index("ix_users_verification_token", "users", ["verification_token"], unique=False)
    op.create_index("ix_users_reset_token", "users", ["reset_token"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_reset_token", table_name="users")
    op.drop_index("ix_users_verification_token", table_name="users")
    op.drop_column("users", "ops_reset_at")
    op.drop_column("users", "monthly_operations")
    op.drop_column("users", "reset_token_expires_at")
    op.drop_column("users", "reset_token")
    op.drop_column("users", "verification_token_expires_at")
    op.drop_column("users", "verification_token")
