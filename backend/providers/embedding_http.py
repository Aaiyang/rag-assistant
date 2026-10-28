"""One-attempt OpenAI-compatible embedding transport, owned by the Provider loop."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from backend.providers.core import (
    ProviderCallContext,
    ProviderCode,
    ProviderError,
    ProviderOperation,
    classify_provider_exception,
)


class _RedactTransportUrls(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                "[provider-endpoint]" if isinstance(value, httpx.URL) else value
                for value in record.args
            )
        return True


_HTTPX_URL_FILTER = _RedactTransportUrls()


class HttpxEmbeddingEncoder:
    """Reuse one async client; EmbeddingRuntime owns validation and retries."""

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        api_key: str,
        timeout_seconds: float,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
        max_response_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        self._endpoint = endpoint
        self._model = model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._client_factory = client_factory
        self._max_response_bytes = max_response_bytes
        self._client: httpx.AsyncClient | None = None
        self._owner_loop: asyncio.AbstractEventLoop | None = None

    async def encode(self, texts: Sequence[str]) -> list[Any]:
        loop = asyncio.get_running_loop()
        if self._owner_loop is None:
            self._owner_loop = loop
            # HTTPX INFO records contain URLs even when our own errors are redacted.
            logging.getLogger("httpx").addFilter(_HTTPX_URL_FILTER)
            # HTTPX's default transport has retries=0. Keeping client-level proxy
            # discovery allows the same explicit server configuration as other APIs.
            self._client = self._client_factory(
                timeout=self._timeout_seconds,
                follow_redirects=False,
                limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
            )
        elif self._owner_loop is not loop:
            raise RuntimeError("embedding HTTP client belongs to another event loop")
        assert self._client is not None
        context = ProviderCallContext(
            provider="embedding-api", operation=ProviderOperation.EMBEDDING
        )
        try:
            async with self._client.stream(
                "POST",
                self._endpoint,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "input": list(texts),
                    "encoding_format": "float",
                },
            ) as response:
                # Redirects must never forward the credential to another origin.
                if response.is_redirect:
                    raise ValueError("embedding redirects are unsupported")
                response.raise_for_status()
                if "application/json" not in response.headers.get("content-type", ""):
                    raise ValueError("embedding response must be JSON")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > self._max_response_bytes:
                        raise ValueError("embedding response exceeds byte budget")
                    body.extend(chunk)
            payload = json.loads(body)
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list) or len(data) != len(texts):
                raise ValueError("invalid embedding response count")
            ordered: dict[int, Any] = {}
            for row in data:
                index = row.get("index") if isinstance(row, dict) else None
                if (
                    type(index) is not int
                    or not 0 <= index < len(texts)
                    or index in ordered
                    or "embedding" not in row
                ):
                    raise ValueError("invalid embedding response index")
                ordered[index] = row["embedding"]
            return [ordered[index] for index in range(len(texts))]
        except httpx.HTTPError as exc:
            raise classify_provider_exception(exc, context=context) from None
        except (ValueError, TypeError):
            raise ProviderError(
                ProviderCode.PROVIDER_REQUEST_INVALID, context=context
            ) from None

    async def aclose(self) -> None:
        if self._client is not None:
            if self._owner_loop is not asyncio.get_running_loop():
                raise RuntimeError(
                    "embedding HTTP client belongs to another event loop"
                )
            await self._client.aclose()
