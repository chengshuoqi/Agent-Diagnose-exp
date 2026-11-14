# 基线产物的 provenance 取证

> 取证时间：2026-11-14T17:58:35+08:00　取证脚本：`repro/code/snapshot_evidence.py`（只读 `output/`）
> 本文件的价值在于：即使 `output/` 被删除，这里的对照表与哈希仍然成立。

## 1. 结论

`output/scores.json`（mtime 2026-11-11T15:30:37+08:00）与 `output/trajectories/*.json`（mtime 2026-11-14T16:22:04+08:00 ~ 2026-11-14T16:23:02+08:00）**不是同一次运行的产物**。逐条比对 `n_steps` / `success`，8/10 条不一致。

`correlate.py:148-155` 的拼接键是**文件名**（= `task_id`），而 `task_id` 在每次重跑中保持不变、文件内容每次都变。于是 `output/correlation.md` 把「上一次运行轨迹的人工分」和「这一次运行轨迹的机器分」拼在一起算相关性——**该数值不对应任何真实量**。

## 2. 时间线

| 产物 | 最后写入 |
|---|---|
| `output/scores.json` | 2026-11-11T15:30:37+08:00 |
| `output/annotations.csv` | 2026-11-14T16:11:51+08:00 |
| `output/trajectories/*.json` | 2026-11-14T16:22:04+08:00 ~ 2026-11-14T16:23:02+08:00 |

## 3. 逐条对照

| task_id | 分数表 (steps, success) | 轨迹 (steps, success) | 判定 | 轨迹字节 | traj sha256[:12] |
|---|---|---|---|---|---|
| `t01_backpack_first_price` | (2, True) | (1, False) | **漂移** | 7787 | `949100dedb0a` |
| `t02_add_home_product` | (2, True) | (0, False) | **漂移** | 630 | `880c71d26e2d` |
| `t03_cheapest_backpack` | (2, True) | (1, False) | **漂移** | 8130 | `9278ed7f674e` |
| `t04_coffee_under_20` | (8, False) | (0, False) | **漂移** | 625 | `bd54dbb5f1f5` |
| `t05_no_results` | (2, True) | (2, True) | 一致 | 10925 | `d7cdce36764a` |
| `t06_product_page_price` | (3, True) | (2, False) | **漂移** | 17371 | `95437d1dc8f9` |
| `t07_cart_status` | (2, True) | (0, False) | **漂移** | 612 | `a9e3d6a302ee` |
| `t08_most_expensive_backpack` | (2, True) | (2, True) | 一致 | 17371 | `215fa9bd812c` |
| `t09_vague_kitchen` | (4, None) | (2, None) | **漂移** | 17443 | `7b649f061baa` |
| `t10_vague_gift` | (8, None) | (1, None) | **漂移** | 8677 | `dcc4bbbf51cc` |

漂移 8/10 条。

## 4. 三个根因（对应 issue）

1. **拼接键是文件名**：`task_id` 稳定、内容不稳定，`correlate.py` 无法察觉错配。
2. **分数行没有来源信息**：`scores.json` 里没有轨迹哈希、没有 `run_id`、没有模型名、没有评分时间（`score_trajectories.py:174-181`）。
3. **输出目录没有运行隔离**：所有批次写同一组 `output/*.json`，后一次覆盖前一次（`run_episodes.py:192-196` 的守卫只在 `n_steps == 0 且 error` 时生效）。

## 5. 标注侧的样本量事实

| 维度 | 已填 | 其中 N/A | 可用于计算的 n |
|---|---|---|---|
| `backtrack_and_explore` | 10/10 | 9 | 1 |
| `task_decomposition` | 10/10 | 0 | 10 |
| `observation_reading` | 10/10 | 0 | 10 |
| `self_verification` | 10/10 | 0 | 10 |
| `objective_quality` | 10/10 | 0 | 10 |

`backtrack_and_explore` 的可用样本为 **n=1**，因此 `output/correlation.md` 该行打印 `-`。这不是算错了，是没有数据。

## 6. 复现本表的方法

```powershell
cd repro
.\\.venv\\Scripts\\python.exe code\\snapshot_evidence.py
```

哈希口径：轨迹 JSON 的 **canonical 形式**（`sort_keys=True`、无多余空白、UTF-8）的 sha256。选 canonical 而非原始字节，是为了让「仅格式变化」不产生误报。

