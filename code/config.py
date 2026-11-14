"""Minimal .env loader (stdlib only) so both scripts pick up the Dify keys.

Accepts the common spellings, quoted or not:

    DIFY_API_KEY=app-xxx
    'dify-web'=app-xxx
    dify-judge=app-yyy
    DIFY_API_BASE=https://api.dify.ai/v1

Existing environment variables always win, so `$env:DIFY_API_KEY=...` still
overrides the file.
"""
from __future__ import annotations

import os
from pathlib import Path

import paths

# .env 的搜索顺序由 paths.py 统一给出（工作区根目录 -> repro -> code -> cwd）
CANDIDATES = paths.ENV_CANDIDATES

ALIASES = {
    "dify-web": "DIFY_API_KEY",
    "dify-web-key": "DIFY_API_KEY",
    "dify-agent": "DIFY_API_KEY",
    "dify-agent-key": "DIFY_API_KEY",
    "dify-api-key": "DIFY_API_KEY",
    "dify-judge": "DIFY_JUDGE_API_KEY",
    "dify-judge-key": "DIFY_JUDGE_API_KEY",
    "dify-judge-api-key": "DIFY_JUDGE_API_KEY",
    "dify-api-base": "DIFY_API_BASE",
    "dify-base": "DIFY_API_BASE",
}


def _clean(token: str) -> str:
    return token.strip().strip("'\"").strip()


def _canonical(key: str) -> str:
    norm = _clean(key).lower().replace("_", "-")
    if norm in ALIASES:
        return ALIASES[norm]
    return norm.upper().replace("-", "_")


def load_env(force: bool = False) -> list[str]:
    """Populate os.environ from the first .env found. Returns loaded key names."""
    loaded: list[str] = []
    for path in CANDIDATES:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:]
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = _clean(value.split(" #")[0])
            canonical = _canonical(key)
            if not canonical:
                continue
            if force or canonical not in os.environ:
                os.environ[canonical] = value
            loaded.append(canonical)
        break  # first existing file wins
    return loaded


def agent_key() -> str:
    load_env()
    return os.environ.get("DIFY_API_KEY", "")


def judge_key() -> str:
    """Fall back to the agent key only if no dedicated judge app is configured."""
    load_env()
    return os.environ.get("DIFY_JUDGE_API_KEY") or os.environ.get("DIFY_API_KEY", "")


def base_url() -> str:
    load_env()
    return os.environ.get("DIFY_API_BASE", "https://api.dify.ai/v1")


if __name__ == "__main__":
    names = load_env()
    print("loaded keys:", ", ".join(sorted(set(names))) or "(none)")
    print("agent key :", "set" if agent_key() else "MISSING")
    print("judge key :", "set" if judge_key() else "MISSING")
    print("base url  :", base_url())
