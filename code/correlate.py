"""Compare automatic AgentDiagnose scores with human annotations (Table 1 reproduction).

    python correlate.py --scores scores.json --annotations annotations.csv

annotations.csv needs a header:
    task_id,backtrack_and_explore,task_decomposition,observation_reading,self_verification,objective_quality
values are 1-4, or N/A / empty when the dimension does not apply.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DIMS = ["backtrack_and_explore", "task_decomposition", "observation_reading",
        "self_verification", "objective_quality"]

import paths
import provenance


def pearson(x: List[float], y: List[float]) -> Optional[float]:
    n = len(x)
    if n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def rank(values: List[float]) -> List[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(x: List[float], y: List[float]) -> Optional[float]:
    return pearson(rank(x), rank(y))


def kendall_tau_b(x: List[float], y: List[float]) -> Optional[float]:
    n = len(x)
    if n < 3:
        return None
    conc = disc = tx = ty = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = x[i] - x[j]
            dy = y[i] - y[j]
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                tx += 1
            elif dy == 0:
                ty += 1
            elif dx * dy > 0:
                conc += 1
            else:
                disc += 1
    denom = math.sqrt((conc + disc + tx) * (conc + disc + ty))
    return (conc - disc) / denom if denom else None


def to_float(value: str) -> Optional[float]:
    value = (value or "").strip()
    if not value or value.upper() in ("N/A", "NA", "NONE"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def self_test() -> int:
    """Check the three statistics against hand-computed cases.

    This is what the 'dummy data' run was really for: make sure the maths and
    the CSV plumbing are correct *before* any real annotation exists.
    """
    failures = 0

    def close(a: Optional[float], b: float, tol: float = 1e-9) -> bool:
        return a is not None and abs(a - b) < tol

    cases = [
        # x, y, expected pearson, spearman, kendall tau-b
        ([1, 2, 3, 4], [1, 2, 3, 4], 1.0, 1.0, 1.0),
        ([1, 2, 3, 4], [4, 3, 2, 1], -1.0, -1.0, -1.0),
        ([1, 2, 3, 4], [1, 1, 2, 2], None, None, None),  # checked below by hand
        ([1, 2, 2, 3], [1, 2, 3, 4], None, None, None),
    ]
    # hand-computed references for the two tie cases (exact forms below)
    tie_expect = [
        # x=[1,2,3,4], y=[1,1,2,2]: r=2/sqrt(5), rho=4/sqrt(20), tau=4/sqrt(24)
        (2 / math.sqrt(5), 4 / math.sqrt(20), 4 / math.sqrt(24)),
        # x=[1,2,2,3], y=[1,2,3,4]: r=3/sqrt(10), rho=4.5/sqrt(22.5), tau=5/sqrt(30)
        (3 / math.sqrt(10), 4.5 / math.sqrt(22.5), 5 / math.sqrt(30)),
    ]

    for i, (x, y, r, rho, tau) in enumerate(cases):
        got = (pearson(x, y), spearman(x, y), kendall_tau_b(x, y))
        if i < 2:
            want = (r, rho, tau)
        else:
            want = tie_expect[i - 2]
        ok = all(close(g, w, 1e-9) for g, w in zip(got, want))
        failures += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'}  x={x} y={y} -> "
              f"r={got[0]!r} rho={got[1]!r} tau={got[2]!r}")

    # N/A handling
    parsed = [to_float(v) for v in ["4", "N/A", "", " 2 ", "3.0"]]
    ok = parsed == [4.0, None, None, 2.0, 3.0]
    failures += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  to_float -> {parsed}")

    print("\nself-test:", "all passed" if failures == 0 else f"{failures} failure(s)")
    return failures


def read_rows(path: Path) -> List[Dict[str, str]]:
    """读标注表，容忍 Excel/WPS 把它存成 GBK。

    这不是理论风险：2026-11-14 就因为另存成 GBK，`correlate` 直接抛 UnicodeDecodeError
    （见 issue #6 的评论）。顺序 utf-8-sig → gbk → utf-8，全失败时给人话提示。
    """
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        if enc != "utf-8-sig":
            print(f"注意：{path.name} 不是 UTF-8（按 {enc} 读取）。"
                  "用 Excel/WPS 另存为「CSV UTF-8」可避免下次再遇到。")
        return list(csv.DictReader(io.StringIO(text)))
    raise SystemExit(
        f"无法解码标注表：{path}\n"
        "请用 Excel/WPS 打开后另存为「CSV UTF-8」，或用文本编辑器转成 UTF-8。"
    )


def resolve_trajectories(explicit: str, scores_path: str) -> Path:
    """去哪找轨迹：显式参数 > scores 同级的 trajectories/ > paths.TRAJECTORIES。

    打印最终选择，避免"猜到了错目录"这种沉默失败。
    """
    if explicit:
        return Path(explicit)
    sibling = Path(scores_path).parent / "trajectories"
    if sibling.is_dir():
        return sibling
    return Path(paths.TRAJECTORIES)


def verify_provenance(scores, human, sheet_meta, disk):
    """逐条比对"分数说的是哪条轨迹"与"标注表生成时看到的是哪条轨迹"。

    返回 [(task_id, 检查项, 一侧, 另一侧)]；空列表表示全部通过。
    只读不写，也不做任何自动修复——修复需要猜哪边是对的，机器不知道。
    """
    problems = []
    for tid in human:
        if tid not in scores:
            continue
        row = scores[tid]
        fp = row.get("traj_sha256")

        if not fp:
            problems.append((tid, "分数行无来源指纹", "缺少 traj_sha256", "需重新判分"))
            continue
        if tid not in disk:
            problems.append((tid, "磁盘上找不到该轨迹", fp[:12], "缺失"))
            continue
        if fp != disk[tid]["sha256"]:
            problems.append((tid, "分数绑定的是另一条轨迹", fp[:12], disk[tid]["sha256"][:12]))
            continue

        # 标注侧：生成打分表时写下的 n_steps / success，必须与磁盘上的轨迹一致。
        seen_steps = sheet_meta.get(tid, {}).get("n_steps")
        if seen_steps is not None and seen_steps != disk[tid]["n_steps"]:
            problems.append((tid, "标注表对应的是另一条轨迹",
                             f"n_steps={seen_steps}", f"n_steps={disk[tid]['n_steps']}"))
        seen_success = sheet_meta.get(tid, {}).get("success")
        if seen_success != disk[tid]["success"]:
            problems.append((tid, "标注表 success 与轨迹不一致",
                             f"success={seen_success}", f"success={disk[tid]['success']}"))
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default=str(paths.SCORES))
    ap.add_argument("--annotations", default="",
                    help="默认取 scores.json 同级的 annotations.csv（issue #3：按 run 隔离）")
    ap.add_argument("--out", default="",
                    help="默认写到 scores.json 同级的 correlation.md（issue #3：按 run 隔离）")
    ap.add_argument("--trajectories", default="",
                    help="轨迹目录；默认取 scores.json 同级的 trajectories/，再退回 output/trajectories")
    ap.add_argument("--force-join", action="store_true",
                    help="跳过来源校验强制出数（输出文件会被标记为不可用于结论）")
    ap.add_argument("--exclude-errors", action="store_true",
                    help="排除 meta.error 非空的轨迹（网络/环境截断的那种）")
    ap.add_argument("--self-test", action="store_true",
                    help="validate the statistics on hand-computed cases and exit")
    args = ap.parse_args()

    if args.self_test:
        raise SystemExit(self_test())

    if not args.out:
        args.out = str(Path(args.scores).parent / "correlation.md")
    if not args.annotations:
        args.annotations = str(Path(args.scores).parent / "annotations.csv")

    scores = json.loads(Path(args.scores).read_text(encoding="utf-8"))
    rows = read_rows(Path(args.annotations))

    human: Dict[str, Dict[str, Optional[float]]] = {}
    sheet_meta: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        tid = (row.get("task_id") or "").strip()
        if tid:
            human[tid] = {d: to_float(row.get(d, "")) for d in DIMS}
            raw_steps = (row.get("n_steps") or "").strip()
            sheet_meta[tid] = {
                "n_steps": int(raw_steps) if raw_steps.isdigit() else None,
                "success": provenance.normalize_success(row.get("success")),
            }

    traj_dir = resolve_trajectories(args.trajectories, args.scores)
    disk = provenance.scan_dir(traj_dir)
    print(f"provenance: 轨迹目录 {traj_dir}（{len(disk)} 条可读轨迹）")
    if not disk:
        print("  警告：该目录下没有可读的轨迹文件，无法校验来源")

    problems = verify_provenance(scores, human, sheet_meta, disk)
    if problems:
        label = "provenance 校验未通过（--force-join 已强制继续）" if args.force_join \
            else "provenance 校验未通过，拒绝计算相关性"
        print(f"\n{label}：")
        print(f"  {'task_id':34} {'检查项':26} {'一侧':>20}  vs  {'另一侧':>20}")
        for tid, why, mine, theirs in problems:
            print(f"  {tid:34} {why:26} {mine:>20}  vs  {theirs:>20}")
        print(f"\n共 {len(problems)} 处不一致。")
        if not args.force_join:
            print("未写输出文件。请重跑判分或重新生成标注表；"
                  "确认差异后可用 --force-join 强制出数（结果会被标记为不可用于结论）。")
            raise SystemExit(2)

    # 网络/环境导致的截断写在 meta.error 里；它们不是"能力差异"，
    # 混进相关性会把"agent 不会做"和"agent 没来得及做"算成同一件事。
    errored = sorted(tid for tid, info in disk.items() if info.get("error"))
    if errored:
        print(f"  注意：{len(errored)}/{len(disk)} 条轨迹带 error（环境或策略中断，不是能力差异）："
              f"{', '.join(errored[:6])}{' …' if len(errored) > 6 else ''}")
        if args.exclude_errors:
            for tid in errored:
                human.pop(tid, None)
                scores.pop(tid, None)
            print(f"  已按 --exclude-errors 排除，剩余 {len(human)} 条参与计算。")

    table: List[Tuple[str, Optional[float], Optional[float], Optional[float], int, int, str]] = []
    dim_rs: List[float] = []

    for dim in DIMS:
        xs, ys = [], []
        n_human = 0
        for tid, hs in human.items():
            if tid not in scores:
                continue
            h = hs.get(dim)
            if h is not None:
                n_human += 1
            auto = scores[tid]
            if dim == "objective_quality":
                a = auto.get("objective_quality", {}).get("score")
                a = a * 4 if a is not None else None
            else:
                a = auto.get("reasoning_quality", {}).get("dimensions", {}).get(dim)
                a = a * 4 if a is not None else None
            if a is None or h is None:
                continue
            xs.append(h)
            ys.append(a)

        r = pearson(xs, ys)
        note = ""
        if not xs:
            note = "无可用样本"
        elif len(xs) < 3:
            note = "样本不足"
        elif r is None:
            note = "某一侧无方差（算不出 r）"
        elif n_human > len(xs):
            note = f"{n_human - len(xs)} 条只有标注没有机器分"
        table.append((dim, r, spearman(xs, ys), kendall_tau_b(xs, ys), len(xs), n_human, note))
        if r is not None:
            dim_rs.append(r)

    # issue #5：不再把各维观测堆成一个大数组算 "pooled"。
    # 10 条轨迹 × 4 维 = 41 个观测并不独立，pooled 的 n 会虚高、区间会假窄。
    # 正确做法是报"各维 r 的均值"，并让人看得到每维的 n。
    overall_r = sum(dim_rs) / len(dim_rs) if dim_rs else None
    table.append(("overall（各维 r 的均值）", overall_r, None, None, sum(t[4] for t in table),
                  sum(t[5] for t in table), f"{len(dim_rs)} 个维度参与"))

    lines = ["| 维度 | Pearson r | Spearman rho | Kendall tau | n（配对） | n（标注） | 备注 |",
             "|---|---|---|---|---|---|---|"]
    for dim, r, rho, tau, n, n_h, note in table:
        fmt = lambda v: "-" if v is None else f"{v:.2f}"
        lines.append(f"| {dim} | {fmt(r)} | {fmt(rho)} | {fmt(tau)} | {n} | {n_h} | {note} |")

    md = "\n".join(lines)
    if problems:
        md = ("> **WARNING**：provenance 校验未通过（`--force-join`），"
              "本表数值不可用于结论。\n\n" + md)
    print(md)
    Path(args.out).write_text(md + "\n", encoding="utf-8")
    print(f"\nwrote {args.out}")

    n_auto = len(scores)
    n_human = len(human)
    both = set(scores) & set(human)
    print(f"trajectories: {n_auto} scored, {n_human} annotated, {len(both)} matched"
          f"（有分数未标注 {len(set(scores) - set(human))}，"
          f"已标注无分数 {len(set(human) - set(scores))}）")


if __name__ == "__main__":
    main()

