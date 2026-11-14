"""产物来源指纹（provenance）。

一个分数必须能回答四个问题：基于哪条轨迹、用哪个模型、哪版 rubric、什么时候。
本模块只负责其中"能算出来"的部分——把对象规范化后算 sha256，以及把一批轨迹
读成 `{task_id: 指纹}`。写不写、比不比，是调用方的事。

为什么用 canonical JSON 而不是原始字节：
    只重新缩进 / 换行 / 换编码，不应该让指纹变化；只有内容变了才应该。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def fingerprint(obj: Any) -> str:
    """一个 JSON 对象的内容指纹。内容变则值变，仅格式变则不变。"""
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def fingerprint_file(path: Path | str) -> str:
    return fingerprint(json.loads(Path(path).read_text(encoding="utf-8")))


def scan_dir(directory: Path | str) -> Dict[str, Dict[str, Any]]:
    """读一个轨迹目录，返回 {task_id: {sha256, n_steps, success}}。

    `*.failed.json` 是失败记录，不是轨迹，跳过（见 issue #7）。
    """
    out: Dict[str, Dict[str, Any]] = {}
    for p in sorted(Path(directory).glob("*.json")):
        if p.name.endswith(".failed.json"):
            continue
        try:
            traj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        meta = traj.get("meta", {}) or {}
        out[p.stem] = {
            "sha256": fingerprint(traj),
            "n_steps": len(traj.get("actions", [])),
            "success": meta.get("success"),
        }
    return out


def prompt_fingerprint(*parts: str) -> str:
    """rubric 的版本指纹：只对模板本身，不对具体某条轨迹。"""
    return hashlib.sha256("\n\n".join(p or "" for p in parts).encode("utf-8")).hexdigest()


def judge_label(base_url: str) -> str:
    """judge 的标识。Dify 背后的真实模型名对调用方不可见，所以不编造：

    - 设了 DIFY_JUDGE_MODEL 就用它；
    - 否则记 `dify:unknown@<host>`，至少能区分"换过端点"。
    """
    import os
    from urllib.parse import urlparse

    model = (os.environ.get("DIFY_JUDGE_MODEL") or "").strip() or "unknown"
    host = urlparse(base_url or "").netloc or "unknown"
    return f"dify:{model}@{host}"


def normalize_success(value: Any) -> Optional[bool]:
    """CSV 里是 TRUE/FALSE/空，JSON 里是 true/false/null，统一成三态。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().upper()
    if text in ("TRUE", "1", "YES", "SUCCESS"):
        return True
    if text in ("FALSE", "0", "NO", "FAIL", "FAILED"):
        return False
    return None
