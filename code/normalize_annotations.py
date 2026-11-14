"""把被 Excel / WPS 存成 GBK 的标注表转回 UTF-8（带 BOM）。

    python normalize_annotations.py                 # 处理 output/runs/*/annotations.csv
    python normalize_annotations.py 路径 [路径 ...]  # 只处理指定文件

只做一件事：检测编码 → 备份原件（`*.gbk.csv`）→ 写成 `utf-8-sig` → 回读校验行数。
已经是 UTF-8 的文件会被跳过（幂等，可以反复跑）。
"""
from __future__ import annotations

import argparse
import csv
import io
import shutil
from pathlib import Path

import paths


def detect(raw: bytes) -> str:
    for enc in ("utf-8-sig", "gbk", "utf-16"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return ""


def convert(path: Path) -> str:
    if not path.exists():
        return "缺失"
    raw = path.read_bytes()
    enc = detect(raw)
    if not enc:
        return "无法识别编码（未改动）"
    if enc == "utf-8-sig":
        return "已是 UTF-8（跳过）"

    text = raw.decode(enc)
    try:
        n_before = len(list(csv.DictReader(io.StringIO(text))))
    except Exception:
        return f"按 {enc} 解码后不是合法 CSV（未改动）"

    backup = path.with_suffix(f".{enc}.csv")
    shutil.copy2(path, backup)
    try:
        path.write_text(text, encoding="utf-8-sig", newline="")
    except PermissionError:
        return "文件被占用：请先在 Excel / WPS 里关闭它，再重试（原件未改动）"

    n_after = len(list(csv.DictReader(path.open(encoding="utf-8-sig", newline=""))))
    if n_after != n_before:
        return f"行数变化 {n_before}->{n_after}（请检查！备份在 {backup.name}）"
    return f"{enc} -> utf-8-sig（{n_after} 行，备份 {backup.name}）"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="*", help="默认 output/runs/*/annotations.csv")
    args = ap.parse_args()

    targets = [Path(t) for t in args.targets] or sorted(paths.RUNS.glob("*/annotations.csv"))
    if not targets:
        print("没有找到任何 annotations.csv；请指定路径。")
        return

    for p in targets:
        print(f"{p}: {convert(p)}")


if __name__ == "__main__":
    main()
