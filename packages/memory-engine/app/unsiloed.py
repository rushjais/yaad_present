"""
Unsiloed client — upload a document, then ask questions about it.

Two endpoints (confirmed working in STATUS.md, 2026-06-06):
  POST {base}/api/v1/playground/upload-document   multipart    → {document_id|id|doc_id}
  POST {base}/api/v1/playground/chat-with-document form-data    → {answer|response|text}

Auth: `Api-Key: <UNSILOED_API_KEY>` header on every request.

This is a thin transport layer. The medical-PDF → structured-memory pipeline
lives in `ingest.py`, which calls this client + Groq + write_memory.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .config import settings


UPLOAD_PATH = "/api/v1/playground/upload-document"
CHAT_PATH = "/api/v1/playground/chat-with-document"

# Unsiloed parse + index runs server-side; budget generously. Chat is faster.
_UPLOAD_TIMEOUT = 120.0
_CHAT_TIMEOUT = 60.0
_CHAT_NOT_READY_DELAYS = (3.0, 8.0, 15.0, 30.0)


def _headers() -> dict[str, str]:
    if not settings.unsiloed_api_key:
        raise RuntimeError("UNSILOED_API_KEY not set")
    return {"Api-Key": settings.unsiloed_api_key}


def _extract_doc_id(payload: Any) -> str:
    """Unsiloed has shipped a few response shapes during the beta; pull the id
    out of whichever field is populated. Raises if none found.
    """
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected upload response: {payload!r}")
    for key in ("document_id", "doc_id", "id", "documentId"):
        v = payload.get(key)
        if v:
            return str(v)
    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_doc_id(data)
    raise RuntimeError(f"No document id in upload response: {payload!r}")


def _extract_answer(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return str(payload)
    for key in ("answer", "response", "text", "message", "result"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v
    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_answer(data)
    return str(payload)


async def upload(file_bytes: bytes, filename: str,
                 content_type: str = "application/pdf") -> str:
    """Upload a document, return its document_id."""
    url = f"{settings.unsiloed_base_url}{UPLOAD_PATH}"
    # Unsiloed expects the multipart field to be named `document`.
    files = {"document": (filename, file_bytes, content_type)}
    async with httpx.AsyncClient(timeout=_UPLOAD_TIMEOUT) as client:
        resp = await client.post(url, headers=_headers(), files=files)
        resp.raise_for_status()
        return _extract_doc_id(resp.json())


async def chat(doc_id: str, question: str) -> str:
    """Ask a question about an uploaded document, return the raw answer text."""
    url = f"{settings.unsiloed_base_url}{CHAT_PATH}"
    # The playground endpoint expects form-data, not JSON, and the field is
    # `message` (not `question`).
    data = {"document_id": doc_id, "message": question}
    async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
        for delay in (0.0, *_CHAT_NOT_READY_DELAYS):
            if delay:
                await asyncio.sleep(delay)
            resp = await client.post(url, headers=_headers(), data=data)
            if not _is_document_not_ready(resp):
                resp.raise_for_status()
                return _extract_answer(resp.json())
        resp.raise_for_status()
        return _extract_answer(resp.json())


def _is_document_not_ready(resp: httpx.Response) -> bool:
    if resp.status_code != 404:
        return False
    try:
        payload = resp.json()
    except ValueError:
        return False
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return False
    message = str(error.get("message") or "").lower()
    return error.get("code") == "not_found" and "document not found" in message


async def ping() -> bool:
    """Cheap reachability check — does the API key auth at all?"""
    try:
        _headers()
    except RuntimeError:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # No documented health endpoint; a 404 with our key still proves reach.
            resp = await client.get(f"{settings.unsiloed_base_url}/", headers=_headers())
            return resp.status_code < 500
    except Exception:
        return False
