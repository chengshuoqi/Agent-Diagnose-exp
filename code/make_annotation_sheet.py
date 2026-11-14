"""Build the human annotation sheet for the correlation study.

Produces two files from the recorded trajectories:

    annotations.csv   -- one row per trajectory, five empty score columns
    annotations.md    -- the same content in a readable form (what annotators read)

    python make_annotation_sheet.py
    python make_annotation_sheet.py --input trajectories --out annotations.csv --md annotations.md

See 打分指南.md for the rubric and worked examples.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import paths

DIMS = ["backtrack_and_explore", "task_decomposition", "observation_reading",
        "self_verification", "objective_quality"]

DIM_CN = {
    "backtrack_and_explore": "回退与探索（可填 N/A）",
    "task_decomposition": "任务分解",
    "observation_reading": "观测阅读",
    "self_verification": "自我验证",
    "objective_quality": "目标质量（只看目标文本）",
}

RUBRIC = ("1–4 整数。4=优秀 3=良好 2=一般 1=差；backtrack 在“全程未走错、也无需回退”时填 N/A。"
          "objective_quality 只看任务目标，不看轨迹。")

NAV_NOISE = ("my account", "sign in", "skip to", "my cart", "my wish list", "create an account",
             "advanced search", "search terms", "copyright", "newsletter", "privacy",
             "report all bugs", "orders and returns", "contact us")


def excerpt(obs: str, limit: int = 3) -> str:
    """Pick the informative lines of an accessibility tree (prices, buttons, results)."""
    picked = []
    for raw in obs.splitlines():
        line = raw.strip()
        if len(line) < 6:
            continue
        low = line.lower()
        if any(noise in low for noise in NAV_NOISE):
            continue
        score = 0
        if "$" in line:
            score += 3
        if "add to cart" in low or "added" in low:
            score += 3
        if "no results" in low or "returned no" in low:
            score += 3
        if "required" in low or "error" in low or "out of stock" in low:
            score += 2
        if "in stock" in low:
            score += 1
        if re.search(r"link '.{30,}'", line):
            score += 2
        if "text '" in line:
            score += 1
        if score >= 2:
            picked.append((score, line))
    picked.sort(key=lambda pair: -pair[0])
    chosen = [line for _, line in picked[:limit]]
    # keep at least one element name so the annotator can tell what was on the page
    if chosen and not any("link '" in line for line in chosen):
        link_lines = [line for _, line in picked if "link '" in line]
        if link_lines:
            chosen = chosen[: max(1, limit - 1)] + [link_lines[0]]
    if not chosen:
        chosen = [l.strip() for l in obs.splitlines()[: limit + 1] if l.strip()]
    return " | ".join(chosen)


def render_steps(traj: dict, reasoning_chars: int, obs_chars: int) -> str:
    lines = []
    for i, a in enumerate(traj.get("actions", []), 1):
        action = (a.get("action") or "").strip()
        reasoning = (a.get("reasoning") or "").strip().replace("\n", " ")
        obs = (a.get("observation") or "").strip()
        lines.append(f"{i}. {action}")
        if reasoning:
            lines.append(f"   理由：{reasoning[:reasoning_chars]}")
        if obs and obs_chars > 0:
            lines.append(f"   页面：{excerpt(obs)[:obs_chars]}")
    return "\n".join(lines) or "(无动作)"


def write_markdown(trajs: list, path: Path, reasoning_chars: int, obs_chars: int) -> None:
    out = [
        "# 人工打分表",
        "",
        "> 评分口径见 `打分指南.md`。填完后把五列分数抄进 `annotations.csv`，再用 `correlate.py` 算相关性。",
        "",
        f"> {RUBRIC}",
        "",
        "---",
        "",
    ]
    for name, traj in trajs:
        meta = traj.get("meta", {})
        out.append(f"## {name}")
        out.append("")
        out.append(f"**目标**：{traj.get('objective', '')}")
        out.append("")
        out.append(f"**程序判定**：success={meta.get('success')}　**步数**：{meta.get('n_steps')}")
        out.append("")
        out.append("```")
        out.append(render_steps(traj, reasoning_chars, obs_chars))
        out.append("```")
        out.append("")
        out.append("| 维度 | 分数 | 依据（可选） |")
        out.append("|---|---|---|")
        for dim in DIMS:
            out.append(f"| {DIM_CN[dim]} |  |  |")
        out.append("")
        out.append("---")
        out.append("")
    path.write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(paths.TRAJECTORIES))
    ap.add_argument("--out", default=str(paths.ANNOTATIONS))
    ap.add_argument("--md", default=str(paths.ANNOTATIONS_MD))
    ap.add_argument("--reasoning-chars", type=int, default=500)
    ap.add_argument("--obs-chars", type=int, default=320, help="0 = 不显示页面观测")
    args = ap.parse_args()

    files = sorted(Path(args.input).glob("*.json"))
    if not files:
        raise SystemExit(f"no trajectories in {args.input}; run run_episodes.py first")

    trajs = []
    rows = []
    for path in files:
        traj = json.loads(path.read_text(encoding="utf-8"))
        trajs.append((path.stem, traj))
        rows.append({
            "task_id": path.stem,
            "objective": traj.get("objective", ""),
            "success": traj.get("meta", {}).get("success"),
            "n_steps": len(traj.get("actions", [])),
            "trace": render_steps(traj, args.reasoning_chars, args.obs_chars)[:8000],
            "rubric": RUBRIC,
            **{d: "" for d in DIMS},
        })

    fields = ["task_id", "objective", "success", "n_steps", "trace", "rubric"] + DIMS
    with Path(args.out).open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    write_markdown(trajs, Path(args.md), args.reasoning_chars, args.obs_chars)

    print(f"wrote {args.out} ({len(rows)} rows)")
    print(f"wrote {args.md} (readable version, hand this to annotators)")
    print(f"five columns to fill: {', '.join(DIMS)}")


if __name__ == "__main__":
    main()

