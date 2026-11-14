# AgentDiagnose 复现实验（WebArena shopping + Dify）

本仓库是对论文 **AgentDiagnose: An Open Toolkit for Diagnosing LLM Agent Trajectories**（EMNLP 2025 Demo）
**实验一**的第三方复现：用 LLM 按论文的五维 rubric 给 agent 轨迹打分，再与标注分数做相关性对比（对应论文 Table 1）。

- 非官方实现；上游项目：<https://github.com/oootttyyy/AgentDiagnose>
- 依赖本地 **WebArena shopping 容器**与 **Dify 应用密钥**，二者均不随仓库分发
- 实验产出（`output/runs/<run_id>/`）不入库，按下方流程在本地生成
- 每次运行的每条分数都带**轨迹指纹**；分数与轨迹对不上时 `correlate` 拒绝出数，而不是给一个数

> **实验报告**见 [`docs/实验报告.md`](docs/实验报告.md)；**验收记录**见 [`docs/验收记录.md`](docs/验收记录.md)。
> **现状与改造计划**见 [`docs/施工地图.md`](docs/施工地图.md)（阶段、验收命令、不做清单）。
> 产物来源的一致性取证见 [`docs/evidence/baseline-drift.md`](docs/evidence/baseline-drift.md)：第一轮产物中
> 分数表与轨迹来自不同批次，8/10 条对不上，当时 `correlation.md` 的数值因此不成立。

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
│   ├── provenance.py         #   来源指纹：canonical JSON 的 sha256（一处实现）
│   ├── prompts/              #   rubric 快照（不再依赖外部克隆，见 issue #4）
│   ├── snapshot_evidence.py  #   只读取证：产物漂移对照表
│   ├── run_episodes.py       #   ① 采集轨迹
│   ├── score_trajectories.py #   ② 自动打分
│   ├── make_annotation_sheet.py  # ③ 生成标注表
│   ├── correlate.py          #   ④ 算相关性（含来源校验，对不上即拒算）
│   ├── run_all.cmd / .ps1    #   一键串起 ①→③ 并停等人工标注
│   └── requirements.txt      #   Python 依赖（只有 playwright）
├── data/
│   ├── tasks_shopping.json   # 实验输入：10 条任务定义（A/B 两批共用）
│   └── tasks_backtrack.json  # 回退专项任务（#8）：ground truth 已核对，当前 agent 跑不通
├── docs/
│   ├── 施工地图.md            # 阶段、验收命令、不做清单
│   ├── evidence/             # 产物来源的取证（漂移对照表 + 哈希）
│   ├── 打分指南.md            # 标注人必读：五维定义、1–4 锚点、示例、误判
│   └── 标注说明.md            # 标注数据来源与重标方法
├── output/runs/<run_id>/     # 实验产物（不入库）：一次运行一个目录
└── README.md
```

所有路径都从 `code/paths.py` 推导，仓库可整体复制/移动，不需要改代码。

---

## 2. 前置条件

### 2.1 上游 AgentDiagnose 仓库（**可选**）

rubric prompt 已经**快照进本仓库**（`code/prompts/agentdiagnose_rubric.py`），运行时不依赖外部克隆。
只有在你想核对"快照与上游是否逐字一致"时才需要它：

```powershell
# 在 repro/ 的上一级（工作区根目录）执行
git clone https://github.com/oootttyyy/AgentDiagnose.git AgentDiagnose-main

# 回到 repro/，逐字比对快照与上游（只读，不改任何文件）
.\.venv\Scripts\python.exe code\score_trajectories.py --check-prompts
```

（`code/paths.py` 会去 `<本项目父目录>/AgentDiagnose-main/evaluator/scorers/prompts/prompt.py` 找上游；
找不到时 `--check-prompts` 会提示"跳过比对"，不影响正常判分。见 issue #4。）

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

每次运行落在**独立的批次目录** `output/runs/<run_id>/`（`run_id` 默认 `<时间戳>-<policy>`，可用 `--run-id` 指定）。
四个入口的 `--out` 默认都从输入目录推导（写到输入的同级目录），所以一个 `--run-id` 就能把整批产物圈在一起，
不会互相覆盖（issue #3）。

### 3.1 标准流程

```powershell
cd repro

# ① 采集轨迹 —— Dify agent 跑 10 条任务
.\.venv\Scripts\python.exe code\run_episodes.py --policy dify --run-id B-refactor --verbose

