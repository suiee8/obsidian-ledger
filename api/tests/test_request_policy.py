from __future__ import annotations

import asyncio

from starlette.types import Message, Receive, Scope, Send

from obsidian_ledger.middleware import RequestPolicyMiddleware


def _scope(path: str, method: str = "POST") -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8000),
    }


async def _empty_receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


def test_heavy_jobs_are_limited_to_configured_concurrency() -> None:
    async def run() -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        first_response: list[Message] = []
        second_response: list[Message] = []

        async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
            started.set()
            await release.wait()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        policy = RequestPolicyMiddleware(
            downstream,
            heavy_limit=1,
            requests_per_minute=100,
            timeout_seconds=5,
        )

        async def first_send(message: Message) -> None:
            first_response.append(message)

        async def second_send(message: Message) -> None:
            second_response.append(message)

        first: asyncio.Task[None] = asyncio.create_task(
            policy(_scope("/api/simulate"), _empty_receive, first_send)
        )
        await started.wait()
        await policy(_scope("/api/simulate"), _empty_receive, second_send)
        release.set()
        await first

        assert second_response[0]["status"] == 503
        assert first_response[0]["status"] == 200

    asyncio.run(run())


def test_requests_receive_a_504_when_the_handler_exceeds_its_timeout() -> None:
    async def run() -> None:
        async def slow_handler(scope: Scope, receive: Receive, send: Send) -> None:
            await asyncio.sleep(0.05)

        policy = RequestPolicyMiddleware(
            slow_handler,
            heavy_limit=1,
            requests_per_minute=100,
            timeout_seconds=0.01,
        )
        response: list[Message] = []

        async def send(message: Message) -> None:
            response.append(message)

        await policy(_scope("/"), _empty_receive, send)
        assert response[0]["status"] == 504

    asyncio.run(run())
