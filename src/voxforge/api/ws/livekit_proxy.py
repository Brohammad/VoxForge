"""Same-origin reverse proxy for local LiveKit (Safari / locked-down browsers).

Browsers often fail to open ``ws://127.0.0.1:7880`` when LiveKit runs in Docker.
Serving signal under the API origin (``ws://127.0.0.1:8000/lk/...``) avoids that.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import httpx
import websockets
from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect

from voxforge.config import get_settings

router = APIRouter(tags=["livekit-proxy"])


def _upstream_http_base() -> str | None:
    settings = get_settings()
    raw = (settings.livekit_url or "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    host = parts.hostname or "127.0.0.1"
    port = parts.port or (443 if parts.scheme in {"wss", "https"} else 80)
    scheme = "https" if parts.scheme in {"wss", "https"} else "http"
    return f"{scheme}://{host}:{port}"


def _upstream_ws_base() -> str | None:
    settings = get_settings()
    raw = (settings.livekit_url or "").strip()
    return raw.rstrip("/") if raw else None


def browser_livekit_url(request: Request) -> str:
    """URL returned to browser clients; may be same-origin ``/lk`` for local LiveKit."""
    settings = get_settings()
    upstream = (settings.livekit_url or "").rstrip("/")
    local_markers = ("127.0.0.1:7880", "localhost:7880", "0.0.0.0:7880")
    if any(m in upstream for m in local_markers):
        host = request.headers.get("host") or "127.0.0.1:8000"
        scheme = "wss" if request.url.scheme == "https" else "ws"
        return f"{scheme}://{host}/lk"
    return upstream


@router.websocket("/lk/{path:path}")
async def livekit_ws_proxy(websocket: WebSocket, path: str) -> None:
    upstream_base = _upstream_ws_base()
    if not upstream_base:
        await websocket.close(code=1011, reason="LiveKit not configured")
        return

    query = websocket.scope.get("query_string", b"").decode()
    target = f"{upstream_base}/{path}"
    if query:
        target = f"{target}?{query}"

    await websocket.accept()
    try:
        async with websockets.connect(
            target,
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
            open_timeout=10,
        ) as upstream:

            async def client_to_upstream() -> None:
                try:
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect":
                            break
                        data = message.get("bytes")
                        if data is not None:
                            await upstream.send(data)
                            continue
                        text = message.get("text")
                        if text is not None:
                            await upstream.send(text)
                except WebSocketDisconnect:
                    pass

            async def upstream_to_client() -> None:
                try:
                    async for message in upstream:
                        if isinstance(message, bytes):
                            await websocket.send_bytes(message)
                        else:
                            await websocket.send_text(message)
                except Exception:
                    pass

            t1 = asyncio.create_task(client_to_upstream())
            t2 = asyncio.create_task(upstream_to_client())
            done, pending = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                _ = task.exception() if not task.cancelled() else None
    except Exception:
        try:
            await websocket.close(code=1011, reason="LiveKit upstream unavailable")
        except Exception:
            pass


@router.api_route("/lk/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def livekit_http_proxy(path: str, request: Request) -> Response:
    base = _upstream_http_base()
    if not base:
        return Response(status_code=503, content="LiveKit not configured")

    query = request.url.query
    target = f"{base}/{path}"
    if query:
        target = f"{target}?{query}"

    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in {"host", "content-length", "connection"}
    }
    body = await request.body()

    async with httpx.AsyncClient(timeout=30.0) as client:
        upstream = await client.request(request.method, target, headers=headers, content=body)

    excluded = {"content-encoding", "transfer-encoding", "content-length"}
    out_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in excluded}
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=out_headers,
        media_type=upstream.headers.get("content-type"),
    )
