# AgentDiagnose 复现实验（WebArena shopping + Dify）

本仓库是对论文 **AgentDiagnose: An Open Toolkit for Diagnosing LLM Agent Trajectories**（EMNLP 2025 Demo）
**实验一**的第三方复现：用 LLM 按论文的五维 rubric 给 agent 轨迹打分，再与标注分数做相关性对比（对应论文 Table 1）。

- 非官方实现；上游项目：<https://github.com/oootttyyy/AgentDiagnose>
- 依赖本地 **WebArena shopping 容器**与 **Dify 应用密钥**，二者均不随仓库分发
- 实验产出（`output/`）不入库，按下方流程在本地生成

> **现状与改造计划**见 [`docs/施工地图.md`](docs/施工地图.md)（阶段、验收命令、不做清单）。
> 产物来源的一致性取证见 [`docs/evidence/baseline-drift.md`](docs/evidence/baseline-drift.md)：现有 `output/` 中
> 分数表与轨迹来自不同批次，8/10 条对不上，`correlation.md` 的数值因此不成立。

---

## 1. 目录结构

```
<repo>/
├── code/                     # 全部可执行代码
│   ├── paths.py              #   所有路径的唯一来源
│   ├── config.py             #   读 .env 里的 Dify 密钥
│   ├── dify_client.py        #   Dify API 客户端（标准库实现）
│   ├── browser_tools.py      #   浏览器层：无障碍树观测 + 动作执行
│   ├── policies.py           #   策略层：Dify 策略 / 离线基线
│   ├── run_episodes.py       #   ① 采集轨迹
│   ├── score_trajectories.py #   ② 自动打分
│   ├── make_annotation_sheet.py  # ③ 生成标注表
│   ├── correlate.py          #   ④ 算相关性
│   ├── run_all.cmd / .ps1    #   一键串起 ①→④
│   └── requirements.txt      #   Python 依赖（只有 playwright）
├── data/
│   └── tasks_shopping.json   # 实验输入：10 条任务定义
├── docs/
│   ├── 打分指南.md            # 标注人必读：五维定义、1–4 锚点、示例、误判
│   └── 标注说明.md            # 标注数据来源与重标方法
├── output/                   # 实验产物（不入库，运行后生成）
└── README.md
```

所有路径都从 `code/paths.py` 推导，仓库可整体复制/移动，不需要改代码。

---

## 2. 前置条件

### 2.1 上游 AgentDiagnose 仓库

第 ② 步要用论文仓库里的原始 rubric prompt，本项目**不内置**上游代码，需把它克隆到**本项目的同级目录**，且目录名必须是 `AgentDiagnose-main`：

```powershell
cd ..
git clone https://github.com/oootttyyy/AgentDiagnose.git AgentDiagnose-main
```

（`code/paths.py` 会去 `<本项目父目录>/AgentDiagnose-main/evaluator/scorers/prompts/prompt.py` 读取 prompt；找不到时 `score_trajectories.py` 会直接给出提示。）

### 2.2 WebArena shopping 容器

```powershell
docker start webarena-verified-shopping
curl.exe -s -o NUL -w "%{http_code}" http://localhost:7770/    # 期望 200
curl.exe -s http://localhost:7771/status                        # 期望 "success": true
```

### 2.3 Dify 应用与密钥

需要两个 Dify **Agent 应用**（一个当被测 agent，一个当 judge）。在项目根目录建 `.env`（已被 `.gitignore` 排除）：

```ini
'dify-web'=app-xxxxxxxx
'dify-judge'=app-yyyyyyyy
```

`code/config.py` 会自动找到它，搜索顺序：**项目父目录 → 项目根 → `code/` → 当前目录**，并兼容 `DIFY_API_KEY` 等写法。

### 2.4 Python 环境

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r code\requirements.txt
```

依赖只有 `playwright`（复用系统 Chrome，不需要下载 Chromium）。

---

## 3. 实验流程

```powershell
# ① 采集轨迹 —— Dify agent 跑 10 条任务 → output/trajectories/*.json
.\.venv\Scripts\python.exe code\run_episodes.py --policy dify --headed --verbose

# ② 自动打分 —— 用论文 rubric 调 judge → output/scores.json
.\.venv\Scripts\python.exe code\score_trajectories.py

# ③ 生成标注表 —— output/annotations.csv（填分）+ output/annotations.md（读轨迹）
.\.venv\Scripts\python.exe code\make_annotation_sheet.py

