"""Minimal browser tool layer for the AgentDiagnose reproduction.

Gives a WebArena-style observation (accessibility tree with element ids) and a
small action space, without needing browsergym:

    click(id) | type(id, "text") | press(id, "Enter")
    goto(url) | go_back() | scroll(dy) | send_msg_to_user("text")

Observations are pruned accessibility-tree lines, one node per line, with a
numeric id in front of every interactive element so the policy can refer to it.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import sync_playwright

import paths

INTERACTIVE_ROLES = {
    "link", "button", "textbox", "searchbox", "combobox", "checkbox", "radio",
    "menuitem", "menuitemcheckbox", "tab", "option", "switch", "slider",
    "spinbutton", "listbox", "treeitem",
}

# Roles that carry no useful information on their own; their children are
# promoted so the tree stays shallow.
TRANSPARENT_ROLES = {
    "generic", "none", "presentation", "InlineTextBox", "LineBreak", "paragraph",
    "StaticText", "group", "list", "listitem", "row", "cell", "table",
    "LayoutTable", "LayoutTableRow", "LayoutTableCell", "section", "article",
}

MAX_NAME_LEN = 160


def use_local_temp() -> Optional[str]:
    """Point TMPDIR/TEMP/TMP at a writable folder before Playwright starts.

    On Windows the system temp dir is sometimes not writable for the sandboxed
    token, which shows up as:
        EPERM: operation not permitted, mkdtemp ...\\Temp\\playwright-artifacts-XXXXXX
    Playwright and the Chrome it launches both honour these variables.
    """
    base = paths.TMP
    try:
        base.mkdir(parents=True, exist_ok=True)
        probe = base / f".writable-{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except Exception:
        return None
    for var in ("TMPDIR", "TEMP", "TMP"):
        os.environ[var] = str(base)
    return str(base)


class BrowserSession:
    def __init__(self, headless: bool = True, viewport: Tuple[int, int] = (1280, 900)):
        use_local_temp()
        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.launch(channel="chrome", headless=headless)
        except Exception as exc:  # give an actionable message instead of EPERM
            self._pw.stop()
            raise RuntimeError(
                "Chrome/Playwright could not start. If the error mentions "
                "'mkdtemp' or 'EPERM', the temp directory is not writable: "
                "set $env:TEMP and $env:TMP to a folder you own (e.g. repro\\.tmp) "
                f"and retry. Original error: {exc}"
            ) from exc
        self.context = self.browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
        self.page = self.context.new_page()
        self.cdp = self.context.new_cdp_session(self.page)
        self.cdp.send("DOM.enable")
        self.cdp.send("Accessibility.enable")
        self._id_map: Dict[int, int] = {}

    # ------------------------------------------------------------------ utils
    def close(self) -> None:
        try:
            self.context.close()
        finally:
            try:
                self.browser.close()
            finally:
                self._pw.stop()

    def goto(self, url: str, timeout: int = 60000) -> None:
        self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        self._settle()

    def _settle(self, ms: int = 600) -> None:
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        self.page.wait_for_timeout(ms)

    # ------------------------------------------------------------- observation
    def observe(self, max_lines: int = 220) -> Tuple[str, Dict[int, int]]:
        tree = self.cdp.send("Accessibility.getFullAXTree")
        nodes = {n["nodeId"]: n for n in tree.get("nodes", [])}
        if not nodes:
            return "(empty page)", {}

        root = None
        for n in tree["nodes"]:
            if "parentId" not in n:
                root = n
                break
        root = root or tree["nodes"][0]

        lines: List[str] = []
        id_map: Dict[int, int] = {}
        next_id = [0]

        def walk(node: Dict[str, Any], depth: int, parent_name: str = "") -> None:
            if len(lines) >= max_lines:
                return
            role = (node.get("role") or {}).get("value", "")
            name = (node.get("name") or {}).get("value", "") or ""
            ignored = node.get("ignored", False)
            children = [nodes[c] for c in node.get("childIds", []) if c in nodes]

            if role == "InlineTextBox" or role == "LineBreak":
                return

            name = re.sub(r"\s+", " ", name).strip()
            # strip private-use glyphs (icon fonts like Magento's)
            name = "".join(ch for ch in name if not (0xE000 <= ord(ch) <= 0xF8FF)).strip()

            if role == "StaticText":
                # keep bare text (prices, ratings, descriptions) but drop the
                # duplicate copies that merely repeat the parent's name
                if name and name != parent_name:
                    lines.append(f"{'  ' * depth}text {name[:MAX_NAME_LEN]!r}")
                    for c in children:
                        walk(c, depth + 1, name)
                return

            if ignored or role in ("none", "presentation"):
                for c in children:
                    walk(c, depth, parent_name)
                return

            if not name and role in TRANSPARENT_ROLES:
                for c in children:
                    walk(c, depth, parent_name)
                return

            shown = name[:MAX_NAME_LEN]
            value = (node.get("value") or {}).get("value") if isinstance(node.get("value"), dict) else None
            bid = node.get("backendDOMNodeId")

            if role in INTERACTIVE_ROLES and bid:
                next_id[0] += 1
                eid = next_id[0]
                id_map[eid] = bid
                prefix = f"[{eid}]"
                extra = f" value={str(value)[:40]!r}" if value else ""
                lines.append(f"{'  ' * depth}{prefix} {role} {shown!r}{extra}")
            elif shown:
                lines.append(f"{'  ' * depth}{role} {shown!r}")

            for c in children:
                walk(c, depth + 1, shown)

        walk(root, 0)
        self._id_map = id_map
        if len(lines) >= max_lines:
            lines.append("... (observation truncated)")
        return "\n".join(lines), id_map

    # ----------------------------------------------------------------- actions
    def _resolve(self, eid: int) -> Optional[str]:
        bid = self._id_map.get(int(eid))
        if not bid:
            return None
        try:
            res = self.cdp.send("DOM.resolveNode", {"backendNodeId": bid})
            return res.get("object", {}).get("objectId")
        except Exception:
            return None

    def _call(self, object_id: str, fn: str, args: Optional[List[Any]] = None) -> Any:
        payload = {
            "objectId": object_id,
            "functionDeclaration": fn,
            "returnByValue": True,
        }
        if args:
            payload["arguments"] = [{"value": a} for a in args]
        return self.cdp.send("Runtime.callFunctionOn", payload)

    def click(self, eid: int) -> str:
        """Real mouse click at the element centre (Magento's JS handlers need it)."""
        bid = self._id_map.get(int(eid))
        if not bid:
            return f"error: unknown element id {eid}"
        oid = self._resolve(eid)
        if oid:
            try:
                self._call(oid, "function(){ this.scrollIntoView({block:'center'}); return 'ok'; }")
                self.page.wait_for_timeout(250)
            except Exception:
                pass
        try:
            box = self.cdp.send("DOM.getBoxModel", {"backendNodeId": bid})["model"]["content"]
            xs, ys = box[0::2], box[1::2]
            cx, cy = sum(xs) / 4.0, sum(ys) / 4.0
            self.page.mouse.click(cx, cy)
        except Exception:
            # fall back to a scripted click for elements without a box model
            if not oid:
                return f"error: cannot click element {eid}"
            try:
                self._call(oid, "function(){ this.click(); return 'ok'; }")
            except Exception as exc:
                return f"error: click failed ({exc})"
        self._settle()
        return "ok"

    def type_text(self, eid: int, text: str, press_enter: bool = False) -> str:
        bid = self._id_map.get(int(eid))
        if not bid:
            return f"error: unknown element id {eid}"
        oid = self._resolve(eid)
        if not oid:
            return f"error: unknown element id {eid}"
        # focus with a real click first: focusing via JS is not enough for
        # Magento's search form and can leave the caret on another element
        try:
            box = self.cdp.send("DOM.getBoxModel", {"backendNodeId": bid})["model"]["content"]
            xs, ys = box[0::2], box[1::2]
            self.page.mouse.click(sum(xs) / 4.0, sum(ys) / 4.0)
            self.page.wait_for_timeout(150)
        except Exception:
            self._call(oid, "function(){ this.focus(); return 'ok'; }")

        editable = self.page.evaluate(
            "() => { const e = document.activeElement;"
            " return !!e && (e.tagName === 'INPUT' || e.tagName === 'TEXTAREA' || e.isContentEditable); }")
        if not editable:
            # overlays (sticky headers, checkout modals) can swallow the mouse
            # click; fall back to focusing the node directly before giving up
            try:
                self._call(oid, "function(){ this.focus(); return 'ok'; }")
                self.page.wait_for_timeout(100)
            except Exception:
                pass
            editable = self.page.evaluate(
                "() => { const e = document.activeElement;"
                " return !!e && (e.tagName === 'INPUT' || e.tagName === 'TEXTAREA' || e.isContentEditable); }")
        if not editable:
            return f"error: element {eid} is not a text field (focus did not land on an input)"

        try:
            self._call(oid, "function(){ this.value = ''; return 'ok'; }")
            self.page.keyboard.type(text, delay=25)
            if press_enter:
                # Do not press Enter blindly: on Magento the search box opens an
                # autocomplete list and Enter would pick a suggestion (e.g. a
                # category) instead of submitting the search. Submit the form.
                submitted = self.page.evaluate(
                    """() => { const e = document.activeElement;
                        if (!e || !e.form) return 'noform';
                        e.form.requestSubmit ? e.form.requestSubmit() : e.form.submit();
                        return 'submitted'; }""")
                if submitted != "submitted":
                    self.page.keyboard.press("Enter")
        except Exception as exc:
            return f"error: typing failed ({exc})"
        self._settle()
        return "ok"

    def press(self, eid: int, key: str) -> str:
        oid = self._resolve(eid)
        if not oid:
            return f"error: unknown element id {eid}"
        try:
            self._call(oid, "function(){ this.focus(); return 'ok'; }")
            self.page.keyboard.press(key)
        except Exception as exc:
            return f"error: press failed ({exc})"
        self._settle()
        return "ok"

    def scroll(self, dy: int = 600) -> str:
        self.page.mouse.wheel(0, dy)
        self.page.wait_for_timeout(400)
        return "ok"

    def go_back(self) -> str:
        try:
            self.page.go_back(wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            return f"error: go_back failed ({exc})"
        self._settle()
        return "ok"

    @property
    def url(self) -> str:
        return self.page.url


ACTION_RE = re.compile(r"^([a-z_]+)\s*\((.*)\)\s*$", re.S)


def parse_action(text: str) -> Tuple[str, List[Any]]:
    """Parse 'click(12)' / 'type(3, "red shoes")' into (name, args)."""
    text = text.strip().strip("`").strip()
    m = ACTION_RE.match(text)
    if not m:
        return "", []
    name, raw = m.group(1), m.group(2).strip()
    args: List[Any] = []
    if raw:
        buf, quote = "", None
        for ch in raw:
            if quote:
                if ch == quote:
                    quote = None
                else:
                    buf += ch
            elif ch in "'\"":
                quote = ch
            elif ch == ",":
                args.append(_coerce(buf))
                buf = ""
            else:
                buf += ch
        args.append(_coerce(buf))
    return name, args


def _coerce(raw: str) -> Any:
    raw = raw.strip()
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


def execute(session: BrowserSession, action: str) -> Tuple[str, bool]:
    """Run one action. Returns (observation message, done?)."""
    name, args = parse_action(action)
    if not name:
        return "error: could not parse action, expected e.g. click(12)", False
    if name == "click":
        return session.click(int(args[0])), False
    if name == "type":
        text = str(args[1]) if len(args) > 1 else ""
        return session.type_text(int(args[0]), text), False
    if name == "submit":
        return session.type_text(int(args[0]), str(args[1]) if len(args) > 1 else "", press_enter=True), False
    if name == "press":
        return session.press(int(args[0]), str(args[1]) if len(args) > 1 else "Enter"), False
    if name == "goto":
        try:
            session.goto(str(args[0]))
            return "ok", False
        except Exception as exc:
            return f"error: goto failed ({exc})", False
    if name == "go_back":
        return session.go_back(), False
    if name == "scroll":
        return session.scroll(int(args[0]) if args else 600), False
    if name == "send_msg_to_user":
        return "submitted final answer", True
    return f"error: unknown action {name!r}", False
