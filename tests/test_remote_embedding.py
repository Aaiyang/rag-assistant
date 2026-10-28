import asyncio
import json
import time
import unittest

import httpx
from pydantic import SecretStr

from backend.core.settings import EmbeddingSettings
from backend.providers.core import ProviderCode, ProviderError, ProviderPolicy
from backend.providers.embedding import EmbeddingRuntime, EmbeddingScope
from backend.providers.embedding_http import HttpxEmbeddingEncoder


class RemoteEmbeddingTests(unittest.IsolatedAsyncioTestCase):
    def runtime(self, handler, *, attempts=1, **kwargs):
        self.clients = []

        def factory(**options):
            client = httpx.AsyncClient(
                transport=httpx.MockTransport(handler), **options
            )
            self.clients.append(client)
            return client

        encoder = HttpxEmbeddingEncoder(
            endpoint="https://embedding.example.test/v1/embeddings",
            model="BAAI/bge-m3",
            api_key="test-secret",
            timeout_seconds=1,
            client_factory=factory,
        )
        runtime = EmbeddingRuntime(
            remote_encoder=encoder,
            model_factory=lambda: self.fail("remote mode loaded a local model"),
            expected_dimension=2,
            policy=ProviderPolicy(max_attempts=attempts, initial_backoff_seconds=0),
            microbatch_window_seconds=0,
            **kwargs,
        )
        self.addAsyncCleanup(runtime.close)
        return runtime

    async def test_document_order_query_normalization_cache_and_client_lifecycle(self):
        calls = []

        def handler(request):
            self.assertEqual("Bearer test-secret", request.headers["Authorization"])
            body = json.loads(request.content)
            self.assertEqual("BAAI/bge-m3", body["model"])
            calls.append(body["input"])
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": index, "embedding": [3.0, 4.0]}
                        for index in reversed(range(len(body["input"])))
                    ]
                },
            )

        runtime = self.runtime(handler, max_batch_size=2)
        self.assertEqual([], self.clients)
        vectors = await runtime.embed_documents(["one", "two", "three"])
        self.assertEqual([[0.6, 0.8]] * 3, vectors)
        self.assertEqual([["one", "two"], ["three"]], calls)
        await runtime.embed_query(" Ａ  B ")
        await runtime.embed_query("A B")
        self.assertEqual(3, len(calls))
        await runtime.embed_query("A B", scope=EmbeddingScope(tenant_id="other"))
        self.assertEqual(4, len(calls))
        self.assertTrue(runtime.readiness().ready)
        self.assertFalse(runtime.readiness().model_loaded)
        self.assertEqual(1, len(self.clients))
        await runtime.close()
        self.assertTrue(self.clients[0].is_closed)

    async def test_retry_owner_and_auth_error_redaction(self):
        attempts = []

        def handler(request):
            attempts.append(1)
            return httpx.Response(
                429 if len(attempts) == 1 else 200,
                headers={"Retry-After": "0"},
                json={"data": [{"index": 0, "embedding": [3, 4]}]},
            )

        runtime = self.runtime(handler, attempts=2)
        self.assertEqual([0.6, 0.8], await runtime.embed_query("retry"))
        self.assertEqual(2, len(attempts))

        denied = []

        def reject(request):
            denied.append(1)
            return httpx.Response(401, text="test-secret private response")

        runtime = self.runtime(reject, attempts=3)
        with self.assertRaises(ProviderError) as raised:
            await runtime.embed_query("denied")
        self.assertEqual(
            ProviderCode.PROVIDER_AUTHENTICATION_FAILED, raised.exception.code
        )
        self.assertEqual(1, len(denied))
        self.assertNotIn("test-secret", str(raised.exception.to_snapshot()))
        self.assertIsNone(raised.exception.__cause__.__cause__)

    async def test_transport_logs_do_not_expose_endpoint_or_key(self):
        runtime = self.runtime(
            lambda request: httpx.Response(
                200, json={"data": [{"index": 0, "embedding": [3, 4]}]}
            )
        )
        with self.assertLogs("httpx", level="INFO") as recorded:
            await runtime.warmup()
        output = str(recorded.output)
        self.assertIn("200 OK", output)
        self.assertNotIn("embedding.example.test", output)
        self.assertNotIn("test-secret", output)

    async def test_malformed_responses_fail_closed(self):
        cases = [
            {},
            {"data": []},
            {"data": [{"index": True, "embedding": [1, 0]}]},
            {"data": [{"index": 1, "embedding": [1, 0]}]},
            {
                "data": [
                    {"index": 0, "embedding": [1, 0]},
                    {"index": 0, "embedding": [1, 0]},
                ]
            },
            {"data": [{"index": 0, "embedding": [1]}]},
            {"data": [{"index": 0, "embedding": [True, 1]}]},
            {"data": [{"index": 0, "embedding": [0, 0]}]},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                runtime = self.runtime(
                    lambda request: httpx.Response(200, json=payload)
                )
                with self.assertRaises(ProviderError):
                    await runtime.embed_query("invalid")
                self.assertFalse(runtime.readiness().ready)
                self.assertEqual(0, runtime.stats().encoded_texts)
                await runtime.close()

        runtime = self.runtime(
            lambda request: httpx.Response(
                200,
                content=b'{"data":[{"index":0,"embedding":[NaN,1]}]}',
                headers={"content-type": "application/json"},
            )
        )
        with self.assertRaises(ProviderError):
            await runtime.embed_query("non-finite")

    async def test_deadline_cancels_the_http_request(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def handler(request):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        runtime = self.runtime(handler)
        call = asyncio.create_task(
            runtime.embed_query("slow", deadline=time.monotonic() + 0.15)
        )
        await asyncio.wait_for(started.wait(), 1)
        with self.assertRaises(ProviderError) as raised:
            await call
        self.assertEqual(ProviderCode.PROVIDER_DEADLINE_EXCEEDED, raised.exception.code)
        await asyncio.wait_for(cancelled.wait(), 1)

    async def test_redirect_and_oversized_response_are_rejected(self):
        for response in (
            httpx.Response(307, headers={"Location": "https://other.example.test"}),
            httpx.Response(
                200,
                content=b" " * (4 * 1024 * 1024 + 1),
                headers={"content-type": "application/json"},
            ),
        ):
            calls = []

            def handler(request):
                calls.append(str(request.url))
                return response

            runtime = self.runtime(handler)
            with self.assertRaises(ProviderError):
                await runtime.embed_query("rejected")
            self.assertEqual(1, len(calls))
            await runtime.close()

    async def test_concurrent_tenants_do_not_share_inflight_vectors(self):
        entered = asyncio.Event()
        calls = []

        async def handler(request):
            calls.append(1)
            index = len(calls)
            if index == 2:
                entered.set()
            await entered.wait()
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": 0, "embedding": [3, 4] if index == 1 else [4, 3]}
                    ]
                },
            )

        runtime = self.runtime(handler)
        first, second = await asyncio.wait_for(
            asyncio.gather(
                runtime.embed_query(
                    "shared text", scope=EmbeddingScope(tenant_id="first")
                ),
                runtime.embed_documents(
                    ["shared text"], scope=EmbeddingScope(tenant_id="second")
                ),
            ),
            2,
        )
        self.assertNotEqual(first, second[0])
        self.assertEqual(2, len(calls))

    async def test_cancelling_one_deduplicated_waiter_keeps_the_other_request(self):
        started = asyncio.Event()
        release = asyncio.Event()
        calls = []

        async def handler(request):
            calls.append(1)
            started.set()
            await release.wait()
            return httpx.Response(
                200, json={"data": [{"index": 0, "embedding": [3, 4]}]}
            )

        runtime = self.runtime(handler)
        first = asyncio.create_task(runtime.embed_query("shared"))
        second = asyncio.create_task(runtime.embed_query("shared"))
        await started.wait()
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        release.set()
        self.assertEqual([0.6, 0.8], await second)
        self.assertEqual(1, len(calls))


class RemoteEmbeddingSettingsTests(unittest.TestCase):
    def test_remote_index_identity_is_distinct_and_never_contains_secret(self):
        local = EmbeddingSettings(_env_file=None)
        remote = local.model_copy(
            update={
                "provider": "openai-compatible",
                "base_url": "https://api.example.test/v1",
                "api_key": SecretStr("private-token"),
            }
        )
        self.assertNotEqual(local.index_identity, remote.index_identity)
        self.assertNotIn("private-token", remote.index_identity)
        changed = remote.model_copy(
            update={"base_url": "https://other.example.test/v1"}
        )
        self.assertNotEqual(remote.index_identity, changed.index_identity)
        changed = remote.model_copy(update={"api_key": SecretStr("rotated-token")})
        self.assertEqual(remote.index_identity, changed.index_identity)
