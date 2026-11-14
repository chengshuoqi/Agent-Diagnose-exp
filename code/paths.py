"""Central place for every path the scripts need.

Directory layout (everything is derived from this file's location, so the
project can be moved or copied anywhere):

    repro/
    ├── code/                  <- this file lives here
    ├── data/tasks_shopping.json
    ├── output/                <- trajectories/, scores.json, annotations.*, correlation.md
    ├── docs/                  <- 打分指南.md ...
    ├── .venv/
    ├── .tmp/                  <- browser scratch space
    └── README.md
"""
from __future__ import annotations

from pathlib import Path

CODE = Path(__file__).resolve().parent
ROOT = CODE.parent                     # repro/
WORKSPACE = ROOT.parent                # 工作区根目录（放 AgentDiagnose-main、.env）

DATA = ROOT / "data"
OUTPUT = ROOT / "output"
DOCS = ROOT / "docs"
TMP = ROOT / ".tmp"

TASKS = DATA / "tasks_shopping.json"
TRAJECTORIES = OUTPUT / "trajectories"
SCORES = OUTPUT / "scores.json"
ANNOTATIONS = OUTPUT / "annotations.csv"
ANNOTATIONS_MD = OUTPUT / "annotations.md"
CORRELATION = OUTPUT / "correlation.md"

# AgentDiagnose 仓库（论文原始 prompt 从这里按路径加载）
REPO = WORKSPACE / "AgentDiagnose-main"
REPO_PROMPTS = REPO / "evaluator" / "scorers" / "prompts" / "prompt.py"

# .env 的搜索顺序：工作区根目录 -> repro/ -> code/ -> 当前目录
ENV_CANDIDATES = [
    WORKSPACE / ".env",
    ROOT / ".env",
    CODE / ".env",
    Path.cwd() / ".env",
]


def ensure_dirs() -> None:
    for directory in (DATA, OUTPUT, TRAJECTORIES, TMP):
        directory.mkdir(parents=True, exist_ok=True)
