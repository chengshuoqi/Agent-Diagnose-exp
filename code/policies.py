"""Policies for the browser loop.

- DifyPolicy: asks the Dify app for the next action (the real experiment).
- ScriptedPolicy: deterministic fallback that exercises search -> open product ->
  answer, so the whole pipeline can be smoke-tested without an API key.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from dify_client import DifyError, answer_text, chat

PROMPT_TEMPLATE = """You are a web navigation agent controlling a Chrome browser on an e-commerce site.

TASK
{objective}

HOW TO READ THE PAGE
You get a pruned accessibility tree. Every interactive element has a numeric id:
    [<id>] link 'My Cart'
    [<id>] combobox 'Search' value='backpack'
    [<id>] button 'Add to Cart'
Bare text nodes (prices, ratings) appear as:
    text '$119.99'
The real ids are only the ones in the PAGE section below -- never copy the
placeholder <id> from these examples.

ALLOWED ACTIONS (reply with exactly ONE per turn, on its own line)
    click(<id>)
    type(<id>, "text")
    submit(<id>, "text")          # type the text then press Enter
    goto("http://localhost:7770/some/path")
    go_back()
    scroll(<pixels>)
    send_msg_to_user("your final answer")   # only when the task is finished

RULES
- Write one or two sentences of reasoning first, prefixed with "Thought:".
- Then write the single action on the last line, and nothing after it.
- Never invent element ids; only use ids that appear in the page below.
- When the task asks you to report something, finish with send_msg_to_user(...) containing the answer.

CURRENT URL
{url}

PAGE
{observation}

ACTION HISTORY (oldest first)
{history}

Your response:"""


class DifyPolicy:
    def __init__(self, api_key: Optional[str] = None, user: str = "agentdiagnose-repro",
                 base: Optional[str] = None):
        self.api_key = api_key
        self.user = user
        self.base = base

    def act(self, task: Dict[str, Any], observation: str, history: List[Dict[str, str]],
            url: str, step: int) -> Dict[str, str]:
        hist = "\n".join(f"{i + 1}. {h['action']}" for i, h in enumerate(history)) or "(none)"
        prompt = PROMPT_TEMPLATE.format(
            objective=task["objective"],
            url=url,
            observation=observation,
            history=hist,
        )
        resp = chat(prompt, api_key=self.api_key, user=self.user, base=self.base)
        text = answer_text(resp).strip()
        action = _extract_action(text)
        return {"raw": text, "reasoning": _extract_thought(text), "action": action}


def _split_thinking(text: str) -> tuple[str, str]:
    """Separate a reasoning model's <think> block from the final answer."""
    think = []
    for pat in (r"<think>(.*?)</think>", r"<thinking>(.*?)</thinking>"):
        for m in re.finditer(pat, text, re.S | re.I):
            think.append(m.group(1).strip())
        text = re.sub(pat, "", text, flags=re.S | re.I)
    text = text.replace("<!--dify-deepseek-reasoning-->", "")
    return text.strip(), "\n".join(think).strip()


def _extract_thought(text: str) -> str:
    answer, think = _split_thinking(text)
    m = re.search(r"Thought:\s*(.+?)(?=\n\s*(?:click|type|submit|goto|go_back|scroll|send_msg_to_user)\s*\(|$)",
                  answer, re.S | re.I)
    if m:
        return m.group(1).strip()[:800]
    return think[:800]


def _extract_action(text: str) -> str:
    answer, _ = _split_thinking(text)
    answer = answer.replace("```", "")
    pattern = re.compile(r"(click|type|submit|goto|go_back|scroll|send_msg_to_user)\s*\((?:[^()]|\([^()]*\))*\)")
    last = None
    for m in pattern.finditer(answer):
        last = m.group(0)
    if not last:
        return ""
    last = last.strip()
    # Reject the model echoing the template instead of a real action, e.g.
    # `send_msg_to_user(...)`, `click(<id>)` -- observed once in practice and it
    # silently produced an empty final answer.
    if "..." in last or "…" in last or "<" in last:
        return ""
    name = last.split("(", 1)[0].strip()
    arg = last.split("(", 1)[1].rstrip(")").strip()
    if name in ("click", "press", "scroll"):
        if not re.fullmatch(r"-?\d+", arg):
            return ""
    elif name in ("type", "submit"):
        first = arg.split(",", 1)[0].strip()
        if not re.fullmatch(r"-?\d+", first):
            return ""
    elif name == "send_msg_to_user":
        if not re.fullmatch(r"(['\"]).+\1", arg, re.S):
            return ""
    return last


class ScriptedPolicy:
    """Deterministic baseline: search -> open first product -> report price / add to cart."""

    def __init__(self) -> None:
        self._state: Dict[str, Dict[str, bool]] = {}

    def act(self, task: Dict[str, Any], observation: str, history: List[Dict[str, str]],
            url: str, step: int) -> Dict[str, str]:
        st = self._state.setdefault(task["id"], {"cart_clicked": False})
        actions = [h["action"] for h in history]
        query = task.get("query") or ""
        on_product_page = ".html" in url and "catalogsearch" not in url

        if query and not any(a.startswith(("submit(", "type(")) for a in actions):
            box = _find(observation, r"\[(\d+)\] (?:combobox|searchbox|textbox) 'Search'")
            if box:
                return {"raw": "", "reasoning": "Use the site search box.",
                        "action": f'submit({box}, "{query}")'}

        if "catalogsearch" in url and not on_product_page and not any(
                a.startswith("click(") for a in actions):
            link = _first_product_link(observation)
            if link:
                return {"raw": "", "reasoning": "Open the first product result.",
                        "action": f"click({link})"}

        if task.get("check") == "cart":
            if st["cart_clicked"] or "added to your shopping cart" in observation.lower():
                return {"raw": "", "reasoning": "Product added, task complete.",
                        "action": 'send_msg_to_user("Added the product to the cart.")'}
            cart_btn = _find(observation, r"\[(\d+)\] button 'Add to Cart'")
            if cart_btn:
                st["cart_clicked"] = True
                return {"raw": "", "reasoning": "Add the product to the cart.",
                        "action": f"click({cart_btn})"}
            return {"raw": "", "reasoning": "No add-to-cart button on this page.",
                    "action": 'send_msg_to_user("Could not find an Add to Cart button.")'}

        if on_product_page:
            price = re.search(r"(?:text|StaticText) '(\$[0-9][0-9.,]*)'", observation)
            if price:
                return {"raw": "", "reasoning": "Report the price on the product page.",
                        "action": f'send_msg_to_user("The price is {price.group(1)}.")'}

        return {"raw": "", "reasoning": "Nothing else to do.",
                "action": 'send_msg_to_user("I could not complete the task.")'}


def _find(text: str, pattern: str) -> Optional[int]:
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None


BAD_LINK_WORDS = (
    "review", "add to", "compare", "wish", "cart", "search", "skip", "image",
    "set ascending", "view as", "advanced", "sort", "account", "sign", "logo",
    "privacy", "terms", "contact", "orders", "subscribe", "home", "shop by",
)


def _first_product_link(text: str) -> Optional[int]:
    """Pick the first line that looks like a product title link."""
    for line in text.splitlines():
        m = re.match(r"\s*\[(\d+)\] link '(.{30,})'", line)
        if not m:
            continue
        name = m.group(2).lower()
        if any(bad in name for bad in BAD_LINK_WORDS):
            continue
        return int(m.group(1))
    return None