# ② 判分 —— 每条分数带上轨迹指纹（traj_sha256 等五个字段）
.\.venv\Scripts\python.exe code\score_trajectories.py --input output\runs\B-refactor\trajectories

# ③ 生成标注表（已填过的表默认拒绝覆盖）
.\.venv\Scripts\python.exe code\make_annotation_sheet.py --input output\runs\B-refactor\trajectories

# ④ 人工填分（另存为 CSV UTF-8）后，算相关性
.\.venv\Scripts\python.exe code\correlate.py --scores output\runs\B-refactor\scores.json
```

②③④ 的 `--out` 都省了：它们默认写到 `--input` / `--scores` 的同级目录。

### 3.2 跑一轮 B（含来源校验）——每一步的检查点

这是最常走的一条路，每一步都写了「怎么算过」。

**0. 前置**

```powershell
docker ps --filter "name=webarena-verified-shopping" --format "{{.Names}} {{.Status}}"
(Invoke-WebRequest http://localhost:7770/ -UseBasicParsing).StatusCode   # 期望 200
.\.venv\Scripts\python.exe code\config.py                                # 期望 agent/judge 都是 set
```

**1. 采集**

```powershell
.\.venv\Scripts\python.exe code\run_episodes.py --policy dify --run-id B-refactor --verbose
```

- 过：`output\runs\B-refactor\trajectories\` 有 10 个 json，且生成了 `run.json`。
- 不过：出现 `*.failed.json` 说明那条是 0 步崩溃。**先处理掉再进第 2 步**——判分会忽略它，但你的任务集就少一条。
- **必须再查一遍 `meta.error`**（2026-11-14 的 B 批次就栽在这里：5/10 条被 TLS 抖动截断，
  其中 3 条 0 步，相关性表面上 `r≈0.90`，实际上是被空轨迹抬起来的）：

```powershell
.\.venv\Scripts\python.exe -c "import json,glob; [print(p.split(chr(92))[-1][:-5], json.load(open(p,encoding='utf-8'))['meta']['error']) for p in glob.glob('output/runs/B-refactor/trajectories/*.json') if json.load(open(p,encoding='utf-8'))['meta'].get('error')]"
```

  有输出就**重跑那几条**（`--only t03_x,t05_y --overwrite`），别带着截断的轨迹往下走。客户端现在对流式请求
  有 3 次指数退避重试，单次抖动一般能救回来。

**2. 判分 + 验指纹**

```powershell
.\.venv\Scripts\python.exe code\score_trajectories.py --input output\runs\B-refactor\trajectories
.\.venv\Scripts\python.exe -c "import json; d=json.load(open('output/runs/B-refactor/scores.json',encoding='utf-8')); ks=('traj_sha256','run_id','judge_model','prompt_sha256','scored_at'); print('rows', len(d)); print('complete', all(k in v for v in d.values() for k in ks)); print('run_id', {v['run_id'] for v in d.values()}); print('prompt', {v['prompt_sha256'][:12] for v in d.values()})"
```

- 过：`rows 10` / `complete True` / `run_id {'B-refactor'}` / `prompt` 只有一个值。
- 不过：`complete False` 说明混进了旧口径记录，把 `scores.json` 挪走重跑。

**3. 生成标注表**

```powershell
.\.venv\Scripts\python.exe code\make_annotation_sheet.py --input output\runs\B-refactor\trajectories
```

- 过：`wrote ...annotations.csv (10 rows)`。
- 报「拒绝覆盖」：说明这张表已经填过——**那是保护，不是错误**。要重来就换 `--out`。

**4. 人工填分**

打开 `annotations.md` 读轨迹，在 `annotations.csv` 里填五列，**另存为「CSV UTF-8」**。存完验一下：

```powershell
.\.venv\Scripts\python.exe -c "import csv; r=list(csv.DictReader(open('output/runs/B-refactor/annotations.csv',encoding='utf-8-sig'))); print('rows', len(r)); print('filled', sum(1 for x in r for k in list(x)[6:] if (x[k] or '').strip()))"
```

- 过：`rows 10`，`filled` 在 45–50 之间（`backtrack` 的 N/A 不计）。

**5. 算相关性**

```powershell
.\.venv\Scripts\python.exe code\correlate.py --scores output\runs\B-refactor\scores.json
```

- 过：先打印 `provenance: 轨迹目录 …（10 条可读轨迹）`，然后出表，exit 0。
- 不过：打印「校验未通过」+ 差异表 + exit 2。**不要加 `--force-join`**——那说明标注与轨迹不是同一批。

### 3.3 一键脚本

```powershell
.\code\run_all.cmd -RunId B-refactor
```

采集 → 判分 → 生成标注表，然后**停下**：标注没填就不算相关性（不会产出「全空但 exit 0」的表）。
它也不会加 `--mock`——mock 分与真分不能混进同一份结果（issue #7）。

### 3.4 各步产物

| 步骤 | 产物（`<run>` = `output/runs/<run_id>`） | 说明 |
|---|---|---|
| ① | `<run>/trajectories/<task_id>.json` × 10、`<run>/run.json` | 轨迹 + 本次运行的清单 |
| ② | `<run>/scores.json` | 五维分数 + judge 理由 + 五个来源字段 |
| ③ | `<run>/annotations.csv` / `annotations.md` | CSV 填分；MD 供人阅读 |
| ④ | `<run>/correlation.md` | 每维 r / ρ / τ、`n（配对）`、`n（标注）`、备注 |

> 标注口径见 [`docs/打分指南.md`](docs/打分指南.md)：五维定义、1–4 分锚点、N/A 规则、两个完整示例与常见误判。

---

## 4. 输出格式

### `<run>/trajectories/<task_id>.json`

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
`reward` 是三态：`1` 成功 / `0` 失败 / `null` 不适用（含糊任务），不再用 `-1` 冒充「不适用」（issue #7）。

### `<run>/run.json`

本次运行的清单：`run_id`、`policy`、任务文件的 `tasks_sha256`、写入了哪些 / 跳过了哪些、起止时间。
`tasks_sha256` 让「同一个 run_id 但任务集被改过」这件事可被发现。

### `<run>/scores.json`

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
    "success": true, "n_steps": 2,

    "traj_sha256":  "949100dedb0a…",   // 这条分数绑定的是哪条轨迹（canonical JSON 的 sha256）
    "run_id":       "A-baseline",      // 哪一批
    "judge_model":  "dify:unknown@api.dify.ai",  // 谁打的分（设 DIFY_JUDGE_MODEL 可写实名）
    "prompt_sha256":"13e76676…",       // 哪版 rubric（模板的哈希，整批一致）
    "scored_at":    "2026-11-14T10:11:54Z"
  }
}
```

后五个字段是 provenance（见 `code/provenance.py`）。`correlate.py` 在拼接前会重算磁盘轨迹的
哈希并比对，**对不上就 exit 2、不写输出**；只有 `--force-join` 能强制出数，且输出文件头会被打上
`WARNING`。没有这五个字段的旧 `scores.json` 会被判为「无法验证」而拒绝——这是刻意的，不是 bug。

哈希口径是 **canonical JSON**（`sort_keys`、无多余空白、UTF-8），所以只改缩进/换行不会让指纹变化。

### `<run>/annotations.csv`

列：`task_id, objective, success, n_steps, trace, rubric` + 五列分数。
`backtrack_and_explore` 可填 `N/A` 或留空；其余填 1–4 整数。

### `<run>/correlation.md`

```
| 维度 | Pearson r | Spearman rho | Kendall tau | n（配对） | n（标注） | 备注 |
| backtrack_and_explore | - | - | - | 1 | 2 | 样本不足 |
| task_decomposition     | 0.83 | 0.82 | 0.77 | 10 | 10 | |
| overall（各维 r 的均值） | 0.81 | - | - | 41 | 43 | 4 个维度参与 |
```

---

## 5. 参数速查

**`code\run_episodes.py`**

| 参数 | 说明 |
|---|---|
| `--policy dify\|scripted` | 真实 Dify，或离线冒烟基线 |
| `--run-id <id>` | 批次名（默认 `<时间戳>-<policy>`），决定 `output/runs/<id>/` |
| `--out 目录` | 覆盖轨迹目录（默认 `output/runs/<run_id>/trajectories`） |
| `--overwrite` | 允许覆盖目录里已有的同名轨迹（默认跳过） |
| `--only t01_x,t02_y` / `--limit N` | 只跑指定 / 前 N 条 |
| `--tasks 文件` | 任务定义（默认 `data/tasks_shopping.json`） |
| `--headed` / `--verbose` | 显示浏览器 / 打印每步与原始回复 |
| `--max-obs-lines 200` | 观测最大行数（太大易被 Dify 截断） |
| `--screenshots` | 保存结束截图到 `<run>/trajectories/shots/` |

> `--max-steps` 基本无效：每个任务在 `data/tasks_shopping.json` 里已写死上限。

**`code\score_trajectories.py`**

| 参数 | 说明 |
|---|---|
| `--input 目录` | 轨迹目录 |
| `--out 文件` | 默认写到输入的同级目录：`<run>/scores.json` |
| `--run-id <id>` | 写进每条分数；默认取输出目录名 |
| `--mock` | 用确定性启发式替代 judge（不要与真分混用） |
| `--limit N` | 只判前 N 条 |
| `--include-observations` | 消融：把无障碍树也发给 judge |
| `--check-prompts` | 只比对 rubric 快照与上游，然后退出 |

**`code\make_annotation_sheet.py`**：`--input` / `--out` / `--md` / `--reasoning-chars` / `--obs-chars` / `--force`
（`--out`、`--md` 默认落在输入的同级目录；目标表已填且无 `--force` 时**拒绝写入**）

**`code\correlate.py`**：`--scores` / `--annotations`（默认同级 `annotations.csv`）/ `--out`（默认同级 `correlation.md`）
/ `--trajectories`（默认同级 `trajectories/`）/ `--force-join` / `--self-test`

---

## 6. 注意事项

1. **每次运行轨迹都不同**：LLM 采样、页面时序、网络都会影响结果；`task_id` 稳定但**内容不稳定**（这是本仓库核心发现的前提）。现在每次运行落在 `output/runs/<run_id>/`，默认不会覆盖；`correlate` 会用 `traj_sha256` 拒绝跨批拼接。要重跑同一批次就换一个 `--run-id`。
2. **judge 有抖动**：同一轨迹重跑分数可能差 0.2 以上；写报告建议每条判 2–3 次取均值。
3. **任务偏简单**：多数"一次走对"，`backtrack_and_explore` 常为 N/A；要让该维度有数据，需补"会走弯路"的任务（issue #8）。
4. **元素 id 是页内编号**：跨页后同一 id 指向别的元素，日志里会看到 `error: element N is not a text field`。属于环境特性。
5. **Playwright `EPERM mkdtemp`**：已自动处理，启动前把 `TEMP/TMP` 指向 `.tmp/`。
6. **Agent 应用只支持流式**：客户端自动从 blocking 回退 SSE，并对 `message` / `agent_message` 去重。
7. **CSV 编码**：用 Excel/WPS 改 `annotations.csv` 请存成「CSV UTF-8」。`correlate` 现在会尝试
   `utf-8-sig → gbk` 回退并给出提示，但别依赖它——2026-11-14 就因为存成 GBK 直接崩过一次。
8. **旧产物会被拒绝**：没有 `traj_sha256` 五个字段的 `scores.json`，`correlate` 一律判为「无法验证」。
   这是刻意的；`output/` 与 `output/runs/A-baseline/` 属于此类，要复算得加 `--force-join`。
9. **网络抖动会毁掉一整条轨迹**：Dify Agent 应用只走流式，早期的 `retries` 参数对流式无效，
   一次 TLS 抖动（`URLError: SSL: UNEXPECTED_EOF_WHILE_READING`）就让这条轨迹 0 步收场。
   现在流式路径也有 3 次指数退避重试；即便如此，**判分前仍要检查 `meta.error`**——截断的轨迹会让
   相关系数虚高（空轨迹人人给低分，天然"一致"）。`correlate` 会提示带 `error` 的条数，
   `--exclude-errors` 可单独看"只算正常结束"的版本。
10. **标注表编码**：Excel/WPS 默认存 GBK。`correlate` 能读，但想让文件干净就跑
    `code\normalize_annotations.py`（带备份，幂等）。

---

## 7. 重跑检查清单

- [ ] `docker ps` 里 `webarena-verified-shopping` 是 Up，`http://localhost:7770/` 返回 200
- [ ] `code\config.py` 显示两个 key 都是 `set`
- [ ] ① 跑完 `output\runs\<run_id>\trajectories\` 有 10 个 json、8 条 `success=true`（2 条含糊任务为 `null`），且没有 `*.failed.json`
- [ ] ② 跑完 `<run>\scores.json` 有 10 条，且验收脚本输出 `complete True`
- [ ] ③ 对照 `docs/打分指南.md` 打分，另存为 CSV UTF-8，`filled` 在 45–50 之间
- [ ] ④ `<run>\correlation.md` **没有** `WARNING` 行，且 `n（配对）` 与标注条数一致
