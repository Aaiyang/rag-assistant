from __future__ import annotations

from datetime import datetime

import pytest
from alembic import command
from sqlalchemy import MetaData, Table, create_engine, inspect, select, update

from backend.infra.database import alembic_config


def test_existing_profile_keeps_defaults_and_explicit_thinking_is_persisted(tmp_path):
    url = f"sqlite:///{tmp_path / 'thinking.db'}"
    config = alembic_config(url)
    command.upgrade(config, "0018_capability_control_plane")
    engine = create_engine(url)
    try:
        profiles = Table("model_profiles", MetaData(), autoload_with=engine)
        with engine.begin() as connection:
            connection.execute(
                profiles.insert().values(
                    id="model_" + "a" * 32,
                    display_name="existing",
                    provider="openai",
                    model_name="qwen",
                    base_url="",
                    timeout_seconds=120,
                    supports_stream=True,
                    supports_structured_output=True,
                    enabled=True,
                    source="user",
                    version=3,
                    created_at=datetime(2026, 10, 20),
                    updated_at=datetime(2026, 10, 20),
                )
            )
        command.upgrade(config, "head")
        profiles = Table("model_profiles", MetaData(), autoload_with=engine)
        with engine.begin() as connection:
            row = connection.execute(select(profiles)).mappings().one()
            assert row["enable_thinking"] is None
            assert row["version"] == 3
            assert row["timeout_seconds"] == 120
            connection.execute(update(profiles).values(enable_thinking=False))
        with engine.connect() as connection:
            assert (
                connection.execute(select(profiles.c.enable_thinking)).scalar_one()
                is False
            )
        with pytest.raises(RuntimeError, match="Clear explicit"):
            command.downgrade(config, "0018_capability_control_plane")
        with engine.begin() as connection:
            connection.execute(update(profiles).values(enable_thinking=None))
        command.downgrade(config, "0018_capability_control_plane")
        assert "enable_thinking" not in {
            column["name"] for column in inspect(engine).get_columns("model_profiles")
        }
    finally:
        engine.dispose()
