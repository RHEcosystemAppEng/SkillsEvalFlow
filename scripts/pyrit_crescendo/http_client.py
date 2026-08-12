"""Generic HTTP chat client for non-A2A Crescendo targets."""

from __future__ import annotations

import httpx


def send_http_chat(
    endpoint: str,
    prompt: str,
    timeout: float = 120.0,
) -> str:
    """Send a single-turn chat-style HTTP request.

    Expects an OpenAI-compatible or simple messages body. Returns response text.
    Multi-turn context is carried only via the attacker prompt history for HTTP.
    """
    payload = {
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = httpx.post(
        endpoint,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()

    # OpenAI-style
    choices = data.get("choices") or []
    if choices:
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if content:
            return str(content).strip()

    # Plain text / common agent shapes
    for key in ("response", "output", "text", "content"):
        if data.get(key):
            return str(data[key]).strip()

    return str(data)[:2000] or "[No response]"
