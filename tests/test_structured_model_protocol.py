from __future__ import annotations

import json
import time
from types import SimpleNamespace

import httpx
import pytest
from langchain_openai import ChatOpenAI

from backend.evaluation import (
    RagEvalCase,
    RagExpectedBehavior,
    RagGoldDocument,
    RagOutcome,
    RagRoute,
)
from backend.evaluation.runtime import RagEvaluationRuntime
from backend.rag import pipeline, utils
from tests.support import TEST_MODEL_SNAPSHOT


@pytest.fixture
def tool_output_model():
    clients = []

    def build(arguments):
        requests = []

        def respond(request):
            payload = json.loads(request.content)
            requests.append(payload)
            if "response_format" in payload or not payload.get("tools"):
                return httpx.Response(
                    400,
                    json={
                        "error": {
                            "message": "Use tools",
                            "type": "invalid_request_error",
                        }
                    },
                )
            name = payload["tools"][0]["function"]["name"]
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "test-model",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-test",
                                        "type": "function",
                                        "function": {
                                            "name": name,
                                            "arguments": json.dumps(arguments),
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                },
            )

        client = httpx.Client(transport=httpx.MockTransport(respond))
        clients.append(client)
        model = ChatOpenAI(
            model="test-model",
            api_key="unit-test-only",
            base_url="https://provider.invalid/v1",
            http_client=client,
            timeout=1,
            max_retries=0,
        )
        return model, requests

    yield build
    for client in clients:
        client.close()


@pytest.mark.parametrize(
    "schema,payload",
    [
        (
            pipeline.ComplexityResult,
            {"complexity": "simple", "reason": "single album", "sub_questions": []},
        ),
        (
            pipeline.EvidenceGrade,
            {"relevance": "strong", "answerability": "sufficient", "route": "answer"},
        ),
    ],
)
def test_rag_planner_and_grader_use_tool_output_protocol(
    tool_output_model, schema, payload
):
    model, requests = tool_output_model(payload)
    result = pipeline._invoke_structured_model(
        {},
        model=model,
        schema=schema,
        messages=[{"role": "user", "content": "question"}],
        provider="test-model",
        timeout_seconds=1,
    )
    assert result == schema(**payload)
    assert len(requests) == 1
    assert "response_format" not in requests[0]
    assert requests[0]["tools"][0]["function"]["name"] == schema.__name__


@pytest.mark.parametrize(
    "method,payload",
    [
        (
            "step_back",
            {
                "method": "step_back",
                "step_back_question": "broader question",
                "hyde_document": "",
            },
        ),
        (
            "hyde",
            {"method": "hyde", "step_back_question": "", "hyde_document": "hypothesis"},
        ),
    ],
)
def test_rewrite_uses_tool_output_protocol_without_an_extra_model_call(
    monkeypatch, tool_output_model, method, payload
):
    model, requests = tool_output_model(payload)
    monkeypatch.setattr(utils, "_get_rewrite_model", lambda *_: model)
    result = utils.rewrite_query_once("question")
    assert result["rewrite_method"] == method
    assert len(requests) == 1
    assert "response_format" not in requests[0]
    assert requests[0]["tools"][0]["function"]["name"] == "RewritePlan"


def test_evaluation_judge_uses_the_same_tool_output_protocol(tool_output_model):
    payload = {
        "answer_correctness": 1,
        "groundedness": 1,
        "answer_relevance": 1,
        "completeness": 1,
        "context_relevance": 1,
        "unsupported_claim_rate": 0,
        "conflict_disclosure_rate": 1,
        "reason": "supported",
    }
    model, requests = tool_output_model(payload)
    models = SimpleNamespace(
        get=lambda *_, **__: model,
        describe=lambda *_, **__: SimpleNamespace(name="test-model", timeout_seconds=1),
    )
    runtime = RagEvaluationRuntime(models=models)
    case = RagEvalCase(
        id="case-1",
        question="question",
        expected=RagExpectedBehavior(
            route=RagRoute.ANSWER, outcome=RagOutcome.ANSWERABLE
        ),
        reference_answer="answer",
        gold_documents=(RagGoldDocument(canonical_name="manual.html"),),
    )
    result = runtime._judge_answer(
        question=case.question,
        case=case,
        generated_answer="answer",
        documents=[],
        model_snapshot=TEST_MODEL_SNAPSHOT,
        deadline=time.monotonic() + 5,
        cancellation=lambda: False,
    )
    assert result.reason == "supported"
    assert len(requests) == 1
    assert "response_format" not in requests[0]
    assert requests[0]["tools"][0]["function"]["name"] == "RagJudgeDecision"