# ④ 算相关性 —— output/correlation.md
.\.venv\Scripts\python.exe code\correlate.py
```

一键跑完（第 ③ 步的分数仍需人工填）：

```powershell
.\code\run_all.cmd
```

### 各步产物

| 步骤 | 产物 | 说明 |
|---|---|---|
| ① | `output/trajectories/<task_id>.json` × 10 | 每条轨迹的观测/动作/推理 |
| ② | `output/scores.json` | 五维分数 + judge 理由 |
| ③ | `output/annotations.csv` / `annotations.md` | CSV 填分；MD 供人阅读 |
| ④ | `output/correlation.md` | 每维 r / ρ / τ + pooled + 样本量 |

> 标注口径见 [`docs/打分指南.md`](docs/打分指南.md)：五维定义、1–4 分锚点、N/A 规则、两个完整示例与常见误判。

---

## 4. 输出格式

### `output/trajectories/<task_id>.json`

```json
{
  "objective": "任务目标",
  "actions": [
    {
      "nth_step": 1,
      "action": "submit(8, \"backpack\")",
      "reasoning": "模型给出的理由",
      "observation": "决策前看到的无障碍树（带 [id]）",
      "url": "http://localhost:7770/",
      "result": "ok"
    }
  ],
  "task_website": "localhost:7770",
  "reward": 1,
  "meta": { "task_id": "t01_backpack_first_price", "policy": "dify", "success": true,
            "final_url": "...", "n_steps": 2, "answers": ["..."], "elapsed_s": 7.4 }
}
```

与上游 `evaluator/trajectory.py` 的 `Trajectory.from_json` 字段一一对应。

### `output/scores.json`

```json
{
  "t01_backpack_first_price": {
    "reasoning_quality": {
      "dimensions": { "backtrack_and_explore": null, "task_decomposition": 0.75,
                      "observation_reading": 0.5, "self_verification": 0.5 },
      "overall": 0.583,
      "justifications": { "维度": "judge 理由" }
    },
    "objective_quality": { "score": 1.0, "justification": "..." },
    "success": true, "n_steps": 2
  }
}
```

### `output/annotations.csv`

列：`task_id, objective, success, n_steps, trace, rubric` + 五列分数。
`backtrack_and_explore` 可填 `N/A` 或留空；其余填 1–4 整数。

---

## 5. 参数速查

**`code\run_episodes.py`**

| 参数 | 说明 |
|---|---|
| `--policy dify\|scripted` | 真实 Dify，或离线冒烟基线 |
| `--only t01_x,t02_y` | 只跑指定任务 |
| `--limit N` | 只跑前 N 条 |
| `--out 目录` | 轨迹输出目录（默认 `output/trajectories`） |
| `--tasks 文件` | 任务定义（默认 `data/tasks_shopping.json`） |
| `--headed` / `--verbose` | 显示浏览器 / 打印每步与原始回复 |
| `--max-obs-lines 200` | 观测最大行数（太大易被 Dify 截断） |
| `--screenshots` | 保存结束截图 |

> `--max-steps` 基本无效：每个任务在 `data/tasks_shopping.json` 里已写死上限。

**`code\score_trajectories.py`**：`--input` / `--out` / `--limit` / `--mock` / `--include-observations`
**`code\make_annotation_sheet.py`**：`--input` / `--out` / `--md` / `--reasoning-chars` / `--obs-chars`
**`code\correlate.py`**：`--scores` / `--annotations` / `--out` / `--self-test`

---

## 6. 注意事项

1. **每次运行轨迹都不同**：LLM 采样、页面时序、网络都会影响结果；`task_id` 稳定但内容不稳定。跑完 ① 后再重跑会覆盖同名文件，导致 `scores.json` / `annotations.csv` 与新轨迹对不上。建议用 `--out output/runs/<日期>` 做版本隔离。
2. **judge 有抖动**：同一轨迹重跑分数可能差 0.2 以上；写报告建议每条判 2–3 次取均值。
3. **任务偏简单**：多数"一次走对"，`backtrack_and_explore` 常为 N/A；要让该维度有数据，需补"会走弯路"的任务。
4. **元素 id 是页内编号**：跨页后同一 id 指向别的元素，日志里会看到 `error: element N is not a text field`。属于环境特性。
5. **Playwright `EPERM mkdtemp`**：已自动处理，启动前把 `TEMP/TMP` 指向 `.tmp/`。
6. **Agent 应用只支持流式**：客户端自动从 blocking 回退 SSE，并对 `message` / `agent_message` 去重。
7. **CSV 编码**：用 Excel/WPS 改 `annotations.csv` 请存成「CSV UTF-8」，否则 `correlate.py` 会报编码错误。

---

## 7. 重跑检查清单

- [ ] 上游仓库已克隆到 `../AgentDiagnose-main`
- [ ] `docker ps` 里 `webarena-verified-shopping` 是 Up，`http://localhost:7770/` 返回 200
- [ ] `code\config.py` 显示两个 key 都是 `set`
- [ ] ① 跑完 `output/trajectories/` 有 10 个 json，8 条 `success=true`（2 条含糊任务为 `null`）
- [ ] ② 跑完 `output/scores.json` 有 10 条，无 `error` 字段
- [ ] ③ 对照 `docs/打分指南.md` 打分
- [ ] ④ `output/correlation.md` 的 `n` 与标注条数一致
