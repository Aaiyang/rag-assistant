from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, ValidationError

from backend.agent.models import ModelRegistry
from backend.core.settings import ModelSettings
from backend.model_control import (
    ModelCatalogSnapshot,
    ModelRole,
    ModelRuntimeSpec,
    build_model_catalog_snapshot,
)
from backend.schemas.models import ModelProfileCreateRequest


def snapshot(mode: bool | None):
    return build_model_catalog_snapshot(
        {
            role: ModelRuntimeSpec(
                profile_id="model_" + "a" * 32,
                profile_version=1,
                display_name="test",
                model_name="test-model",
                timeout_seconds=120,
                supports_stream=True,
                supports_structured_output=True,
                enable_thinking=mode,
            )
            for role in ModelRole
        }
    )


def test_historical_snapshot_hash_is_preserved_and_thinking_is_hash_bound():
    old = snapshot(None).model_dump(mode="json")
    for spec in old["assignments"].values():
        del spec["enable_thinking"]
    canonical = json.dumps(
        old["assignments"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    old["catalog_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
    restored = ModelCatalogSnapshot.model_validate(old)
    assert restored.catalog_hash == snapshot(None).catalog_hash
    assert restored.require(ModelRole.ANSWER).enable_thinking is None
    assert len({snapshot(mode).catalog_hash for mode in (None, False, True)}) == 3
    changed = snapshot(False).model_dump(mode="json")
    changed["assignments"]["answer"]["enable_thinking"] = True
    with pytest.raises(ValidationError, match="hash"):
        ModelCatalogSnapshot.model_validate(changed)


@pytest.mark.parametrize("invalid", ["false", 0, {}, []])
def test_thinking_requires_an_explicit_boolean_or_null(invalid):
    with pytest.raises(ValidationError):
        ModelProfileCreateRequest(
            display_name="test", model_name="test", enable_thinking=invalid
        )


class Decision(BaseModel):
    accepted: bool


@pytest.mark.parametrize("mode", [None, False, True])
def test_registry_transmits_frozen_thinking_mode_for_plain_stream_and_structured_requests(
    mode,
):
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if payload.get("stream"):
            event = {
                "id": "test",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": "ok"},
                        "finish_reason": None,
                    }
                ],
            }
            terminal = {
                **event,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=f"data: {json.dumps(event)}\n\ndata: {json.dumps(terminal)}\n\ndata: [DONE]\n\n",
            )
        message = {"role": "assistant", "content": "ok"}
        if payload.get("tools"):
            name = payload["tools"][0]["function"]["name"]
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-test",
                        "type": "function",
                        "function": {"name": name, "arguments": '{"accepted": true}'},
                    }
                ],
            }
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": "tool_calls"
                        if payload.get("tools")
                        else "stop",
                    }
                ],
            },
        )

    settings = SimpleNamespace(
        models=ModelSettings(
            _env_file=None,
            ARK_API_KEY="test-only",
            BASE_URL="https://provider.invalid/v1",
            MODEL="test-model",
        )
    )
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:

        def initialize(**kwargs):
            return init_chat_model(**kwargs, http_client=client)

        registry = ModelRegistry(settings=settings, initializer=initialize)
        frozen = snapshot(mode)
        for role in ModelRole:
            model = registry.get(role, snapshot=frozen)
            assert model.invoke("test").content == "ok"
            if role == ModelRole.ANSWER:
                assert "".join(chunk.content for chunk in model.stream("test")) == "ok"
            else:
                assert (
                    model.with_structured_output(Decision, method="function_calling")
                    .invoke("test")
                    .accepted
                )
        for payload in requests:
            if mode is None:
                assert "enable_thinking" not in payload
            else:
                assert payload["enable_thinking"] is mode
        assert len(requests) == 8


def test_thinking_modes_do_not_share_cached_clients():
    calls = []

    def initialize(**kwargs):
        calls.append(kwargs)
        return object()

    registry = ModelRegistry(
        settings=SimpleNamespace(
            models=ModelSettings(
                _env_file=None, ARK_API_KEY="test-only", MODEL="test-model"
            )
        ),
        initializer=initialize,
    )
    old = snapshot(True)
    new = snapshot(False)
    before = registry.get(ModelRole.ANSWER, snapshot=old)
    after = registry.get(ModelRole.ANSWER, snapshot=new)
    assert before is registry.get(ModelRole.ANSWER, snapshot=old)
    assert before is not after
    assert [call["extra_body"]["enable_thinking"] for call in calls] == [True, False]
