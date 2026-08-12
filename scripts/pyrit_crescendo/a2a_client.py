"""A2A JSON-RPC client for multi-turn Crescendo attacks."""

from __future__ import annotations

import uuid

import httpx


def extract_a2a_text(data: dict) -> str:
    """Extract visible response text, skipping adk_thought parts."""
    result = data.get("result", {})
    text_parts: list[str] = []

    for artifact in result.get("artifacts", []):
        for part in artifact.get("parts", []):
            if part.get("kind") == "text":
                metadata = part.get("metadata") or {}
                if not metadata.get("adk_thought"):
                    text_parts.append(part.get("text", ""))

    if not text_parts:
        for msg in reversed(result.get("history", [])):
            if msg.get("role") == "agent":
                for part in msg.get("parts", []):
                    if part.get("kind") == "text":
                        metadata = part.get("metadata") or {}
                        if not metadata.get("adk_thought"):
                            text_parts.append(part.get("text", ""))
                if text_parts:
                    break

    if not text_parts:
        status = result.get("status") or {}
        state = (status.get("state") or "").lower()
        if state in ("failed", "rejected"):
            reason = status.get("reason") or status.get("message") or "safety policy"
            return f"[Blocked by agent safety filter: {reason}]"
        status_msg = status.get("message") or {}
        for part in status_msg.get("parts") or []:
            if part.get("kind") == "text":
                text_parts.append(part.get("text", ""))

    return "\n".join(text_parts).strip() or "[No response]"


def send_a2a_message(
    endpoint: str,
    prompt: str,
    context_id: str | None = None,
    timeout: float = 120.0,
) -> tuple[str, str | None]:
    """Send a prompt via A2A JSON-RPC message/send.

    Returns (response_text, context_id).
    """
    payload: dict = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": f"pyrit-{uuid.uuid4().hex[:8]}",
                "role": "user",
                "parts": [{"kind": "text", "text": prompt}],
            }
        },
        "id": f"req-{uuid.uuid4().hex[:8]}",
    }
    if context_id:
        payload["params"]["contextId"] = context_id

    resp = httpx.post(
        endpoint,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    result = data.get("result", {})
    new_context_id = result.get("contextId", context_id)
    return extract_a2a_text(data), new_context_id
