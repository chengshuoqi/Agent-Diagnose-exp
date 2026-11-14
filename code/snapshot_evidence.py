# -*- coding: utf-8 -*-
"""把 output/ 里现存产物的 provenance 事实固化成可引用的文档。

只读 output/，只写 docs/evidence/。不修改任何实验产物。
"""
import csv
import glob
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

OUT = Path("output")
EV = Path("docs/evidence")


def canon(obj) -> bytes:
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def mtime(p) -> str:
    return datetime.fromtimestamp(os.path.getmtime(p)).astimezone().isoformat(timespec="seconds")


scores_path = OUT / "scores.json"
scores = json.loads(scores_path.read_text(encoding="utf-8"))
trajs = sorted(glob.glob(str(OUT / "trajectories" / "*.json")))

rows = []
for p in trajs:
    raw = Path(p).read_bytes()
    t = json.loads(raw.decode("utf-8"))
    tid = Path(p).stem
    meta = t.get("meta", {})
    n_meta = meta.get("n_steps")
    n_actions = len(t.get("actions", []))
    n_traj = n_meta if n_meta is not None else n_actions
    sc = scores.get(tid, {})
    s_steps = sc.get("n_steps")
    s_succ = sc.get("success")
    t_succ = meta.get("success")
    rows.append(
        {
            "task_id": tid,
            "scores_n_steps": s_steps,
            "traj_n_steps": n_traj,
            "traj_meta_n_steps": n_meta,
            "traj_n_actions": n_actions,
            "scores_success": s_succ,
            "traj_success": t_succ,
            "reward": t.get("reward"),
            "match": (s_steps == n_traj and s_succ == t_succ),
            "traj_sha256": sha(canon(t)),
            "traj_sha256_raw_bytes": sha(raw),
            "traj_mtime": mtime(p),
            "traj_bytes": len(raw),
        }
    )

drift = [r for r in rows if not r["match"]]

ann_path = OUT / "annotations.csv"
ann_rows = list(csv.DictReader(ann_path.open(encoding="utf-8-sig")))
dims = [k for k in ann_rows[0] if k not in ("task_id", "objective", "success", "n_steps", "trace", "rubric")]
ann_stats = {}
for d in dims:
    vals = [(r.get(d) or "").strip() for r in ann_rows]
    ann_stats[d] = {
        "filled": sum(1 for v in vals if v),
        "na": sum(1 for v in vals if v.upper() == "N/A"),
        "numeric": sum(1 for v in vals if v and v.upper() != "N/A"),
    }

payload = {
    "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    "scores_json": {
        "path": str(scores_path),
        "mtime": mtime(scores_path),
        "sha256": sha(scores_path.read_bytes()),
        "keys": len(scores),
    },
    "trajectories": {
        "count": len(trajs),
        "mtime_min": min(r["traj_mtime"] for r in rows),
        "mtime_max": max(r["traj_mtime"] for r in rows),
        "hashes": {r["task_id"]: r["traj_sha256"] for r in rows},
    },
    "annotations": {
        "mtime": mtime(ann_path),
        "sha256": sha(ann_path.read_bytes()),
        "rows": len(ann_rows),
        "dims": ann_stats,
    },
    "drift": drift,
    "rows": rows,
}

EV.mkdir(parents=True, exist_ok=True)
(EV / "baseline-drift.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
)

lines = []
w = lines.append
w("# 基线产物的 provenance 取证")
w("")
w(f"> 取证时间：{payload['captured_at']}　取证脚本：`repro/code/snapshot_evidence.py`（只读 `output/`）")
w("> 本文件的价值在于：即使 `output/` 被删除，这里的对照表与哈希仍然成立。")
w("")
w("## 1. 结论")
w("")
w(f"`output/scores.json`（mtime {payload['scores_json']['mtime']}）与 `output/trajectories/*.json`"
  f"（mtime {payload['trajectories']['mtime_min']} ~ {payload['trajectories']['mtime_max']}）**不是同一次运行的产物**。"
  f"逐条比对 `n_steps` / `success`，{len(drift)}/{len(rows)} 条不一致。")
w("")
w("`correlate.py:148-155` 的拼接键是**文件名**（= `task_id`），而 `task_id` 在每次重跑中保持不变、"
  "文件内容每次都变。于是 `output/correlation.md` 把「上一次运行轨迹的人工分」和"
  "「这一次运行轨迹的机器分」拼在一起算相关性——**该数值不对应任何真实量**。")
w("")
w("## 2. 时间线")
w("")
w("| 产物 | 最后写入 |")
w("|---|---|")
w(f"| `output/scores.json` | {payload['scores_json']['mtime']} |")
w(f"| `output/annotations.csv` | {payload['annotations']['mtime']} |")
w(f"| `output/trajectories/*.json` | {payload['trajectories']['mtime_min']} ~ {payload['trajectories']['mtime_max']} |")
w("")
w("## 3. 逐条对照")
w("")
w("| task_id | 分数表 (steps, success) | 轨迹 (steps, success) | 判定 | 轨迹字节 | traj sha256[:12] |")
w("|---|---|---|---|---|---|")
for r in rows:
    a = f"({r['scores_n_steps']}, {r['scores_success']})"
    b = f"({r['traj_n_steps']}, {r['traj_success']})"
    verdict = "一致" if r["match"] else "**漂移**"
    w(f"| `{r['task_id']}` | {a} | {b} | {verdict} | {r['traj_bytes']} | `{r['traj_sha256'][:12]}` |")
w("")
w(f"漂移 {len(drift)}/{len(rows)} 条。")
w("")
w("## 4. 三个根因（对应 issue）")
w("")
w("1. **拼接键是文件名**：`task_id` 稳定、内容不稳定，`correlate.py` 无法察觉错配。")
w("2. **分数行没有来源信息**：`scores.json` 里没有轨迹哈希、没有 `run_id`、没有模型名、没有评分时间（`score_trajectories.py:174-181`）。")
w("3. **输出目录没有运行隔离**：所有批次写同一组 `output/*.json`，后一次覆盖前一次（`run_episodes.py:192-196` 的守卫只在 `n_steps == 0 且 error` 时生效）。")
w("")
w("## 5. 标注侧的样本量事实")
w("")
w("| 维度 | 已填 | 其中 N/A | 可用于计算的 n |")
w("|---|---|---|---|")
for d, s in ann_stats.items():
    w(f"| `{d}` | {s['filled']}/{len(ann_rows)} | {s['na']} | {s['numeric']} |")
w("")
w(f"`backtrack_and_explore` 的可用样本为 **n={ann_stats['backtrack_and_explore']['numeric']}**，"
  "因此 `output/correlation.md` 该行打印 `-`。这不是算错了，是没有数据。")
w("")
w("## 6. 复现本表的方法")
w("")
w("```powershell")
w("cd repro")
w(".\\\\.venv\\\\Scripts\\\\python.exe code\\\\snapshot_evidence.py")
w("```")
w("")
w("哈希口径：轨迹 JSON 的 **canonical 形式**（`sort_keys=True`、无多余空白、UTF-8）的 sha256。"
  "选 canonical 而非原始字节，是为了让「仅格式变化」不产生误报。")
w("")

(EV / "baseline-drift.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

print(f"drift {len(drift)}/{len(rows)}")
print(f"wrote {EV/'baseline-drift.md'}")
print(f"wrote {EV/'baseline-drift.json'}")
