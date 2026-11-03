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

★★ **表格永远只有 `ORDER` 这几行，一行不多一行不少** ★★
  小版本号是**就地覆盖**的：3.15.2 → 3.15.3 那天，`| 3.15 |` 那行的第二列
  变成 3.15.3，**不会额外多出一行 3.15.2**。历史小版本的产物在 `old` 分支
  （`old/v3.15.2/`），README 里不留痕。
  因此：表格里任何不在 `ORDER` 里的版本行（旧补丁版、试验性的 3.16 …）
  每次都会被**丢掉**，并在日志里报出丢了哪几行 —— 这是有意为之，不是 bug。

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
#: 更宽的口径：第一列是任意形式版本号（`3.15.2`、`3.16`）。只用来识别
#: 「该丢的行」，表头（`| 版本 | …`）和分隔线（`|-|-|`）都不匹配它。
WIDE_RE = re.compile(r"^\|\s*(\d+(?:\.\d+)+)\s*\|")


def _patch_key(line: str) -> tuple[int, ...]:
    """从表格行里取出第二列的小版本号，作为可比较的元组。"""
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) < 2:
        return (0,)
    nums = re.findall(r"\d+", cells[1])
    return tuple(int(x) for x in nums[:3]) or (0,)


def parse_existing(block: str) -> tuple[dict[str, str], list[str]]:
    """把标记区里已有的表格行读出来 → ({版本: 整行}, [不在名单里的行])。

    ★ 同一版本出现多行时保留**小版本号最大**的那一行（不是最后一行）。
      表格里本不该有重复，但万一手工写重了，也不该让旧补丁版盖住新的 ——
      「旧的小版本不显示」这条规则在这里同样成立。
    """
    rows: dict[str, str] = {}
    keys: dict[str, tuple[int, ...]] = {}
    dropped: list[str] = []
    for line in block.splitlines():
        s = line.strip()
        m = ROW_RE.match(s)
        if m:
            v = m.group(1)
            if v not in ORDER:
                dropped.append(s)          # 旧补丁版 / 3.16 之类的行：不要
                continue
            k = _patch_key(s)
            if v not in rows or k > keys[v]:
                rows[v] = s
                keys[v] = k
        elif WIDE_RE.match(s):
            # 看着像数据行，但版本不在名单里（旧补丁版 `3.14.9`、`3.16` …）
            dropped.append(s)
    return rows, dropped


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
    old_rows, dropped = parse_existing(m.group(1) if m else "")
    if dropped:
        print(f"  丢弃 {len(dropped)} 行不在名单里的旧行（表格只保留 "
              f"{'、'.join(ORDER)}）：")
        for d in dropped:
            print(f"    - {d}")

    # ---------- 3. 拼表格（行集合严格等于 ORDER，顺序固定） ----------
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
    # ★ 硬约束：表头 2 行 + 每个版本 1 行。多一行就说明有旧小版本漏进来了。
    expect = len(HEAD) + len(ORDER)
    if len(lines) != expect:
        print(f"内部错误：表格 {len(lines)} 行，应为 {expect} 行", file=sys.stderr)
        return 3
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
