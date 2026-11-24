#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把各版本的「构建时间 / 译文时间 / 下载直链」写进 README 的表格。

由 CI 的 summary job 调用：每个 build job 会产出 `build-info-<版本>.json`，
这里把它们合并进 README.md 中 `<!-- BUILD-TABLE:BEGIN -->` 与
`<!-- BUILD-TABLE:END -->` 之间的表格，一个版本一行：

    版本 | 小版本号 | 构建时间 | 译文时间 | 合并册 PDF | 全部分册包

设计要点（都是踩过的坑）：

★ 只替换标记之间的内容，README 其它部分一个字不动 —— 人工编辑与自动更新
  才不会互相打架。
★ **合并**而不是重建：某个版本这轮没构建成功（没产出 info）时，保留表格里
  它原来那一行（含那条直链），不要把它变成 `?`。表格是给人看的历史，
  不是本轮的快照。
★ 3.10 固定不复写（已 EOL、release 已归档到 old 分支），保留一行占位。

★★ 表格永远只有 `ORDER` 这几行，一行不多一行不少 ★★
  小版本号是**就地覆盖**的：3.15.2 → 3.15.3 那天，`| 3.15 |` 那行的第二列
  变成 3.15.3，**不会额外多出一行 3.15.2**。历史小版本的产物在 `old` 分支
  （`old/v3.15.2/`），README 里不留痕。

★ 直链的**文件名带日期**，所以每轮都要重新取，不能靠模板拼。取的是发布页上
  真实存在的附件（GitHub API 读 release），不是本地推出来的名字 —— 某版本
  这轮失败时它保留上次那一行，链接不会失效。

用法：
    python3 ci/linux/update_readme_table.py <infos 目录> [README.md]

环境变量：`GITHUB_REPOSITORY`（默认本仓库）、`GITHUB_TOKEN` / `GH_TOKEN`
（CI 必带；本地可不带，走匿名额度 60 次/时）。
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

BEGIN = "<!-- BUILD-TABLE:BEGIN -->"
END = "<!-- BUILD-TABLE:END -->"

REPO = os.environ.get("GITHUB_REPOSITORY") or "zhou-dev-design/python-doc-pdf-zh"

#: 表格里出现的版本与顺序（3.10 是历史行，固定不复写）
ORDER = ["3.10", "3.11", "3.12", "3.13", "3.14", "3.15"]

#: 3.10 的固定行：它已 EOL，产物在 old 分支。
#: 前两个时间是**真实值，不是占位**，只是永远不再变：
#:   · PDF 构建时间 = 2026-11-03 那次构建（run #21）的 .po 时刻。
#:     取「构建 Python 3.10」步骤开始 19:48:16，加约 6 秒 —— 3.10 的
#:     步骤 1(4s)+2(1s)+3(1s) 合计 6s，所以 .po 落盘就在同一分钟。
#:   · 译文最后更新 = python-docs-zh-cn `3.10` 分支最后提交
#:     2026-10-19T06:32:05Z → 北京 2026-10-19 14:32（EOL 后基本冻结）。
#: 要改这一行只能改这里；README 里同名字符串会被本文件覆盖。
#: 直链指向 `old` 分支（release 已删），`?raw=true` 让浏览器直接下载。
PINNED = {
    "3.10": "| 3.10 | 3.10.22 | 2026-11-03 19:48 | 2026-10-19 14:32 "
            "| [PDF · 36.9 MB](https://github.com/zhou-dev-design/python-doc-pdf-zh"
            "/blob/old/v3.10.22/Python-3.10.22-docs-20261103.pdf?raw=true) "
            "| [RAR · 49.8 MB](https://github.com/zhou-dev-design/python-doc-pdf-zh"
            "/blob/old/v3.10.22/Python-3.10.22-docs-20261103.rar?raw=true) |",
}

HEAD = [
    "| 版本 | 小版本号 | PDF 构建时间 | 译文最后更新 | 合并册 PDF | 全部分册包 |",
    "|-|-|-|-|-|-|",
]

ROW_RE = re.compile(r"^\|\s*(\d+\.\d+)\s*\|")
#: 更宽的口径：第一列是任意形式版本号（`3.15.2`、`3.16`）。只用来识别
#: 「该丢的行」，表头（`| 版本 | …`）和分隔线（`|-|-|`）都不匹配它。
WIDE_RE = re.compile(r"^\|\s*(\d+(?:\.\d+)+)\s*\|")


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _patch_key(line: str) -> tuple[int, ...]:
    """从表格行里取出第二列的小版本号，作为可比较的元组。"""
    cs = cells(line)
    if len(cs) < 2:
        return (0,)
    nums = re.findall(r"\d+", cs[1])
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


def fetch_assets(tag: str, token: str | None) -> list[dict] | None:
    """读某个 tag 的 release 附件；读不到返回 None（调用方保留旧行）。"""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases/tags/{tag}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "python-doc-pdf-zh-readme-updater",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get("assets") or []
    except urllib.error.HTTPError as e:
        print(f"  读 {tag} 失败：HTTP {e.code}", file=sys.stderr)
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"  读 {tag} 失败：{e}", file=sys.stderr)
    return None


def link_cell(asset: dict | None, label: str) -> str:
    if not asset:
        return "—"
    mb = asset.get("size", 0) / 1048576
    return f"[{label} · {mb:.1f} MB]({asset['browser_download_url']})"


def link_cells(assets: list[dict]) -> tuple[str, str]:
    pdf = next((a for a in assets if a["name"].lower().endswith(".pdf")), None)
    arc = next((a for a in assets
                if a["name"].lower().endswith((".rar", ".zip"))), None)
    return link_cell(pdf, "PDF"), link_cell(arc, "RAR")


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
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    lines = list(HEAD)
    for v in ORDER:
        if v in PINNED:
            lines.append(PINNED[v])
            continue
        d = fresh.get(v)
        full = str(d.get("full") or "?").strip() if d else ""
        if not d or not full or full == "?":
            # 本轮没构建 → 整行（含直链）原样保留
            lines.append(old_rows.get(v) or f"| {v} | ? | — | — | 待发布 | 待发布 |")
            continue
        po = str(d.get("po") or "—").strip()
        zh = str(d.get("zh") or "—").strip()
        assets = fetch_assets(f"v{full}", token)
        if assets is None:
            # API 读不到：只有「旧行本来就是这一版」才能沿用那两条直链，
            # 否则会出现「行写着 3.15.3、链接指向 3.15.2 的文件」。
            old = cells(old_rows.get(v, ""))
            old_full = old[1] if len(old) >= 2 else ""
            if len(old) >= 6 and old_full == full:
                pdf_cell, arc_cell = old[-2], old[-1]
            else:
                pdf_cell, arc_cell = "待发布", "待发布"
        else:
            print(f"  {full}：{len(assets)} 个附件")
            pdf_cell, arc_cell = link_cells(assets)
        lines.append(f"| {v} | {full} | {po} | {zh} | {pdf_cell} | {arc_cell} |")

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
