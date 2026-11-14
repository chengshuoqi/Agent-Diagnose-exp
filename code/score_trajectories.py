"""Score recorded trajectories with AgentDiagnose's rubric.

Uses the exact prompts from the paper's repo (loaded straight out of
AgentDiagnose-main/evaluator/scorers/prompts/prompt.py) and sends them to a Dify
app that acts as the judge.

    set DIFY_JUDGE_API_KEY=app-xxxx     (or reuse DIFY_API_KEY)
    python score_trajectories.py --input trajectories --out scores.json

--mock replaces the judge with a deterministic heuristic, useful to verify the
plumbing before you have a key.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dify_client import DifyError, answer_text, chat
import config

import paths
import provenance

REPO_PROMPTS = paths.REPO_PROMPTS

DIMENSIONS = ["backtrack_and_explore", "task_decomposition", "observation_reading", "self_verification"]


def load_prompts():
    """返回仓内的 rubric 快照模块（`code/prompts/agentdiagnose_rubric.py`）。

    不再在运行期读 `../AgentDiagnose-main`（issue #4）：那条路径不在版本库里、
    也没有 pin commit，rubric 会随外部文件静默漂移，而产物的 `prompt_sha256`
    也就失去了意义。
    """
    from prompts import agentdiagnose_rubric

    return agentdiagnose_rubric


PROMPT_ATTRS = (
    "REASONING_QUALITY_SYSTEM_PROMPT",
    "REASONING_QUALITY_USER_PROMPT",
    "OBJECTIVE_QUALITY_SYSTEM_PROMPT",
    "OBJECTIVE_QUALITY_USER_PROMPT",
)


def compare_with_upstream() -> int:
    """把快照与同级克隆逐字比对；返回不一致的条数。只读，不改任何文件。"""
    if not REPO_PROMPTS.exists():
        print(f"上游 prompt 不存在：{REPO_PROMPTS}（跳过比对）")
        return 0
    spec = importlib.util.spec_from_file_location("agentdiagnose_prompts", REPO_PROMPTS)
    if spec is None or spec.loader is None:
        print(f"无法加载上游 prompt：{REPO_PROMPTS}")
        return 1
    upstream = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(upstream)
    local = load_prompts()
    bad = 0
    for name in PROMPT_ATTRS:
        a, b = getattr(upstream, name, None), getattr(local, name, None)
        same = a == b
        bad += 0 if same else 1
        print(f"{'SAME' if same else 'DIFF'}  {name}")
    print(f"\n{'快照与上游逐字一致' if bad == 0 else f'{bad} 处不一致'}")
    return bad


def format_steps(traj: Dict[str, Any], max_steps: int = 30,
                 include_observations: bool = False, obs_chars: int = 1200) -> str:
    """Mirror the repo's format_steps (action + reasoning only).

    The repo's ReasoningQualityScorer never sends the page observations to the
    judge, so "observation reading" is scored from the reasoning text alone.
    `include_observations` is an ablation that fixes that.
    """
    out = []
    for i, a in enumerate(traj.get("actions", [])[:max_steps]):
        out.append(f"\n--- Step {i + 1} ---")
        if a.get("action"):
            out.append(f"Action: {a['action']}")
        if a.get("reasoning"):
            out.append(f"Reasoning: {a['reasoning'][:1500]}")
        if include_observations and a.get("observation"):
            out.append(f"Observation (truncated):\n{a['observation'][:obs_chars]}")
    return "\n".join(out) or "No steps recorded."


def parse_json_block(text: str) -> Dict[str, Any]:
    m = re.search(r"```json\s*(.*?)\s*```", text, re.S)
    raw = m.group(1) if m else text
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    return json.loads(raw)


def judge_reasoning(prompts, traj, judge_key, mock=False, include_observations=False) -> Dict[str, Any]:
    if mock:
        n = len(traj.get("actions", []))
        base = max(1, min(4, 5 - n // 3))
        return {
            "backtrack_and_explore": {"score": base, "justification": "mock"},
            "task_decomposition": {"score": base, "justification": "mock"},
            "observation_reading": {"score": base, "justification": "mock"},
            "self_verification": {"score": base, "justification": "mock"},
        }
    prompt = [
        {"role": "system", "content": prompts.REASONING_QUALITY_SYSTEM_PROMPT},
        {"role": "user", "content": prompts.REASONING_QUALITY_USER_PROMPT.format(
            objective=traj.get("objective", ""),
            steps=format_steps(traj, include_observations=include_observations))},
    ]
    text = "\n\n".join(f"#{m['role']}\n{m['content']}" for m in prompt)
    resp = chat(text, api_key=judge_key, user="agentdiagnose-judge")
    return parse_json_block(answer_text(resp))


def judge_objective(prompts, traj, judge_key, mock=False) -> Dict[str, Any]:
    if mock:
        return {"score": 2, "justification": "mock"}
    prompt = [
        {"role": "system", "content": prompts.OBJECTIVE_QUALITY_SYSTEM_PROMPT},
        {"role": "user", "content": prompts.OBJECTIVE_QUALITY_USER_PROMPT.format(
            objective=traj.get("objective", ""))},
    ]
    text = "\n\n".join(f"#{m['role']}\n{m['content']}" for m in prompt)
    resp = chat(text, api_key=judge_key, user="agentdiagnose-judge")
    return parse_json_block(answer_text(resp))


def normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Mirror ReasoningQualityScorer.parse_response: /4, N/A drops the dimension.

    同时记录"这条分数是由哪几个维度算出来的"（issue #5）：N/A 不进均值本身没问题，
    问题是**分母变了却不留痕**，导致同一批里不同轨迹的总分不可横比。
    """
    subs = {}
    for dim in DIMENSIONS:
        item = raw.get(dim) or {}
        score = item.get("score")
        if dim == "backtrack_and_explore" and str(score).strip().upper() in ("N/A", "NA", "NONE"):
            subs[dim] = None
        else:
            try:
                subs[dim] = float(score) / 4.0
            except (TypeError, ValueError):
                subs[dim] = None
    used = {d: v for d, v in subs.items() if v is not None}
    overall = sum(used.values()) / len(used) if used else None
    return {"dimensions": subs, "overall": overall,
            "dimensions_used": list(used),
            "n_dims_used": len(used),
            "justifications": {d: (raw.get(d) or {}).get("justification", "") for d in DIMENSIONS}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(paths.TRAJECTORIES))
    ap.add_argument("--out", default="",
                    help="默认写到 input 的同级目录：<run>/scores.json（issue #3：按 run 隔离）")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--include-observations", action="store_true",
                    help="ablation: also give the judge the page accessibility trees")
    ap.add_argument("--run-id", default="",
                    help="this batch's id; defaults to the output directory's name")
    ap.add_argument("--check-prompts", action="store_true",
                    help="只把 rubric 快照与 ../AgentDiagnose-main 逐字比对，然后退出")
    args = ap.parse_args()

    if args.check_prompts:
        raise SystemExit(compare_with_upstream())

    if not args.out:
        args.out = str(Path(args.input).parent / "scores.json")

    prompts = load_prompts()

    # rubric 的版本指纹。只对模板，不对某条轨迹，所以整批一致。
    prompt_sha = provenance.prompt_fingerprint(
        prompts.REASONING_QUALITY_SYSTEM_PROMPT,
        prompts.REASONING_QUALITY_USER_PROMPT,
        prompts.OBJECTIVE_QUALITY_SYSTEM_PROMPT,
        prompts.OBJECTIVE_QUALITY_USER_PROMPT,
    )
    run_id = args.run_id or Path(args.out).parent.name
    judge_model = "mock:deterministic" if args.mock else provenance.judge_label(config.base_url())

    judge_key = None if args.mock else config.judge_key()
    if not args.mock and not judge_key:
        raise SystemExit("no judge key: set DIFY_JUDGE_API_KEY (or dify-judge) in repro/.env")
    files = sorted(p for p in Path(args.input).glob("*.json")
                   if not p.name.endswith(".failed.json"))
    if args.limit:
        files = files[: args.limit]

    results: Dict[str, Any] = {}
    if Path(args.out).exists():
        existing = json.loads(Path(args.out).read_text(encoding="utf-8"))
        stale = [t for t, row in existing.items() if "traj_sha256" not in row]
        if stale:
            print(f"注意：{Path(args.out)} 里有 {len(stale)} 条旧口径记录（无来源指纹）。"
                  f"它们会被保留，但 correlate 会拒绝使用。建议挪走该文件重跑。")
        results = existing

    for path in files:
        traj = json.loads(path.read_text(encoding="utf-8"))
        tid = path.stem
        print(f"[{tid}] scoring ...", flush=True)
        try:
            rq = judge_reasoning(prompts, traj, judge_key, args.mock,
                                 include_observations=args.include_observations)
            oq = judge_objective(prompts, traj, judge_key, args.mock)
        except DifyError as exc:
            print(f"    judge failed: {exc}")
            continue
        except Exception as exc:
            print(f"    parse failed: {exc}")
            continue

        rq_norm = normalize(rq)
        try:
            oq_score = float(oq.get("score")) / 4.0
        except (TypeError, ValueError):
            oq_score = None
        results[tid] = {
            "objective": traj.get("objective", ""),
            "reasoning_quality": rq_norm,
            "objective_quality": {"score": oq_score, "justification": oq.get("justification", "")},
            "success": traj.get("meta", {}).get("success"),
            "n_steps": traj.get("meta", {}).get("n_steps"),
            "raw_reasoning": rq,
            # ---- provenance（issue #1）：这条分数绑定到哪条轨迹、哪版 rubric、谁、何时 ----
            "traj_sha256": provenance.fingerprint(traj),
            "run_id": run_id,
            "judge_model": judge_model,
            "prompt_sha256": prompt_sha,
            "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"    reasoning={rq_norm['overall']:.3f} objective={oq_score}", flush=True)

    print(f"\nwrote {args.out} ({len(results)} trajectories)")


if __name__ == "__main__":
    main()

