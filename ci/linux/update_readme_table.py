#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把各版本的「构建时间 / 译文更新时间」写进 README 的表格里。

由 CI 的 summary job 调用：每个 build job 会产出 `build-info-<版本>.json`，
这里把它们合并进 README.md 中 `<!-- BUILD-TABLE:BEGIN -->` 与
`<!-- BUILD-TABLE:END -->` 之间的表格。

设计要点（都是踩过的坑）：

★ 只替换标记之间的内容，README 其它部分一个字不动 —— 人工编辑与自动更新
  才不会互相打架。
★ **合并**而不是重建：某个版本这轮没构建成功（没产出 info）时，保留表格里
  它原来那一行，不要把它变成 `?`。表格是给人看的历史，不是本轮的快照。
★ 3.10 固定不复写（已 EOL、release 已归档到 old 分支），保留一行占位。

用法：
    python3 ci/linux/update_readme_table.py <infos 目录> [README.md]
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

BEGIN = "<!-- BUILD-TABLE:BEGIN -->"
END = "<!-- BUILD-TABLE:END -->"

#: 表格里出现的版本与顺序（3.10 是历史行，固定不复写）
ORDER = ["3.10", "3.11", "3.12", "3.13", "3.14", "3.15"]

#: 3.10 的固定行：它已 EOL，产物在 old 分支
PINNED = {
    "3.10": "| 3.10 | 3.10.22 | —（已 EOL，产物在 `old` 分支） | — |",
}

HEAD = [
    "| 版本 | 小版本号 | PDF 构建时间（北京时间） | 译文最后更新（北京时间） |",
    "|-|-|-|-|",
]

ROW_RE = re.compile(r"^\|\s*(\d+\.\d+)\s*\|")


def parse_existing(block: str) -> dict[str, str]:
    """把标记区里已有的表格行读出来 → {版本: 整行}。"""
    rows: dict[str, str] = {}
    for line in block.splitlines():
        m = ROW_RE.match(line.strip())
        if m:
            rows[m.group(1)] = line.strip()
    return rows


def main() -> int:
    infos = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "infos")
    readme = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "README.md")
    if not readme.is_file():
        print(f"找不到 {readme}", file=sys.stderr)
        return 2

    # ---------- 1. 读本轮各版本的数据 ----------
    fresh: dict[str, dict] = {}
    if infos.is_dir():
        for f in sorted(infos.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                print(f"  跳过读不了的 {f.name}：{e}")
                continue
            v = str(d.get("version") or "").strip()
            if v:
                fresh[v] = d
    print(f"本轮拿到 {len(fresh)} 个版本的数据：{'、'.join(sorted(fresh)) or '（无）'}")

    # ---------- 2. 读 README 现有表格（用于"本轮没构建的版本保留旧行"） ----------
    text = readme.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        print(f"README 里找不到 {BEGIN} / {END} 标记", file=sys.stderr)
        return 1
    m = re.search(re.escape(BEGIN) + r"(.*?)" + re.escape(END), text, re.S)
    old_rows = parse_existing(m.group(1) if m else "")

    # ---------- 3. 拼表格 ----------
    lines = list(HEAD)
    for v in ORDER:
        if v in PINNED:
            lines.append(PINNED[v])
            continue
        d = fresh.get(v)
        if d:
            full = str(d.get("full") or "?").strip()
            po = str(d.get("po") or "—").strip()
            zh = str(d.get("zh") or "—").strip()
            lines.append(f"| {v} | {full} | {po} | {zh} |")
        elif v in old_rows:
            lines.append(old_rows[v])          # 本轮没构建 → 保留上次的
        else:
            lines.append(f"| {v} | ? | — | — |")
    table = "\n".join(lines)

    # ---------- 4. 只换标记区 ----------
    new = re.sub(
        re.escape(BEGIN) + r".*?" + re.escape(END),
        BEGIN + "\n" + table + "\n" + END,
        text,
        flags=re.S,
    )
    if new == text:
        print("表格无变化，不写回")
        return 0
    readme.write_text(new, encoding="utf-8")
    print("README 表格已更新")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
