"""Tiny stdlib-only client for the Dify chat API.

Used both as the *policy* (browser agent) and as the *judge* (AgentDiagnose
rubric scoring). No third-party dependencies, so it also works in the plain
system Python.

    set DIFY_API_KEY=app-xxxxxxxx
    python -c "from dify_client import chat; print(chat('hello'))"
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

import config as _config

_config.load_env()  # pick up DIFY_* from the .env file if present

DEFAULT_BASE = os.environ.get("DIFY_API_BASE", "https://api.dify.ai/v1")


class DifyError(RuntimeError):
    pass


def chat(
    query: str,
    api_key: str | None = None,
    user: str = "agentdiagnose-repro",
    base: str | None = None,
    conversation_id: str = "",
    inputs: dict | None = None,
    timeout: int = 180,
    retries: int = 2,
) -> dict:
    """Send one chat message and return a dict with an `answer` field.

    Blocking mode is used when the app supports it; Dify *Agent* apps reject it
    ("Agent Chat App does not support blocking mode"), so the client falls back
    to streaming automatically and reassembles the answer from the SSE events.
    """
    key = api_key or _config.agent_key()
    if not key:
        raise DifyError("no Dify API key: put DIFY_API_KEY=app-... in repro/.env "
                        "(or export it, or create one in the app: 访问 API -> API 密钥)")

    base = (base or DEFAULT_BASE).rstrip("/")
    payload = {
        "inputs": inputs or {},
        "query": query,
        "response_mode": "blocking",
        "conversation_id": conversation_id,
        "user": user,
        "auto_generate_name": False,
    }

    if _MODE.get(base) == "streaming":
        return _chat_stream(base, key, payload, timeout)

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{base}/chat-messages",
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            if exc.code == 400 and ("streaming response mode" in detail
                                    or "does not support blocking mode" in detail):
                _MODE[base] = "streaming"
                return _chat_stream(base, key, payload, timeout)
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                last_err = DifyError(f"HTTP {exc.code}: {detail}")
                continue
            raise DifyError(f"HTTP {exc.code} from Dify: {detail}") from exc
        except Exception as exc:  # network errors
            last_err = exc
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise DifyError(f"request to Dify failed: {exc}") from exc
    raise DifyError(str(last_err))


_MODE: dict[str, str] = {}


def _chat_stream(base: str, key: str, payload: dict, timeout: int) -> dict:
    """Streaming mode: read the SSE events and concatenate the answer chunks."""
    payload = dict(payload, response_mode="streaming")
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/chat-messages",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    chunks: list[str] = []
    agent_chunks: list[str] = []
    thoughts: list[str] = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data in ("", "[DONE]"):
                    continue
                try:
                    evt = json.loads(data)
                except json.JSONDecodeError:
                    continue
                kind = evt.get("event", "")
                if kind == "message":
                    chunks.append(evt.get("answer", "") or "")
                elif kind == "agent_message":
                    # agent apps stream the same text as both `message` and
                    # `agent_message`, so keep them apart and prefer `message`
                    agent_chunks.append(evt.get("answer", "") or "")
                elif kind == "agent_thought":
                    thoughts.append(evt.get("thought", "") or "")
                elif kind == "error":
                    raise DifyError(f"stream error: {evt.get('message', evt)}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise DifyError(f"HTTP {exc.code} from Dify (stream): {detail}") from exc

    answer = "".join(chunks).strip() or "".join(agent_chunks).strip()
    if not answer and thoughts:
        answer = thoughts[-1]
    return {"event": "message", "answer": answer, "mode": "streaming",
            "thoughts": thoughts}


def answer_text(resp: dict) -> str:
    """Extract the assistant text from a Dify chat-messages response."""
    if not isinstance(resp, dict):
        return ""
    if "answer" in resp:
        return str(resp["answer"])
    if "data" in resp and isinstance(resp["data"], dict):
        for key in ("answer", "outputs", "text"):
            if key in resp["data"]:
                value = resp["data"][key]
                return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return ""


if __name__ == "__main__":
    import sys

    prompt = sys.argv[1] if len(sys.argv) > 1 else "ping"
    out = chat(prompt)
    print(answer_text(out)[:2000])
