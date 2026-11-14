"""Run shopping episodes on the local WebArena shopping container and record
trajectories in AgentDiagnose's JSON format.

    python run_episodes.py --policy scripted --limit 2
    python run_episodes.py --policy dify --limit 10 --headed

Output: repro/trajectories/<task_id>.json, loadable by
`evaluator.trajectory.Trajectory.from_json` from the AgentDiagnose repo.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from browser_tools import BrowserSession, execute
from dify_client import DifyError
from policies import DifyPolicy, ScriptedPolicy

import paths
import provenance


def load_tasks(path: Path) -> List[Dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def page_text(session: BrowserSession) -> str:
    try:
        return session.page.inner_text("body", timeout=10000)
    except Exception:
        return ""


def verify(task: Dict[str, Any], session: BrowserSession, answers: List[str], base: str) -> Optional[bool]:
    check = task.get("check", "none")
    keywords = [k.lower() for k in task.get("answer_keywords", [])]
    if check == "none":
        return None
    if check == "answer":
        blob = " ".join(answers).lower()
        return any(k in blob for k in keywords)
    if check == "cart":
        try:
            session.goto(f"{base}/checkout/cart")
        except Exception:
            return False
        blob = page_text(session).lower()
        return any(k.lower() in blob for k in keywords)
    if check == "url":
        return any(k.lower() in session.url.lower() for k in keywords)
    return None


def run_task(task: Dict[str, Any], policy, args) -> Dict[str, Any]:
    session = BrowserSession(headless=not args.headed)
    steps: List[Dict[str, Any]] = []
    answers: List[str] = []
    error = None
    started = time.time()
    try:
        session.goto(task.get("start_url", f"{args.base_url}/"))
        observation, _ = session.observe(max_lines=args.max_obs_lines)
        for i in range(task.get("max_steps", args.max_steps)):
            try:
                decision = policy.act(task, observation, steps, session.url, i)
            except DifyError as exc:
                error = str(exc)
                break
            action = (decision.get("action") or "").strip()
            if not action:
                error = "policy returned no parseable action"
                steps.append(_step(task, session, "", decision.get("raw", ""), i + 1, "error: unparseable action"))
                break

            step = _step(task, session, action, decision.get("reasoning", ""), i + 1, observation)
            if decision.get("raw"):
                step["raw_response"] = decision["raw"][:4000]
            steps.append(step)
            if args.verbose:
                print(f"    step {i + 1}: {action}")
                if decision.get("raw"):
                    print(f"      raw: {decision['raw'].strip()[:300].replace(chr(10), ' | ')}")
            if action.startswith("send_msg_to_user"):
                answers.append(_action_arg(action))
                break

            result, done = execute(session, action)
            step["result"] = result
            if args.verbose:
                print(f"      result: {result}  url: {session.url[:90]}")
            if done:
                break
            observation, _ = session.observe(max_lines=args.max_obs_lines)
    except Exception as exc:  # keep partial trajectory for debugging
        error = f"{type(exc).__name__}: {exc}"
    finally:
        success = None
        try:
            success = verify(task, session, answers, args.base_url)
        except Exception:
            success = None
        if args.screenshots:
            try:
                shot = Path(args.out) / "shots" / f"{task['id']}.png"
                shot.parent.mkdir(parents=True, exist_ok=True)
                session.page.screenshot(path=str(shot))
            except Exception:
                pass
        final_url = session.url
        session.close()

    return {
        "objective": task["objective"],
        "actions": steps,
        "task_website": "localhost:7770",
        # 三态：1 成功 / 0 失败 / null 不适用（issue #7）。不再用 -1 冒充"不适用"。
        "reward": None if success is None else int(success),
        "meta": {
            "task_id": task["id"],
            "policy": args.policy,
            "check": task.get("check", "none"),
            "success": success,
            "error": error,
            "final_url": final_url,
            "n_steps": len(steps),
            "answers": answers,
            "elapsed_s": round(time.time() - started, 1),
            "note": task.get("note", ""),
        },
    }


def _step(task, session, action, reasoning, nth, observation) -> Dict[str, Any]:
    return {
        "action": action,
        "reasoning": reasoning,
        "action_type": action.split("(")[0] if action else "",
        "observation": (observation or "")[:20000],
        "url": session.url,
        "label_line": -1,
        "total_line": len((observation or "").splitlines()),
        "label_pos": -1,
        "nth_step": nth,
        "output": f"{reasoning}\n\nAction: {action}".strip(),
        "output_root_verb": "",
        "output_root_noun": "",
        "output_verb_pairs": [],
        "output_verb_noun_pairs": [],
        "image_encoding": None,
    }


def _action_arg(action: str) -> str:
    m = re.match(r'\w+\s*\(\s*(["\'])(.*?)\1\s*\)', action, re.S)
    return m.group(2) if m else ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=str(paths.TASKS))
    ap.add_argument("--out", default="",
                    help="轨迹目录；默认 output/runs/<run-id>/trajectories")
    ap.add_argument("--run-id", default="",
                    help="本次运行的标识；默认 <时间戳>-<policy>")
    ap.add_argument("--policy", choices=["dify", "scripted"], default="scripted")
    ap.add_argument("--limit", type=int, default=0, help="only run the first N tasks")
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--max-obs-lines", type=int, default=200)
    ap.add_argument("--base-url", default="http://localhost:7770")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="print each action and the raw LLM answer")
    ap.add_argument("--screenshots", action="store_true")
    ap.add_argument("--only", default="", help="comma separated task ids")
    ap.add_argument("--overwrite", action="store_true",
                    help="允许覆盖输出目录里已有的同名轨迹（默认跳过，见 issue #3）")
    args = ap.parse_args()

    tasks = load_tasks(Path(args.tasks))
    if args.only:
        wanted = {t.strip() for t in args.only.split(",") if t.strip()}
        tasks = [t for t in tasks if t["id"] in wanted]
    if args.limit:
        tasks = tasks[: args.limit]

    run_id = args.run_id or (time.strftime("%Y%m%dT%H%M") + "-" + args.policy)
    out = Path(args.out) if args.out else paths.RUNS / run_id / "trajectories"
    run_dir = out.parent
    out.mkdir(parents=True, exist_ok=True)
    args.out = str(out)          # run_task 用它决定截图落点

    policy = ScriptedPolicy() if args.policy == "scripted" else DifyPolicy()

    started = time.time()
    written: List[str] = []
    skipped: List[str] = []
    for task in tasks:
        path = out / f"{task['id']}.json"
        if path.exists() and not args.overwrite:
            print(f"[{task['id']}] 已存在，跳过（--overwrite 可覆盖）", flush=True)
            skipped.append(task["id"])
            continue
        print(f"[{task['id']}] running ...", flush=True)
        record = run_task(task, policy, args)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        meta = record["meta"]
        written.append(task["id"])
        print(f"    steps={meta['n_steps']} success={meta['success']} error={meta['error']} "
              f"({meta['elapsed_s']}s) -> {path.name}", flush=True)

    manifest = {
        "run_id": run_id,
        "policy": args.policy,
        "base_url": args.base_url,
        "tasks_file": str(Path(args.tasks).resolve()),
        "tasks_sha256": provenance.fingerprint(load_tasks(Path(args.tasks))),
        "n_tasks": len(tasks),
        "written": written,
        "skipped": skipped,
        "started_at": datetime.fromtimestamp(started, timezone.utc)
        .isoformat(timespec="seconds").replace("+00:00", "Z"),
        "finished_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds").replace("+00:00", "Z"),
        "elapsed_s": round(time.time() - started, 1),
    }
    (run_dir / "run.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nrun dir : {run_dir}")
    print(f"written : {len(written)}   skipped: {len(skipped)}")
    if skipped:
        print(f"跳过（已存在，未覆盖）: {', '.join(skipped)}")


if __name__ == "__main__":
    main()

