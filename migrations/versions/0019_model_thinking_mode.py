"""Add explicit optional thinking configuration to Model Profiles.

Revision ID: 0019_model_thinking_mode
Revises: 0018_capability_control_plane
Create Date: 2026-10-20
"""

import sqlalchemy as sa
from alembic import op


revision = "0019_model_thinking_mode"
down_revision = "0018_capability_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL retains provider defaults; existing snapshots and hashes are untouched.
    op.add_column(
        "model_profiles", sa.Column("enable_thinking", sa.Boolean(), nullable=True)
    )


def downgrade() -> None:
    # Removing explicit False/True would silently change future request semantics.
    connection = op.get_bind()
    configured = connection.execute(
        sa.text("SELECT COUNT(*) FROM model_profiles WHERE enable_thinking IS NOT NULL")
    ).scalar_one()
    if configured:
        raise RuntimeError(
            "Clear explicit Model Profile thinking settings before downgrade"
        )
    op.drop_column("model_profiles", "enable_thinking")
