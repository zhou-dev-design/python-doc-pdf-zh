#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Python 中文文档分册 PDF 构建器 · 多版本并行版（PyQt6 图形界面）

★★ 本文件是**唯一的主程序**（2026-11-03 起：原单版本版 `pdf_builder_gui.py` 已退役，
`build-sphinx-pdf.sh`、启动器与 exe 打包全部指向这里）★★

要点：
  · 版本可以多选（3.11 ~ 3.15，册数各不相同：29 / 32 / 37 / 38 / 39），选几个就跑几个；
    只勾一个就是原来的「单版本」用法，所以单版本版没有存在价值了；
  · 每个版本各用各的解释器（D:\\软件\\Python313 / 314 / 315），**各起一个子进程**并行跑
    —— 进程隔离，不会有 venv / 工作目录 / 环境变量互相踩的问题；
  · 点「开始处理」后弹出一个**多版本并行日志窗口**，每个版本一个独立日志面板
    （和主界面的「运行日志」长得一样：标题 + 复制 / 导出 / 清空 + 文本框），并排显示；
  · 文件夹与合并册名带上**完整版本号 + 日期**：
        <基准目录>/Python 3.13.16 PDF 文档 20261017
        <基准目录>/Python 3.13.16 PDF 文档 20261017/Python 3.13.16 文档 20261017.pdf

⚠ 维护约定：流水线（Pipeline / 内置工具 / 步骤实现）**只有这一份**。
  历史上它曾与单版本版同步维护，那次实验证明「两份实现」必然分叉 ——
  所以 2026-11-03 直接把单版本版删了。改流水线只改这里。

--------------------------------------------------------------------------------
单版本版的原说明（仍然适用）：

本程序是下列两份参考文件的 **Python 重写版**，步骤、判据、报错信息一一对应：

    sphinx-pdf/build-sphinx-pdf.sh                  一键 bash 脚本（全流程）
    sphinx-pdf/构建Python文档PDF-完整步骤.md          分步说明 + 故障排查表

与 bash 脚本的步骤对照（本程序的步骤号沿用脚本里的编号）：

    脚本步骤   本程序行号      内容
    --------   -----------    ------------------------------------------------
    0          0              前置检查：git / Python / xelatex / latexmk / makeindex
    1          1              联网稀疏克隆 CPython Doc（★ Include 不能漏）
    2          2              联网克隆 python-docs-zh-cn 的对应版本分支
    3          3              把 .po 按目录层级装进 Doc/locales/<lang>/LC_MESSAGES
    4          4              venv + 依赖（含 sphinxcontrib-svg2pdfconverter）
    5          5              构建 HTML（python-docs-theme，验证目录与超链接）
    6          6              构建 LaTeX 源（★ conf.py 的 rsvg → cairosvg）
    6b         7              封面标题中文化（localize-titles.py，11 册）
    7          8              编译 PDF（逐册串行 latexmk；$makeindex ＝ 修索引的脚本）
    7b         9              索引自检（分组标题「非字母/数字」+ 页码超链接 + 长条目断点）
    8          10             收集 / 验收 / 重命名

★ 默认配置就能直接跑：版本默认 3.14（可选 3.11 ~ 3.15，两个仓库同步切分支；3.10 已 EOL 不再提供），源码与翻译源默认**从网站实时克隆/更新**，
  语言默认中文，构建目录按版本自动推算。
★ 分册表（每版几册、每册叫什么）在 `sphinx-pdf/volumes.json`，界面「分册配置…」
  可以可视化编辑；`--tool volumes --verify` 联网对着 CPython 官方复核。

★ 索引（与参考样张一致）：
  · 所有非字母条目排在最前，并有加粗分组标题「非字母」（数字组是「数字」）
  · 每条页码都是可点的超链接（\\hyperpage）
  · 长模块路径不会压到隔壁栏（索引是双栏排的，溢出没页边距可去 → 叠字）
  做法：把 latexmk 的 $makeindex 换成 tools/fix-index.py —— 它先跑 makeindex，
  再就地修补 .ind（删掉按字节截断的坏标题、补标题名、给页码包 \\hyperpage、
  给长条目补 \\allowbreak{} 断行点），第 2 遍 xelatex 直接读到修好的索引，
  一遍编译搞定，不必事后重排 38 册。

脚本里用 `# ★` 标出的每一个"坑"，在本程序里都以注释保留，位置就在对应代码旁。

运行
----
    GUI ：python pdf_builder_multi.py             （或双击 启动PDF构建器.bat）
    命令行：python pdf_builder_multi.py --cli              全流程，终端打印
            python pdf_builder_multi.py --cli --from 7     从步骤 7 开始（6b）
            python pdf_builder_multi.py --cli --only 0     只跑指定步骤
            python pdf_builder_multi.py --cli --version 3.13
            python pdf_builder_multi.py --cli --config x.json

依赖
----
    GUI 自身 ：PyQt6
    流程       ：见步骤 4 的 PIP_PACKAGES；TeX Live 需含 xelatex/latexmk/makeindex
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

# =============================================================================
# 一、常量：步骤表、重命名映射、依赖清单、默认配置
# =============================================================================

#: 步骤表 —— (行号, 脚本里的编号, 标题, 说明)
#: 行号是 0..10 的连续整数，用来索引界面列表；脚本编号保留 "6b" "7b" 的写法。
STEPS: list[tuple[int, str, str, str]] = [
    (0, "0", "前置检查", "检查 git / Python / xelatex / latexmk / makeindex 是否就绪"),
    (1, "1", "获取 CPython 源码", "联网稀疏克隆 Doc + Misc/NEWS.d + Include（Include 不能漏）"),
    (2, "2", "准备中文翻译", "联网克隆 python-docs-zh-cn 的对应版本分支（可改用本地目录）"),
    (3, "3", "安装 locales", "按原始目录层级把 .po 铺进 Doc/locales/<lang>/LC_MESSAGES"),
    (4, "4", "虚拟环境与依赖", "venv + sphinx + python-docs-theme + svg2pdfconverter"),
    (5, "5", "构建 HTML", "python-docs-theme 主题 / 目录树 / 站内超链接"),
    (6, "6", "构建 LaTeX 源", "sphinx -b latex；并把 conf.py 的 rsvg 换成 cairosvg"),
    (7, "6b", "封面标题中文化", "localize-titles.py（11 册，封面＋页眉一起变）"),
    (8, "7", "编译 PDF", "逐册串行 latexmk；$makeindex 换成修索引的脚本"
                        "（页码变超链接 + 长条目补断点）"),
    (9, "7b", "索引自检", "分组标题「非字母/数字」+ 页码 \\hyperpage 超链接 + 长条目断点逐册核对"),
    (10, "8", "收集 / 验收 / 重命名", "复制产物 + 生成验收报告 + 中文文件名"),
    (11, "9", "合并成一册", "38 册合成一本带完整书签的总册（一级书签 + Python 指南分组）"),
    (12, "10", "清理过程文件", "删掉构建过程中产生的 cpython / venv / 翻译源 / 日志，只留成品 PDF"),
]

#: 步骤 10「清理过程文件」的范围（下拉框用）
CLEAN_MODES: list[tuple[str, str]] = [
    ("none", "不清理（保留全部过程文件）"),
    ("build", "只删构建中间件：<根>/cpython/Doc/build"),
    ("all", "全删：cpython 源码 + venv + 翻译源 + 日志（只留成品 PDF）"),
]

#: Doc/ 之外的、被文档正文引用到的资源目录 —— 稀疏克隆必须一起带上。
#:   ★ 3.15 起 Doc/whatsnew/3.15.rst 与 Doc/library/profiling.sampling.rst 写了
#:     `.. image:: ../../Lib/profiling/sampling/_assets/tachyon-logo.png`，
#:     图片在 **Lib/** 下（Doc 之外）。漏取它的后果很隐蔽：
#:       Sphinx 找不到图片时**不报错**，只留一条 "File ... not found" 软警告，
#:       然后把**原始相对路径**原样写进 .tex —— Windows 上分隔符是反斜杠，
#:       于是 `..\Lib\profiling\sampling\_assets\tachyon-logo.png` 里的
#:       `\Lib` `\profiling` `\_assets` 全成了未定义控制序列 → xelatex 报错、
#:       latexmk 退出码 12 → 整个册子（本例 library / whatsnew）出不来 PDF。
#:     实测：39 册里就这 2 册挂，而报错点离病根隔了 20 分钟 + 两层工具。
#: 稀疏检出的路径（`--filter=blob:none` 下，**只有列在这里的文件才真拉 blob**）。
#:
#: ★ 判据不是「Doc 需要什么」，而是「Doc 引用了哪些 Doc/ 之外的文件」——
#:   这件事可以直接量出来，别靠记：`tools/check-doc-refs.py <Doc 目录>`。
#:
#:   Doc                 ← 正文（同时含 Doc/tools/、Doc/locales/）
#:   Misc/NEWS.d         ← Doc/Makefile 的 build 目标要拼 NEWS
#:   Include             ← Doc/tools/extensions/patchlevel.py 读 Include/patchlevel.h
#:                         取版本号（漏了它 Sphinx 直接崩）
#:   Grammar             ← reference/grammar.rst 用 literalinclude 引
#:                         Grammar/python.gram，即《完整的语法规范》整章正文
#:   Parser              ← library/ast.rst 用 literalinclude 引 Parser/Python.asdl
#:   Lib/profiling/sampling ← 3.15 的 Tachyon 文档引这里的配图
#:
#: ★★ 漏掉一条的后果**是静默的**，这是本项目最贵的一类坑：
#:   · literalinclude / include 找不到文件 → Sphinx 只留一条 warning、`.tex` 里
#:     什么都不写 → **PDF 里整章空白**（3.13/3.14/3.15 的《完整的语法规范》
#:     整章只剩标题 + 两行引言；实测该章本该 20 多页）
#:   · image / figure 找不到文件 → 把**原始相对路径**原样写进 `.tex`，Windows 上
#:     分隔符是反斜杠 → `\Lib` `\profiling` 成了未定义控制序列 → latexmk 退出码 12
#:   两种都得等构建完才看得出来，所以现在由 `tools/check-doc-refs.py` 在
#:   步骤 6 之前几秒内拦住（GUI 与 bash 调的是同一份实现）。
SPARSE_PATHS: list[str] = [
    "Doc",
    "Misc/NEWS.d",
    "Include",
    "Grammar",
    "Parser",
    "Lib/profiling/sampling",
]

STEP_BY_ROW: dict[int, tuple[int, str, str, str]] = {s[0]: s for s in STEPS}

#: 最终文件名映射 —— ★ **唯一真源就是本文件第六节里内联的那张表**
#:   （原 `sphinx-pdf/tools/name_map.py`；那个文件现在只剩几行转发器）。
#:   2026-09-26 之前这里有第三份副本（另两份在 rename-pdf.sh 与 merge-pdf.py），
#:   三份必须手工同步，实测漏同步过两次。2026-10-04 起干脆内联成一份：
#:     * 重命名     → 第六节 `rnpdf_main`（原 `tools/rename-pdf.py`）
#:     * 合并册结构 → 第六节 name_map 的 HOWTO 表 + `mgpdf_main`
#:   **不要**在这里再加映射表。

#: 步骤 3 要铺进 locales 的子目录（与脚本里的 for d in ... 一致）。
#: 实际实现用 rglob 自动发现，这份清单只用于日志里做"是否漏目录"的对照。
ZH_SUBDIRS = [
    "c-api", "deprecations", "distributing", "extending", "faq", "howto",
    "installing", "library", "reference", "tutorial", "using", "whatsnew",
]

#: 步骤 4 的依赖（对齐 Doc/requirements.txt；blurb / sphinx-linklint 是 CI 用的，出 PDF 不需要）。
PIP_PACKAGES = [
    "sphinx<9.0.0",
    "pygments>=2.21",
    "sphinx-notfound-page~=1.0.0",
    "sphinxext-opengraph~=0.13.0",
    "sphinxext-rediraffe",
    "python-docs-theme>=2023.3.1,!=2023.7",
    # c-api/lifecycle.rst、howto/logging.rst、library/datetime.rst 有 SVG 插图，
    # LaTeX 引擎不认 SVG，必须装转换器（CairoSVG 分支在 Windows 上免额外 DLL）。
    "sphinxcontrib-svg2pdfconverter[CairoSVG]",
    # 步骤 9（合并成一册）和验收报告都要用 pypdf
    "pypdf>=5",
]

#: 依赖就绪判据：这些模块都能 import 就不必再跑 pip。
READY_MODULES = ["sphinx", "python_docs_theme", "sphinxcontrib.cairosvgconverter", "pypdf"]

#: 官方源 —— 配置的镜像出问题时的**最后退路**（只有镜像失败才用，平时不碰）。
OFFICIAL_INDEX = "https://pypi.org/simple"


def pip_hint(text: str) -> str:
    """把 pip 那一大坨输出翻成一句人话（给界面/日志用）。

    ★ 为什么需要它：pip 的报错动辄几十行，真正的判据（例如
      `THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE`）
      埋在一堆 `Collecting …` / `Downloading …` 中间。实测在清华源上就撞过：
      下载下来的 wheel 和索引里登记的 sha256 对不上（镜像上那份文件被换过，
      或本地 pip 缓存是坏的）—— 这类失败**与代码无关**，换源或清缓存就好，
      但这层结论得替用户先说出口，否则他只会看到「pip 装依赖失败」。
    """
    low = text.lower()
    if "do not match the hashes" in low or "hash mismatch" in low:
        return ("下载到的文件与索引里登记的 sha256 对不上 —— 镜像上那份包被换过，"
                "或本地 pip 缓存是坏的（换源 / 加 --no-cache-dir 即可）")
    if "no matching distribution" in low or "could not find a version" in low:
        return "源里没有可用的包（镜像缺文件，或该版本已从 PyPI 撤下）"
    if any(k in low for k in ("read timed out", "connection", "proxy", "ssl",
                              "temporary failure", "timed out", "network is unreachable")):
        return "网络/代理问题（连不上源，或连接被中途掐断）"
    if "no space left" in low:
        return "磁盘空间不足"
    for ln in reversed(text.splitlines()):
        s = ln.strip()
        if s.startswith("ERROR:") or s.startswith("error:"):
            return s[:200]
    return ""


# ---------------------------------------------------------------------------
# cairo 运行库（cairocffi / CairoSVG 需要，**pip 不会装**）
# ---------------------------------------------------------------------------
#: cairo 的文件名（Windows / Linux / macOS 三套）。
#: ★ cairocffi 是用 `ctypes.CDLL` 按这些名字在 **PATH 里**找的。
CAIRO_DLL_NAMES = ("libcairo-2.dll", "cairo-2.dll", "cairo.dll",
                   "libcairo.so.2", "libcairo.2.dylib")

#: 知道「自带 cairo」的常见安装位置（按优先级；不存在的会被跳过）。
CAIRO_DIR_HINTS = (
    r"C:\Program Files\gnuplot\bin",
    r"C:\Program Files (x86)\gnuplot\bin",
    r"C:\Program Files\GTK3-Runtime Win64\bin",
    r"C:\Program Files (x86)\GTK3-Runtime Win64\bin",
    r"C:\Program Files\GTK2-Runtime\bin",
    r"C:\msys64\mingw64\bin",
    r"C:\msys64\ucrt64\bin",
)


def _dll_loadable(path: str) -> bool:
    """这个 DLL 能不能**真的**加载（存在 ≠ 能加载：依赖缺了照样 0x7e）。"""
    try:
        import ctypes
        ctypes.CDLL(path)
        return True
    except Exception:                                  # noqa: BLE001
        return False


def cairo_loadable() -> bool:
    """当前进程里能不能按名字加载 cairo。

    ⚠️ 只当**诊断**用，别拿它做判断：`ctypes.CDLL` 一旦按全路径加载过，
       后面按裸名字再要一次会直接命中已加载的模块 —— 同一个进程里第二次调用
       永远返回 True，与「子进程的 PATH 里到底有没有」是两码事（踩过）。
    """
    return any(_dll_loadable(n) for n in CAIRO_DLL_NAMES)


def _dir_has_cairo(d: str) -> bool:
    """这个目录里有没有一份**能加载**的 cairo。"""
    for n in CAIRO_DLL_NAMES:
        try:
            p = Path(d) / n
            if p.is_file() and _dll_loadable(str(p)):
                return True
        except OSError:
            continue
    return False


def _path_has_cairo() -> bool:
    """系统 PATH 里是不是本来就有 cairo 的文件（**纯查文件，不加载**）。"""
    for d in os.environ.get("PATH", "").split(os.pathsep):
        d = d.strip()
        if not d:
            continue
        try:
            if any((Path(d) / n).is_file() for n in CAIRO_DLL_NAMES):
                return True
        except OSError:
            continue
    return False


def _scan_common_cairo() -> str:
    """扫一遍常见安装位置，返回第一个可用的目录（空串 = 没有）。"""
    cands: list[str] = list(CAIRO_DIR_HINTS)
    try:
        cands.append(str(Path(sys.executable).resolve().parent))
    except Exception:                                  # noqa: BLE001
        pass
    # 再扫一层 Program Files\*\bin（GTK / 各种带 cairo 的软件都这么摆）
    for base in (r"C:\Program Files", r"C:\Program Files (x86)"):
        try:
            cands.extend(str(p) for p in Path(base).glob("*/bin"))
        except OSError:
            continue
    seen: set[str] = set()
    for d in cands:
        try:
            key = os.path.normcase(os.path.abspath(d))
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        if _dir_has_cairo(d):
            return d
    return ""


def find_cairo_dir(extra: list[str] | None = None) -> str:
    """找一个**含可用 cairo 运行库**的目录；找不到返回空串。

    ★★ 为什么非要有这一段（2026-10-23 实测踩到，代价是两次 17 分钟）★★
      `sphinxcontrib.cairosvgconverter.is_available()` 里是
          try: import cairosvg
          except ImportError: return False
      而 cairocffi 找不到 `libcairo-2.dll` 抛的是 **OSError**（不是 ImportError）
      ⇒ 冒泡成未捕获异常 ⇒ `sphinx-build` 直接退出码 2、**一个 .tex 都不产出**。
      触发条件很隐蔽：文档里得有真正的 `.. image:: *.svg`。
      3.14 / 3.15 有（c-api/lifecycle 等），3.13 只有 `.. raw:: html :file:`，所以 3.13 不炸。
      pip 不提供 cairo，这里就替 cairocffi 找一遍，把目录加进**子进程**的 PATH
      （只动我们自己的子进程，不污染系统 PATH）。

    顺序：环境变量 `PDFBUILDER_CAIRO_DIR` > `extra`（调用方给的，比如 venv Scripts）
          > 常见安装位置 > exe 所在目录。
    """
    if not IS_WIN:
        return ""                       # Linux/macOS 由系统包管理器管，别多事
    if _path_has_cairo():
        return ""                       # 系统 PATH 本来就有 → 什么都不用加
    ev = os.environ.get("PDFBUILDER_CAIRO_DIR", "").strip()
    if ev and _dir_has_cairo(ev):
        return ev
    for d in (extra or []):
        if d and _dir_has_cairo(d):
            return d
    return _scan_common_cairo()

#: 只把这些行"透传"到界面日志（latexmk 输出动辄几万行，全塞界面会卡）。
#: 勾选「显示完整输出」后不再过滤，且任何情况下完整输出都写进日志文件。
NOTABLE = re.compile(
    r"^!"
    r"|^! LaTeX Error"
    r"|Invalid UTF-8"
    r"|Rerun to get"
    r"|Label\(s\) may have changed"
    r"|[Ll]aTeX Warning"
    r"|Package \S+ Warning"
    r"|^Latexmk:.*(?:rror|failed|Failed)"
    r"|Traceback"
    r"|No such file or directory"
    r"|Cannot determine size"
    r"|[Cc]annot "
    r"|^==>"
)

#: ANSI 转义序列（CSI 如 `\x1b[2K` `\x1b[01m` `\x1b[39;49;00m`，以及两字节的 ESC-x）。
#:
#: ★ 为什么必须剥掉：**Sphinx 8 在 Windows 上是「无条件着色」的** ——
#:   `sphinx/_cli/util/colour.py::terminal_supports_colour()` 里写着
#:       if 'NO_COLOR' in environ: return False
#:       if sys.platform == 'win32': return True      # ← 直接 True，不看 isatty！
#:   Linux 上它是 `sys.stdout.isatty()` 才着色，所以管道里干净；Windows 上**管道里
#:   也照样**吐 `\x1b[01mreading sources... \x1b[39;49;00m[  6%] ...`。
#:   这些字节进界面/日志就是一片 `[2K[01m` 乱码（实测本次 gui-build.log 有 6934 个 ESC）。
#:   两道防线：① 子进程环境里塞 `NO_COLOR=1`（源头不出色）；② 这里再剥一遍
#:   （防别的工具、别的版本 —— 包括 pip 的彩色输出）。
ANSI_ESC = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-Z\\-_]")


def strip_ansi(text: str) -> str:
    """去掉终端着色转义。只认真正的 ESC(0x1b) 开头，不会误伤 `[2K` 这类普通文本。"""
    return ANSI_ESC.sub("", text) if "\x1b" in text else text


#: Sphinx 的进度行形如 `正在读取源文件……[ 48%] library/ensurepip` /
#: `writing output... [ 50%]`。这类行是「当前步骤」进度条唯一的数据源，单独识别。
#: ⚠️ 必须**在 `strip_ansi()` 之后**再匹配：着色版本里 `%` 前面还夹着转义序列。
SPHINX_PROG = re.compile(r"\[\s*(\d+)%\]")
#: 行号（STEPS 里的第几个）：5 = 构建 HTML，6 = 构建 LaTeX 源。
#: 其它步骤的进度用各步骤自己算的 sub（如步骤 7 按册计数），不解析百分比。
SPHINX_STEP_ROWS = frozenset({5, 6})

IS_WIN = os.name == "nt"

#: Sphinx 只在「CJK 语言」下加载 xeCJK、给正文配汉字字体（Fandol 等）。
#: 语言填 en/其它时，CPython conf.py 的 fontpkg 只给 FreeSerif/FreeSans/FreeMono，
#: 汉字一个字形都没有 → XeTeX 静默丢字，日志刷一片
#: `Missing character: There is no 安 (U+5B89) in font [FreeSansBold.otf]`。
#: 最坑的是它不报错：界面全绿，产出却是英文正文＋页眉缺字的 PDF。
CJK_LANGS = frozenset({"zh_CN", "zh_TW", "ja", "ko", "zh", "ja_JP"})
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
#: XeTeX 的缺字告警，例：`Missing character: There is no 安 (U+5B89) in font [...]`。
MISSING_CHAR_RE = re.compile(r"Missing character: There is no (.) \(U\+")
#: 正文汉字少于这个数就认为"这本没被翻译"，多半是语言设错了。
CJK_MIN_PER_BOOK = 200

#: 构建根目录里各子路径（相对 ROOT）——与 bash 脚本里的写法一一对应。
P_CPYTHON = "cpython"
P_VENV = "venv"


# =============================================================================
# 二、异常与工具函数
# =============================================================================

class Fail(Exception):
    """步骤失败。消息直接显示到界面，等同于脚本里的 die()。"""


class Cancelled(Exception):
    """用户点了「停止」。"""


def now_hms() -> str:
    return time.strftime("%H:%M:%S")


def human_dur(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return f"{sec}s"
    m, s = divmod(sec, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def cmdline(cmd: list[str]) -> str:
    """把命令渲染成可读的一行（仅用于显示）。"""
    try:
        return shlex.join(cmd)
    except AttributeError:                                  # py<3.8
        return " ".join(cmd)


def read_text_safe(p: Path, limit: int | None = None) -> str:
    try:
        t = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return t[:limit] if limit else t


def is_root_tex(p: Path) -> bool:
    """是不是 Sphinx 生成的「册子」根文件（带 \\documentclass）。

    目录里还有 SVG 转出来的插图 .tex，那些没有 \\documentclass，必须排除。
    """
    head = read_text_safe(p, 8000)
    return "\\documentclass" in head


#: 步骤 7 自动并发数的上限。
#:   为什么不直接 `cpu_count()`：单册 latexmk 的峰值内存不低（library 那样
#:   2358 页的大册，xelatex 能到 1 GB 以上），18 核全开容易开始换页反而变慢。
#:   想更快就传 `--jobs N`（或配置里写 jobs）。
AUTO_JOBS_CAP = 6


def list_root_tex(latex_dir: Path) -> list[Path]:
    return [f for f in sorted(latex_dir.glob("*.tex")) if is_root_tex(f)]


def kill_tree(pid: int) -> None:
    """连子孙进程一起杀（latexmk 会拉起 perl / xelatex / makeindex）。"""
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, creationflags=CREATE_NO_WINDOW)
        else:
            os.killpg(os.getpgid(pid), 9)
    except Exception:
        pass


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0


def _never_show_console_windows() -> None:
    """让本进程 spawn 的**所有**子进程都不弹黑色控制台窗口（Windows）。

    ★ 为什么必须做：打包后的 exe 是 **GUI 子系统**（`console=False`）—— 它自己
      没有控制台。这种进程一旦启动一个控制台程序，Windows 会**给它新分配一个
      控制台窗口**；而那个子进程的 stdout 常常已经被我们接进了管道，于是屏幕上
      出现一块**纯黑的空窗口**，用户完全看不懂它在干什么（本次就踩到了：
      构建到步骤 7「编译 PDF」时黑框弹出来挡住界面）。

    ★ 实测中招的三处（都不在 `run()` 里，所以漏掉了）：
        · `_git_head_kind()` 的 `git ls-tree`   → 步骤 0/6/7 的引用自检
        · `fidx_main()` 里的 `makeindex`        → 步骤 7 每册的索引（最频繁，39 次）
        · `cover_line()` 的 `pdftotext`         → 步骤 8 取封面标题
      补完这三处之后仍然加这一层**兜底**：这类"漏一处就闪一次黑框"的坑
      已经不止踩过一次，靠"每个调用点都记得写"不如靠这里统一兜住。

    ★ 只做一件事：**默认**补上 `CREATE_NO_WINDOW`。调用点自己显式写了的
      （包括 `taskkill` 那种）一律不动；非 Windows 平台完全跳过。
    """
    if not IS_WIN:
        return
    _orig_init = subprocess.Popen.__init__

    def _init(self, *args, **kwargs):                      # noqa: ANN001
        if not kwargs.get("creationflags"):
            kwargs["creationflags"] = CREATE_NO_WINDOW
        _orig_init(self, *args, **kwargs)

    _init.__doc__ = "subprocess.Popen.__init__ + Windows 默认 CREATE_NO_WINDOW"
    subprocess.Popen.__init__ = _init                     # type: ignore[method-assign]


_never_show_console_windows()


def open_in_explorer(path: Path) -> None:
    try:
        if IS_WIN:
            os.startfile(str(path))                        # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 强制删除（步骤 10「清理过程文件」以及各种"删旧目录重来"的场合）
# ---------------------------------------------------------------------------
def _long_path(p: Path | str) -> str:
    """路径长到会撞 Windows 的 260 字符 MAX_PATH 时，换成 `\\\\?\\` 扩展长度形式。

    ★ 为什么非加不可：`cpython/.git/objects/pack/` 里的文件名本身就有 50 多字符，
      再叠上「桌面/编程软件/Python 文档/Python 3.15 PDF 文档」这种中文长路径，
      很容易越过 260 —— 这时 `os.stat` / `os.scandir` / `os.unlink` 报的是
      FileNotFoundError / PermissionError（**其实文件就在那儿**），
      表现出来正是「删除过程文件经常失败」。

    ★★ 阈值判据是 `len(s) >= 240`（盘符 3 + 240 = 243 实际长度，留 17 字符余量）。
      **不要**改成「无条件加」：`\\\\?\\` 会让 Windows 跳过全部路径规范化，
      有些杀软/EDR/删除助手会因此认不出路径而报错（实测 WorkBuddy 自带的
      safe-delete shim 就会 `SAFE_DELETE_FAIL_CLOSED`）。只在真需要时才用。

    ★★ 但**只给「传进来的那个根」加是不够的**（2026-10-06 实测踩到）：
      目录树是一层层拼出来走的，根不长、树很深时，第三层往后就退回普通路径，
      照样中招 —— 报的是 `FileNotFoundError: [WinError 3] 系统找不到指定的路径`，
      而文件明明在。所以调用方（`_rmtree_forced`）必须**每一层都重新套一次**，
      长度够了的那些层自然就被转成扩展长度形式，走到多深都不会断层。
    """
    s = str(p)
    if not IS_WIN:
        return os.path.abspath(s)
    if s.startswith("\\\\?\\"):            # 已经套过了，别套第二遍
        return s
    s = os.path.abspath(s)
    if len(s) < 240:
        return s
    if s.startswith("\\\\"):               # UNC：\\server\share → \\?\UNC\server\share
        return "\\\\?\\UNC\\" + s[2:]
    return "\\\\?\\" + s


def _clear_readonly(p: str) -> None:
    """去掉只读位。

    ★ git 的 `objects/pack/*.pack` / `*.idx` **天生是只读的**（`-r--r--r--`），
      `shutil.rmtree` 碰到它们直接 `PermissionError` —— 这是实测里
      「删 cpython 目录必失败」的头号原因。Windows 上 chmod 只认只读位，
      0o777 就够了。
    """
    try:
        os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _deleted(p: Path) -> bool:
    """路径是否已经不在了（走长路径前缀，免得把"太长"误判成"已删"）。"""
    try:
        os.stat(_long_path(p))
    except OSError:
        return True
    return False


def _rmtree_forced(p: Path) -> None:
    """自己走一遍目录树删掉：清只读位、**每一层都重算长路径前缀**、不跟随符号链接。

    ★★ 为什么**不用 `os.walk`**（2026-10-06 实测踩到，很隐蔽）：
      `os.walk` 只对**传进去的那个根**用我们给的路径，往下是它自己用
      `os.path.join(top, name)` 拼的。于是「根不长、树很深」时，第 3 层往后
      就悄悄变回普通路径 → 越过 260 字符 → 报
      `FileNotFoundError: [WinError 3] 系统找不到指定的路径`（文件明明在）。
      再加上给 `onerror` 挂了「必须抛」，这一下就把**整个清理**打成失败。
      手工递归走 + 每次拼完都过一遍 `_long_path()`，就不存在这个断层：
      短路径保持普通形式（对杀软/删除助手友好），长到 240 以上的那一层
      自动变成 `\\\\?\\` 形式（绕开 MAX_PATH），再往下的子项沿用同一个前缀。
    """
    root = _long_path(p)

    def _walk(cur: str) -> None:
        try:
            entries = list(os.scandir(cur))
        except OSError:
            _clear_readonly(cur)          # 目录只读也会挡 scandir
            entries = list(os.scandir(cur))
        subdirs: list[str] = []
        for e in entries:
            fp = _long_path(e.path)
            # ★ 符号链接/联接点当文件删（`is_dir(follow_symlinks=False)`），
            #   否则会顺着链接删到别处去。
            try:
                is_dir = e.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False
            if is_dir:
                subdirs.append(fp)
                continue
            try:
                os.unlink(fp)
            except OSError:
                _clear_readonly(fp)
                os.unlink(fp)
        for d in subdirs:                 # 自底向上：先清空再删目录
            _walk(d)
            try:
                os.rmdir(d)
            except OSError:
                _clear_readonly(d)
                os.rmdir(d)

    _walk(root)
    os.rmdir(root)


def _unlink_forced(p: Path) -> None:
    s = _long_path(p)
    try:
        os.unlink(s)
    except OSError:
        _clear_readonly(s)
        os.unlink(s)


def _cmd_forced_delete(p: Path) -> bool:
    """最后一道兜底：交给系统自带的 `del /f` + `rd /s /q`。

    Python 删不掉的怪状态（只读、被扫毒软件缓了句柄）它多半能删。
    这里刻意**不用**长路径前缀 —— cmd 的内建命令不认 `\\\\?\\`。
    """
    if not IS_WIN:
        return False
    s = os.path.abspath(str(p))
    q = '"' + s + '"'
    if os.path.isdir(s):
        cmd = f"del /f /s /q {q} >nul 2>&1 & rd /s /q {q} >nul 2>&1"
    else:
        cmd = f"del /f /q {q} >nul 2>&1"
    try:
        subprocess.run(["cmd", "/c", cmd], capture_output=True,
                       creationflags=CREATE_NO_WINDOW, timeout=1800)
    except (OSError, subprocess.SubprocessError):
        return False
    return _deleted(p)


def force_delete(p: Path, *, tries: int = 3, log=None) -> None:
    """**强制**删除文件或目录；只有实在删不掉才抛 OSError。

    分四层，逐层加力（每一层都对着一个实测过的失败原因）：

      ① 清只读位 + `\\\\?\\` 长路径前缀 —— git 的 pack 文件只读 / 路径超 260
      ② 重试 `tries` 次（间隔递增）     —— 杀软、索引器、子进程刚退出还没撒手
      ③ `del /f` + `rd /s /q` 兜底      —— Python 删不掉的怪状态
      ④ 还不行 → **抛异常**，由调用方把它明确报给用户（绝不静默当成功）

    ★ 绝不用 `rmtree(..., ignore_errors=True)`：它**静默**放过删不掉的东西 ——
      曾经踩到的后果是旧 `cpython/` 目录没删掉，紧接着 `git clone` 因为
      「目标目录非空」失败，报错却指向 git，查半天。
    """
    p = Path(p)
    last: OSError | None = None
    for attempt in range(1, tries + 1):
        try:
            if os.path.isdir(_long_path(p)):
                _rmtree_forced(p)
            else:
                _unlink_forced(p)
            return
        except OSError as e:
            last = e
            if attempt < tries:
                if log:
                    log(f"      · {p.name} 第 {attempt} 次没删掉"
                        f"（{e.strerror or e}），重试…")
                time.sleep(0.6 * attempt)
    if _cmd_forced_delete(p) or _deleted(p):
        return
    if last is not None:
        raise last


# =============================================================================
# 三、配置
# =============================================================================

def app_dir() -> Path:
    """程序「自己的」目录 —— `config.json`、错误日志都写这里。

    ★ 打包成 exe（PyInstaller）后**不能再有 `__file__` 的念头**：
      onefile 下它是临时解压目录（`_MEIPASS`，进程退出即删），
      onedir 下它在 `_internal/` 里 —— 两种情况用户都找不到、也留不住。
      所以有 exe 时一律用 **exe 所在目录**。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _first_existing(*cands: str) -> str:
    for c in cands:
        if c and Path(c).exists():
            return c
    return cands[0] if cands else ""


def _guess_python() -> str:
    """猜「建 venv 用的解释器」。

    ★ 打包成 exe 后**绝不能回退到 `sys.executable`** —— 那时它就是 exe 本身，
      拿它跑 `-m venv` 会把参数塞给本程序自己的 argparse，报出一堆
      和「缺 Python」毫无关系的错（实测最容易把人带偏的一类）。
      所以 frozen 下猜不到就**返回空**，交给 `step0` 用
      `shutil.which("python3"/"python")` 兜底，或给出「请指定解释器」的明确报错。
    """
    cands = [
        r"C:\Users\zb137\.workbuddy\binaries\python\versions\3.13.12\python.exe",
        r"C:\Users\zb137\.workbuddy\binaries\python\versions\3.14.7\python.exe",
        shutil.which("python3") or "",
        shutil.which("python") or "",
    ]
    cands = [c for c in cands if c]
    for c in cands:
        if Path(c).exists() and "gui-venv" not in c.lower():
            return c
    if getattr(sys, "frozen", False):
        return ""
    return cands[0] if cands else sys.executable


def _guess_texlive() -> str:
    return _first_existing(
        r"F:\texlive\2025\bin\windows",
        r"C:\texlive\2025\bin\windows",
        r"D:\texlive\2025\bin\windows",
        r"E:\texlive\2025\bin\windows",
        "/usr/bin",
    )


def _guess_zh_src() -> str:
    """本机现成的翻译源目录（**留空才是默认**：留空 = 每次联网克隆最新的）。

    ★ 打包后不能按 `__file__` 往上推算仓库位置（那是个临时解压目录），
      改成从 **exe 所在目录**和**当前工作目录**两处找 —— 也算一种「把译文源
      放在 exe 旁边就能离线用」的便利。
    """
    if getattr(sys, "frozen", False):
        bases = [Path(sys.executable).resolve().parent, Path.cwd()]
    else:
        bases = [Path(__file__).resolve().parent.parents[1], Path.cwd()]
    cands: list[str] = []
    for b in bases:
        cands += [str(b / "python-docs-zh-cn-3.14"), str(b / "python-docs-zh-cn")]
    cands.append(str(Path.home() / "python-docs-zh-cn"))
    return _first_existing(*cands)


def _guess_base_dir() -> str:
    """默认路径基准目录：<基准>/Python <版本> PDF 文档 就是构建根目录。

    优先用本机已有的那套目录（例如 …/编程软件/Python 文档），都没有就退到
    用户主目录下的 PythonDocsPDF。
    """
    home = Path.home()
    for cand in (Path(r"C:\Users\zb137\Desktop\编程软件\Python 文档"),
                 home / "Desktop" / "Python 文档",
                 home / "Python 文档"):
        if cand.is_dir():
            return str(cand)
    return str(home / "PythonDocsPDF")


#: 支持的版本 —— 两个仓库（cpython / python-docs-zh-cn）都有同名的 3.x 分支。
#: ★ 册数**每个版本都不一样**（3.10 27 册 / 3.11 29 / 3.12 32 / 3.13 37 / 3.14 38 /
#:   3.15 39），来源是各分支 `Doc/conf.py` 的 `latex_documents` 加上
#:   `Doc/howto/*.rst` 的文件数；`--tool volumes --verify` 会联网对着官方复核。
#: ★ 3.10 **已停止支持**（2026-10-31 EOL），从清单里移除：不再构建、不再列册数，
#:   它的产物已归档到仓库的 `old` 分支（`old/v3.10.22/`），release 已删。
#:   想重建 3.10（比如修某个错字）：把 "3.10" 加回这个列表 + 手动跑一次即可，
#:   代码里对它的支持（`distributing` 册、sphinx 3.4.3 依赖、gettext_compact 补丁）
#:   全都还在，没有删。
#: ★ 3.16 **暂时不收录**：上游还没切出 `3.16` 分支（只有 main），中文译文也没有对应
#:   分支，现在收进来只会编出「英文 + 版本号不确定」的东西。等分支出现再加一行即可
#:   （同时给 volumes.json 里 3.16 新增的册子补 min 区间）。
KNOWN_VERSIONS = ["3.11", "3.12", "3.13", "3.14", "3.15"]

#: ★ 还没切出独立分支的版本 → 借哪个分支（例如将来 3.16 尚未建分支时填 `{"3.16": "main"}`）。
#:   目前六个版本都有自己的分支，所以是空的；机制留着，加版本时不用改 `Config.branch`。
BRANCH_ALIAS: dict[str, str] = {}

#: ★ 每个版本用哪个解释器 —— 三个分支各用各的，互不干扰（避免共用 venv / 依赖）。
#: 界面上可以改（① 版本与目录 → 每个版本一行），改完存进 config.json 的
#: `version_pythons`；这里只是默认值。
DEFAULT_VERSION_PYTHONS: dict[str, str] = {
    "3.13": r"D:\软件\Python313\python.exe",
    "3.14": r"D:\软件\Python314\python.exe",
    "3.15": r"D:\软件\Python315\python.exe",
}

#: 基准目录默认值。构建根目录 = `<基准>/Python <完整版本> PDF 文档 <日期>`，
#: 输出目录默认同构建根目录 —— 三者都落在这一处（要求如此，也方便整体搬走）。
DEFAULT_BASE_DIR = r"C:\Users\zb137\Desktop\编程软件\Python 文档"

#: 解释器版本号缓存：{(解释器路径, mtime): "3.13.16"}
_FULLVER_CACHE: dict[tuple[str, float], str] = {}


def today_tag() -> str:
    """默认的日期标签，形如 `20261017`（写进文件夹名与合并册名）。"""
    return time.strftime("%Y%m%d")


def interpreter_version(py: str) -> str:
    """跑一下那个解释器，拿**完整版本号**（3.13.16 / 3.14.8 / 3.15.0）。

    ★ 为什么不写死：文件夹名要「详细版本号」，而 3.13 分支的文档实际是 3.13.16。
      写死一张表，上游一发版就过期；直接问解释器最准，而且带 mtime 缓存，
      一次运行只问 3 次（每次约 40 ms）。拿不到就返回空串，由调用方兜底。
    """
    p = (py or "").strip()
    if not p or not Path(p).is_file():
        return ""
    try:
        key = (p, Path(p).stat().st_mtime)
    except OSError:
        key = (p, 0.0)
    hit = _FULLVER_CACHE.get(key)
    if hit is not None:
        return hit
    ver = ""
    try:
        r = subprocess.run(
            [p, "-c", "import sys;print('%d.%d.%d' % sys.version_info[:3])"],
            capture_output=True, text=True, timeout=60,
            creationflags=CREATE_NO_WINDOW)
        if r.returncode == 0:
            m = re.search(r"\b(\d+\.\d+\.\d+)\b", r.stdout or "")
            if m:
                ver = m.group(1)
    except (OSError, subprocess.SubprocessError):
        ver = ""
    if ver:
        _FULLVER_CACHE[key] = ver
    return ver


#: 官方中文文档站的标题口径 —— 文件名/文件夹名/Release 标题里的**完整版本号认它**，
#: 而不是「这台机器上碰巧装到的解释器」。来源是各版本首页 h1：
#:   https://docs.python.org/zh-cn/3.10/  → `Python 3.10.22 文档`
#: 缓存文件 `version-titles.json` 由 `--tool titles` 生成（见本文件下半部分）。
VERSION_TITLES_FILENAME = 'version-titles.json'
_OFFICIAL_TITLES: dict[str, dict[str, str]] | None = None


def version_titles_candidates() -> list[Path]:
    """`version-titles.json` 的查找顺序 —— 与 `volumes.json` 用同一套目录。"""
    out: list[Path] = []
    env = os.environ.get('PDFBUILDER_TITLES', '').strip()
    if env:
        out.append(Path(env))
    for p in volumes_json_candidates():
        out.append(p.with_name(VERSION_TITLES_FILENAME))
    return out


def official_titles(*, refresh: bool = False) -> dict[str, dict[str, str]]:
    """读 `version-titles.json` → `{'3.10': {'full': '3.10.22', 'title': 'Python 3.10.22 文档'}}`。

    ★ 读不到/读坏一律返回空字典（= 退回问解释器），绝不因为一个缓存文件让程序起不来。
    """
    global _OFFICIAL_TITLES
    if _OFFICIAL_TITLES is not None and not refresh:
        return _OFFICIAL_TITLES
    data: dict[str, dict[str, str]] = {}
    for p in version_titles_candidates():
        if not p.is_file():
            continue
        try:
            raw = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        for k, v in (raw.get('titles') or {}).items():
            if not isinstance(v, dict):
                continue
            full = str(v.get('full') or '').strip()
            if full:
                data[str(k).strip()] = {'full': full, 'title': str(v.get('title') or '').strip()}
        break
    _OFFICIAL_TITLES = data
    return data


def official_full_version(short: str) -> str:
    """官方文档站标题里的完整版本号；没有/不匹配就返回空串。"""
    short = (short or '').strip()
    ent = official_titles().get(short) or {}
    full = str(ent.get('full') or '')
    return full if short and full.startswith(short + '.') else ''


def official_title(short: str) -> str:
    """官方文档站标题原文（`Python 3.10.22 文档`）；没有就返回空串。"""
    return str((official_titles().get((short or '').strip()) or {}).get('title') or '')


def resolve_full_version(short: str, py: str = "") -> str:
    """`3.13` → `3.13.18`。

    ★ 优先级（为什么是这个顺序）：
      1. `version-titles.json` —— **官方文档站 h1 的版本号**。用户点开
         `docs.python.org/zh-cn/3.13/` 看到的就是 3.13.18，下载到的东西也该叫这个。
         CI 上 `setup-python` 给的补丁版可能落后于文档站，跟着解释器走就会出现
         「内容是新分支、文件名是老补丁版」的错位；本地换台机器也会变。
      2. 问解释器 —— 本地手动跑、又没有缓存文件时最准。
      3. 本进程 / `.0` 兜底。

    **只认同 major.minor 的结果**，宁可退到 `.0` 也不张冠李戴。
    """
    short = (short or "").strip() or "3.14"
    off = official_full_version(short)
    if off:
        return off
    for cand in (py, DEFAULT_VERSION_PYTHONS.get(short, "")):
        v = interpreter_version(cand)
        if v.startswith(short + "."):
            return v
    if "%d.%d" % sys.version_info[:2] == short:
        return "%d.%d.%d" % sys.version_info[:3]
    return short + ".0"


def _ver_key(v: str) -> tuple:
    """版本号排序键：`3.13` < `3.14` < `3.15`；认不出的排最后。"""
    try:
        return tuple(int(x) for x in str(v).strip().split("."))
    except ValueError:
        return (999,)


#: 老版本的默认代理（写死的那一个）。用户配置里如果还是它，就当「自动」处理。
LEGACY_GH = "https://ghfast.top/https://github.com"

#: 内置的 GitHub 加速镜像，**按顺序自动回退**。`{repo}` = `owner/name`。
#: ★★ 为什么必须有一串（2026-10-31 实测）★★
#:   单个代理会「有时通、有时不通」：`ghfast.top` 的 `git ls-remote` 可能通过，
#:   但真 clone 报 `Could not connect to server after 210 ms`，三个版本一起卡死在
#:   步骤 1。所以按可用性排好序，前一个失败就自动换下一个，并在日志里写清用的是
#:   哪个（用户下次可以直接把它填进「GitHub 代理」）。
#: 直连放最后：本机多数时候直连 github.com 不通，但换个网络可能反而最快。
GH_MIRRORS: list[tuple[str, str]] = [
    ("ghproxy.net",    "https://ghproxy.net/https://github.com/{repo}"),
    ("gh-proxy.com",   "https://gh-proxy.com/https://github.com/{repo}"),
    ("ghfast.top",     "https://ghfast.top/https://github.com/{repo}"),
    ("xget",           "https://xget.xi-xu.me/gh/{repo}"),
    ("githubproxy.cc", "https://githubproxy.cc/https://github.com/{repo}"),
    ("gitclone",       "https://gitclone.com/github.com/{repo}"),
    ("直连",           "https://github.com/{repo}"),
]


@dataclass
class Config:
    # ── 版本（★ 决定两个仓库的分支，默认 3.14）────────────────────────────
    version: str = "3.14"

    # ── 多版本（★ 本文件新增）──────────────────────────────────────────────
    #: 勾选的版本；跑的时候**一个版本 = 一个子进程**。空 = 退回 `version` 那一个。
    versions: list[str] = field(default_factory=lambda: ["3.14"])
    #: 每个版本各用哪个解释器（版本 → python.exe 绝对路径）。
    version_pythons: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_VERSION_PYTHONS))
    #: 日期标签，写进文件夹名与合并册名（如 20261017）。留空 = 今天。
    #: ★ 它会存进 config.json：**续跑同一轮构建时保持不变**，否则第二天换个文件夹
    #:   就等于重新克隆、重装依赖。想新开一轮，界面上点「今天」或手改。
    date_tag: str = field(default_factory=today_tag)

    # ── 路径 ──────────────────────────────────────────────────────────────
    base_dir: str = field(default_factory=_guess_base_dir)
    """路径基准目录：root / outdir 留空时按
    "<基准>/Python <完整版本> PDF 文档 <日期>" 推算。"""

    root: str = ""                            # 构建根目录（空 = 按版本自动推算）
    outdir: str = ""                          # 最终 PDF 输出目录（空 = 同构建根目录）
    python: str = field(default_factory=_guess_python)   # 建 venv 用的解释器
    texlive_bin: str = field(default_factory=_guess_texlive)  # xelatex/latexmk 所在目录
    zh_src: str = ""                          # 本地翻译源（★ 留空 = 联网下载，推荐）
    tools_dir: str = ""                       # 本项目 tools/（默认 <gui>/../tools）
    venv: str = ""                            # 构建用 venv（留空 = 自动探测）

    # ── 链接（★ 可改：直连不通就换代理/镜像）───────────────────────────────
    version_branch: str = ""                  # 分支覆盖（留空 = 用版本号，如 3.14）
    #: GitHub 代理前缀。**留空 = 自动依次尝试内置镜像表**（见 `GH_MIRRORS`：
    #: ghproxy.net → gh-proxy.com → ghfast.top → xget → githubproxy.cc → gitclone
    #: → 直连）。填了就先用它，失败仍会自动回退到内置表 —— 单一代理随时可能挂。
    gh: str = ""
    cpython_url: str = ""                     # 空 = 自动（<镜像>/python/cpython.git）
    zh_url: str = ""                          # 空 = 自动（<镜像>/python/python-docs-zh-cn.git）
    pip_index: str = "https://pypi.tuna.tsinghua.edu.cn/simple"
    #: 补充译文的**联网更新地址**（可选）。程序已不再内置正文译文，正文一律
    #: 来自上游 .po；这个地址只用来给个别页面**额外打补丁**。三种形态都认：
    #:   * 以 `.json` 结尾的 http(s) 地址 → 清单文件
    #:     `{"builtins/index.po": "<文本>", …}`
    #:   * 其它 http(s) 地址 → 当作目录前缀，按相对路径逐个 GET
    #:   * `file://…` 或**本机目录路径** → 直接读该目录里的同名文件
    #: ★ 每次运行（步骤 3）都会实时抓一次并整份重写到 `<root>/i18n-extra/`；
    #:   留空 = 不打补丁（正常状态，不影响构建）。
    i18n_extra_url: str = ""

    # ── 其它 ──────────────────────────────────────────────────────────────
    lang: str = "zh_CN"
    # ★ 注意：`jobs` 的**唯一定义**在下面的「步骤 7」分区（int）。
    #   历史上这里曾有第二个 `jobs: str = "auto"`，与下面重复；dataclass 里
    #   后出现的会覆盖前面的默认值，于是 `-j` 拿到的是 int 0，
    #   直接 `TypeError: expected str, bytes or os.PathLike object, not int`。
    #   要传给 sphinx -j 请用 `cfg.sphinx_jobs()`（见 helper）。
    from_step: int = 0                        # 起始步骤行号
    only_steps: str = ""                      # 形如 "0,1" —— 只跑这些步骤（行号）

    # ── 开关 ──────────────────────────────────────────────────────────────
    download_sources: bool = True             # ★ 默认从网站实时克隆/更新源码与翻译源
    refresh_sources: bool = True              # 已在本地也要 fetch + reset 到最新
    skip_clone_if_exists: bool = True         # 步骤 1：Doc/conf.py 已存在就跳过克隆
    skip_pip_if_ready: bool = True            # 步骤 4：依赖已就绪就跳过 pip（省 10 分钟）
    keep_build_dir: bool = False              # 步骤 4：保留已有 build/（增量构建）
    build_html: bool = False                  # 步骤 5：HTML 只是验证主题，可关
    localize_titles: bool = True              # 步骤 6b
    fix_index: bool = True                    # 步骤 7b：索引自检（不通过才重排）
    prune_extra_pdf: bool = True              # 步骤 8：丢掉插图 PDF，只留 38 册
    gen_report: bool = True                   # 步骤 8：生成 验收报告.md
    # ★ 本版默认**开**：成品交付里那本 `Python 3.13.16 文档 20261017.pdf`
    #   就是这一步产出的（命名规则见 Config.default_merge_name）。单版本版默认是关的。
    merge_pdf: bool = True                    # 步骤 9：把 38 册合并成一册（完整书签）
    merge_name: str = ""                      # 步骤 9：合并册文件名（留空 = 自动）
    clean_mode: str = "none"                  # 步骤 10：none / build / all
    #: 步骤 7：只编这几册（逗号分隔的 .tex 名，如 `reference,library`；留空 = 全部）。
    #: 为什么需要：补一条稀疏路径 / 改一个 .rst 往往只影响一两册，而全编 39 册
    #: 要四十分钟。步骤 8 只按同名覆盖，其余册的成品保持原样，不会被打断。
    books: str = ""
    #: 步骤 7：同时编译几册（0 = 自动）。单册 latexmk 是 CPU 密集型 ——
    #: xelatex 要跑 3 遍外加一次 makeindex，所以并行几乎线性提速（18 核机器
    #: 实测从 40 分钟降到个位数分钟）。上限卡在内存：像 library 那样 2358 页的
    #: 大册，xelatex 峰值能到 1 GB 以上，开太多会开始换页、反而变慢。
    #: 类型说明：CLI 的 `--jobs N` 写 int；GUI／配置里是文本框，存的是字符串
    #: （`"auto"` / `"4"`）。取用时**不要直接塞给 subprocess** —— 一律走
    #: `_resolve_jobs()`（给线程池，要 int）或 `sphinx_jobs()`（给 sphinx `-j`，要 str）。
    jobs: int | str = 0
    verbose_log: bool = False                 # 界面显示完整输出（不止关键行）
    open_outdir_when_done: bool = False

    # ---------------------------------------------------------------- helpers
    @property
    def branch(self) -> str:
        """两个仓库用的分支名：默认就是版本号（3.10…3.15）。

        ★ 还没切出分支的版本走 `BRANCH_ALIAS`（如将来 `{"3.16": "main"}`）；界面上的
          「分支覆盖」永远优先，所以哪个版本切出来了都不用改代码。
        """
        explicit = (self.version_branch or "").strip()
        if explicit:
            return explicit
        ver = (self.version or "").strip() or "3.14"
        return BRANCH_ALIAS.get(ver, ver)

    # ------------------------------------------------------- 版本 / 命名
    def date_tag_eff(self) -> str:
        """实际用的日期标签（留空 = 今天）。"""
        return (self.date_tag or "").strip() or today_tag()

    def full_version(self) -> str:
        """完整版本号：`3.13` → `3.13.18`。

        ★ 口径是**官方文档站标题**（`docs.python.org/zh-cn/3.13/` 的 h1 写着
          `Python 3.13.18 文档`），存在 `sphinx-pdf/version-titles.json` 里；
          没有缓存时才去问解释器（`python_for(版本)`，不是兜底字段 `self.python`，
          后者可能指向别的小版本）。见 `resolve_full_version()` 的优先级说明。
        """
        return resolve_full_version(self.version, self.python_for(self.version))

    def python_for(self, ver: str) -> str:
        """某个版本该用的解释器：版本表 > 默认表 > 全局 python。"""
        return ((self.version_pythons or {}).get(ver, "").strip()
                or DEFAULT_VERSION_PYTHONS.get(ver, "")
                or (self.python or "").strip())

    def selected_versions(self) -> list[str]:
        """勾选的版本，按 3.13 → 3.15 升序；一个都没勾就退回 `version`。"""
        got = [v for v in (self.versions or []) if (v or "").strip()]
        got = sorted({v.strip() for v in got}, key=_ver_key)
        return got or [(self.version or "3.14").strip()]

    def for_version(self, ver: str) -> "Config":
        """派生出一份「只管某个版本」的配置（多版本并行时每个子进程用一份）。

        ★ root / outdir 一律按「基准目录 + 完整版本 + 日期」重新算，**不沿用**
          手动填的那个 —— 否则三个版本会同时往一个目录里写，互相覆盖产物。
        """
        c = Config(**asdict(self))
        c.version = ver
        c.versions = [ver]
        c.python = self.python_for(ver)
        c.root = ""
        c.outdir = ""
        c.merge_name = ""          # 留空 → 用 default_merge_name()（带完整版本号+日期）
        return c

    def default_merge_name(self) -> str:
        """合并册默认文件名：`Python 3.13.16 文档 20261017.pdf`。"""
        return f"Python {self.full_version()} 文档 {self.date_tag_eff()}.pdf"

    @property
    def default_root(self) -> str:
        base = (self.base_dir or "").strip() or _guess_base_dir()
        return str(Path(base) / f"Python {self.full_version()} PDF 文档 "
                                f"{self.date_tag_eff()}")

    def resolved_root(self) -> str:
        return (self.root or "").strip() or self.default_root

    def url_cpython(self) -> str:
        return self.git_urls("python/cpython", self.cpython_url)[0][1]

    def url_zh(self) -> str:
        return self.git_urls("python/python-docs-zh-cn", self.zh_url)[0][1]

    def git_urls(self, repo: str, explicit: str = "") -> list[tuple[str, str]]:
        """给出「先指定、再依次回退内置镜像」的 (镜像名, 完整 URL) 列表。

        ★★ 2026-10-31 加：单一代理会突然挂 ★★
          实测 `ghfast.top` 有时 `git ls-remote` 通、真 `git clone` 却报
          `Could not connect to server after 210 ms`（三个版本同时卡在步骤 1）。
          所以不能只写一个前缀：把社区里还能用的几个都列上，**失败自动换下一个**，
          并且记住这次成功的那个，后面（翻译仓库）优先用它。

        顺序约定：显式指定（`CPython 仓库地址` / `翻译仓库地址`）> 自定义代理前缀
                  > 内置镜像表（见 `GH_MIRRORS`）。
        """
        seen: set[str] = set()
        out: list[tuple[str, str]] = []

        def add(name: str, url: str) -> None:
            url = (url or "").strip()
            if url and url not in seen:
                seen.add(url)
                out.append((name, url))

        if explicit.strip():
            add("你指定的地址", explicit.strip())
        gh = (self.gh or "").strip().rstrip("/")
        # 老默认值不算「自定义」——它已经在内置表里了，别重复试。
        if gh and gh != LEGACY_GH:
            add("自定义代理", f"{gh}/{repo}")
        for name, tpl in GH_MIRRORS:
            add(name, tpl.format(repo=repo))
        return out

    def resolved_outdir(self) -> str:
        # 默认与构建根目录同一处：脚本本来就把最终 PDF 复制/改名到根目录
        if self.outdir.strip():
            return self.outdir.strip()
        return self.resolved_root()

    def resolved_tools(self) -> str:
        if self.tools_dir.strip():
            return self.tools_dir.strip()
        # 打包后(PyInstaller单文件)：检查临时解压目录
        if getattr(sys, 'frozen', False):
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass:
                p = Path(meipass) / "tools"
                if p.is_dir():
                    return str(p)
        # 开发环境(直接python运行)：用原来的相对路径
        if getattr(sys, "frozen", False):
            # exe 旁边若有 tools/（用户自己放的转发器，给 bash 用）就用它；
            # 否则这个字段只剩「显示」用途 —— 工具已全部内联。
            return str(app_dir() / "tools")
        return str(Path(__file__).resolve().parent.parent / "tools")

    def sphinx_jobs(self) -> str:
        """规范化成 sphinx `-j` 想要的**字符串**。

        这个字段有两个来源：CLI `--jobs N` 写进来的是 int，GUI 文本框写进来的是
        字符串（`"auto"` / `"4"`）。直接把它塞进 subprocess 参数列表时，int 会触发
        `TypeError: expected str, bytes or os.PathLike object, not int`
        （步骤 6 实测踩过，见 Config 里 `jobs` 的注释）。

        返回：正数 → `"4"` 这样的字符串；0 / 空 / 非数字 / `"auto"` → `"auto"`。
        """
        try:
            n = int(getattr(self, "jobs", 0) or 0)
        except (TypeError, ValueError):
            return "auto"
        return str(n) if n > 0 else "auto"

    def only_set(self) -> set[int] | None:
        """把 `only_steps` 文本解析成**行号**集合（None = 全部）。

        ★ 解析顺序：**先按步骤号**（STEPS 第 2 列，也就是界面上显示的编号
          `6b` / `7` / `9`），**再退回行号**（STEPS 第 1 列）。

        为什么要这个顺序：步骤号与行号**本来就不一致** —— 步骤 6b 的行号是 7、
        步骤 7 的行号是 8、步骤 9 的行号是 11。人写 `--only 7` 时想的是「步骤 7
        （编译 PDF）」，若把 7 当行号，跑到的却是步骤 6b（标题中文化）。
        实测踩过：`--only 7 --books builtins` 实际只重跑了 6b，白等一场。

        退回行号是为了兼容既有习惯：`--only 11 --merge`（11 没有对应的步骤号，
        就是行号 11 = 步骤 9 合并），以及 `--only 12`（行号 12 = 步骤 10 清理）。

        ★ 历史坑：早先只写 `if tok.isdigit()`，`6b` 这种会被**静默丢掉** ——
          命令看着跑完了、日志全绿，但要跑的那一步压根没执行。
        """
        raw = (self.only_steps or "").strip()
        if not raw:
            return None
        by_label = {label.lower(): row for row, label, _t, _d in STEPS}
        valid = {row for row, *_ in STEPS}
        out: set[int] = set()
        bad: list[str] = []
        for tok in re.split(r"[,\s]+", raw):
            t = tok.strip().lower()
            if not t:
                continue
            if t in by_label:                     # 步骤号：`7`→行 8、`6b`→行 7
                out.add(by_label[t])
            elif t.isdigit() and int(t) in valid:  # 退路：行号（`11`→行 11）
                out.add(int(t))
            else:
                bad.append(tok)
        if bad:
            known = '、'.join(f"{label}=行{row}" for row, label, _t, _d in STEPS)
            raise Fail(f"--only 里有认不出的步骤：{'、'.join(bad)}\n"
                       f"  步骤号与行号的对照：{known}")
        return out or None


def rename_map(version: str) -> dict[str, str]:
    """【已废弃】分册名映射。

    ★ 2026-09-26：映射已收敛到 `name_map` **唯一一处**，重命名改由 `rnpdf_main`
      （原 `tools/rename-pdf.py`）执行。2026-10-04 更进一步：两者都被内联进本文件
      第六节，于是「同一份逻辑存在两处」的可能彻底消失。
      这里保留一个空实现只是为了不让旧的外部脚本 import 时报 AttributeError；
      **不要再往这里加映射** —— 加了就又是一份要手工同步的副本。
    """
    return {}


CONFIG_NAME = "config-multi.json"
"""★ 刻意与单版本版的 `config.json` 分开。

两个 exe 就摆在同一个 `dist/` 目录里。若共用一份配置，改这个的版本/目录会
把另一个的也改掉（实测过一次：单版本版被带着跑到了另一个版本的目录）。
"""


def config_path() -> Path:
    """配置文件位置。★ 用 `app_dir()` 而不是 `__file__` —— 见其 docstring。"""
    return app_dir() / CONFIG_NAME


def load_config(explicit: str | None = None) -> Config:
    """读配置。**读不了就报出来**，别再静默全用默认值。

    ★ 原来的写法是 `except Exception: pass` —— 一个手改坏的 `config.json`
      （多一个逗号、Windows 路径写成 `"C:\\x"` 却漏了转义）会让**整份配置被
      无声无息地丢掉**，程序照跑、跑的是默认值：构建根目录、输出目录、
      版本全变了，日志里一个字都没有。这正是本项目一直在治的那类静默失败。
      现在：一句能照做的警告（走 stderr / 界面弹一次），其余仍按默认值继续。
    """
    p = Path(explicit) if explicit else config_path()
    cfg = Config()
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:                       # noqa: BLE001
            msg = (f"[警告] 配置文件读不了，本次全部按默认值跑：{p}\n"
                   f"        {type(e).__name__}: {e}\n"
                   f"        （常见原因：JSON 里 Windows 路径的反斜杠要写成 "
                   f"\\\\，或者多了个逗号）")
            print(msg, file=sys.stderr)
            return cfg
        for k, v in (data or {}).items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        # ★ 老配置里的代理前缀还是写死的 ghfast.top —— 现在那只是「内置镜像之一」，
        #   等于自动模式。把它归一化掉，界面上就显示「留空 = 自动」，
        #   否则用户会以为程序还盯着那一个（它挂了就以为整轮必挂）。
        if (cfg.gh or "").strip().rstrip("/") == LEGACY_GH.rstrip("/"):
            cfg.gh = ""
    return cfg


def save_config(cfg: Config, explicit: str | None = None) -> Path:
    p = Path(explicit) if explicit else config_path()
    p.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return p


# =============================================================================
# 四、流程引擎（与 Qt 完全无关，可单独命令行跑）
# =============================================================================

class _TeeReporter:
    """把 reporter 的消息**同时**落进日志文件。

    ★ 为什么需要：`gui-build.log` 是事后排错的唯一凭据，但界面 reporter 的
      `log()` 只把文字发信号给界面，**不写文件**。于是失败时日志里只剩原始
      命令行输出，最关键的那句「步骤 1 失败：…」反而没记下来 —— 事后翻日志
      根本看不出为什么停的，只能靠当时盯着界面。

    只补记 `cmd` / `raw` 之外的消息：这两级 `Pipeline.run()` 已经自己写过，
    再记一遍会把每条命令和每一行输出都翻倍。
    """

    #: 需要加级别标签的（err / warn / ok）；info / meta 是叙述性文字，加了反而吵
    _TAGGED = ("err", "warn", "ok")

    def __init__(self, inner, pipe: "Pipeline") -> None:
        self._inner = inner
        self._pipe = pipe

    def __getattr__(self, name):          # sub / check_cancel 等直接透传
        return getattr(self._inner, name)

    def log(self, text: str, level: str = "info") -> None:
        self._inner.log(text, level)
        if level in ("cmd", "raw"):
            return
        for ln in str(text).splitlines() or [""]:
            if level in self._TAGGED and not ln.lstrip().startswith("["):
                ln = f"[{level}] {ln}"
            self._pipe._file(ln)

    def step_end(self, i: int, ok: bool, summary: str, secs: float) -> None:
        self._inner.step_end(i, ok, summary, secs)
        _row, label, title, _sub = STEP_BY_ROW.get(i, (i, str(i), "", ""))
        self._pipe._file(f"----- 步骤 {label} {title}："
                         f"{'完成' if ok else '失败'}（{human_dur(secs)}）{summary}")
        self._pipe._flush_files()


class Pipeline:
    """把 build-sphinx-pdf.sh 的每一步搬到 Python。

    reporter 需要实现：log / step_begin / step_end / sub / check_cancel。
    """

    def __init__(self, cfg: Config, rep) -> None:
        self.cfg = cfg
        # 包一层：让界面上的每一句提示（尤其是失败原因）也进 gui-build.log
        self.rep = _TeeReporter(rep, self)

        self.root = Path(cfg.resolved_root()).expanduser()
        self.outdir = Path(cfg.resolved_outdir()).expanduser()
        self.tools = Path(cfg.resolved_tools()).expanduser()

        # ★ 这两行**必须在 `_make_env()` 之前**：`_make_env()` 里会把找到的
        #   cairo 目录写进 `self.cairo_dir`，放在后面等于又清成空串（踩过）。
        #: 找到的 cairo 运行库目录（空 = 系统本来就能加载，或没找到）
        self.cairo_dir = ""
        #: 本次运行里**已经验证可用**的 GitHub 镜像名（`git_clone` 记的）。
        #: 克隆 CPython 成功后，克隆翻译仓库会优先用它，省得再等一次超时。
        self._gh_good = ""
        #: `import cairosvg` 的探测结果缓存：(能不能用, 失败原因)
        self._cairo_state: tuple[bool, str] | None = None
        self.env = self._make_env()
        self.python = cfg.python                    # 建 venv 用
        self.vp: Path | None = None                 # venv 里的 python
        self.doc: Path | None = None                # <root>/cpython/Doc
        self.latex: Path | None = None              # <root>/cpython/Doc/build/latex
        self.zh_src: Path | None = None

        self._log_fp = None
        self._sec_fp = None
        self._sec_name = ""
        self._proc: subprocess.Popen | None = None
        #: ★ 并发编译（步骤 7 用线程池）时同时在跑的子进程 —— `stop()` 要全杀掉，
        #:   只盯着 `_proc` 会留下几个孤儿 xelatex 继续吃 CPU。
        self._procs: set[subprocess.Popen] = set()
        #: ★ 保护日志句柄与上面那个集合：并发时多个工作线程同时写 gui-build.log /
        #:   改 _procs，不加锁会写出半行、或让集合在迭代中被改。
        self._io_lock = threading.RLock()
        self._cur_row: int | None = None            # 当前步骤行号（供 run() 上报子进度）

    # ---------------------------------------------------------------- 环境
    def _make_env(self) -> dict[str, str]:
        env = dict(os.environ)
        # ★★ 剥掉 PyInstaller 引导层塞进环境的内部变量（_MEIPASS2 /
        #    _PYI_ARCHIVE_FILE / _PYI_APPLICATION_HOME_DIR / _PYI_PARENT_PROCESS_LEVEL
        #    等，onefile 父进程留给"子 exe"用的）。这些变量对普通子进程无害，但
        #    子进程若再起一个 onefile exe，其引导层会走「挂接父进程归档」的启动
        #    路径 —— 2026-10-28 实测在该路径上嵌入解释器初始化失败
        #    （Fatal Python error: Failed to import encodings module），并弹
        #    **模态**错误框把 latexmk 和整个构建卡死。这里一律剥掉，让每个
        #    onefile 子进程都走正常的独立解压。（本程序自己的 makeindex-fix.py
        #    已改为自包含脚本、不再起 exe —— 这是第二道防线。）
        for k in [k for k in env if k == "_MEIPASS2" or k.startswith("_PYI")]:
            env.pop(k, None)
        parts: list[str] = []
        tb = self.cfg.texlive_bin.strip()
        if tb:
            # ★ 脚本里的 `export PATH="/f/texlive/2025/bin/windows:$PATH"`。
            #   注意：编 PDF 时 xelatex/latexmk/makeindex/pdfinfo/pdffonts 都靠它。
            parts.append(tb)
            env["TEXLIVE_BIN"] = tb
        # ★ 步骤 7 里 latexmk 要按名字调用 `python makeindex-fix.py`：
        #   把 venv 的 Scripts 目录塞进 PATH，保证 cmd 里 `python` 一定找得到。
        #   （换成写全路径不行：venv 路径含中文，latexmk 的 -e 参数按 UTF-8 解析会炸。）
        vpdir = self._venv_scripts_dir()
        if vpdir:
            parts.append(str(vpdir))
        # ★ cairo 运行库（cairocffi / CairoSVG 需要，pip 不提供）：找到就加进
        #   **子进程** PATH 的最前面。为什么必须做、为什么不改系统 PATH：
        #   见 `find_cairo_dir()` 的长注释。空串 = 系统本来就有 / 没找到。
        self.cairo_dir = find_cairo_dir([str(vpdir)] if vpdir else None)
        if self.cairo_dir:
            parts.append(self.cairo_dir)
        if parts:
            env["PATH"] = os.pathsep.join(parts) + os.pathsep + env.get("PATH", "")
        env["LATEXOPTS"] = "-interaction=nonstopmode"   # ★ 不加会在批处理里等 stdin 挂死
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        # ★ 关掉子进程的彩色输出。Sphinx 8 在 Windows 上**无条件着色**（不看 isatty，
        #   见 sphinx/_cli/util/colour.py），管道里也吐 `\x1b[01m…\x1b[39;49;00m` ——
        #   界面日志会变成一片 `[2K[01mreading sources...` 乱码。它认 `NO_COLOR`
        #   （任意值即生效），顺手也让 pip / 其它工具安静下来。
        #   注意这里**故意覆盖**外部环境：本程序所有子进程的输出都要进日志，
        #   日志里出现转义序列没有任何好处。（`strip_ansi()` 是第二道防线。）
        env["NO_COLOR"] = "1"
        # ★★ 坑：Windows 版 perl 一看到 LC_ALL / LANG 是非 C 的 locale，
        #   就把文件名按那个编码处理，而 Windows 的文件 API 走 ANSI 代码页 ——
        #   于是**凡是路径里带中文的文件全都打不开**（本机路径含「Python 文档」）：
        #     Latexmk: I cannot read the rc-file 'latexmkrc'
        #     Cannot write file 'whatsnew.aux'
        #     runscript.tlu:933: ...\tlperl\bin\perl.exe: No such file or directory
        #   后果是 latexmk 退出码 12、整册不出 PDF，而**报错完全不提编码**。
        #   本机实测（`latexmk -v` 里 "cannot read the rc-file" 出现次数）：
        #     LC_ALL=C.UTF-8 → 1   LC_ALL=zh_CN.GBK → 1   LC_ALL=C → 0   清空 → 0
        #   也就是说 git-bash 里常见的 LC_ALL=C.UTF-8（甚至 GBK）都会中招，
        #   而用户从资源管理器双击启动时没有这些变量 —— 同一份配置、两种结局。
        #   Python 侧不受影响（上面两个 PYTHON* 已经把编码钉死 UTF-8），
        #   所以直接清掉，回到「双击启动」那套已验证可用的环境。
        if IS_WIN:
            for k in ("LC_ALL", "LANG", "LC_CTYPE"):
                env.pop(k, None)
        # ★ 子进程 stdout 是管道（不是终端），Python 默认按 8 KB 块缓冲：
        #   sphinx 的进度行会攒够一块才吐出来 —— 表现为「界面日志几分钟不动，然后一次跳一大段」。
        #   加这个才能真正做到边跑边看（每篇文档一行进度）。
        env["PYTHONUNBUFFERED"] = "1"
        return env

    def _venv_scripts_dir(self) -> Path | None:
        """venv 的 Scripts（Windows）/ bin 目录，里面要有 python 可执行文件。"""
        cfg_venv = self.cfg.venv.strip()
        cands: list[Path] = []
        if cfg_venv:
            cands.append(Path(cfg_venv).expanduser())
        try:
            cands.append(Path(self.cfg.resolved_root()).expanduser() / P_VENV)
        except Exception:                                        # noqa: BLE001
            pass
        for v in cands:
            for sub in ("Scripts", "bin"):
                d = v / sub
                if (d / "python.exe").is_file() or (d / "python").is_file():
                    return d
        return None

    def _tool(self, name: str) -> str:
        """把裸工具名换成**配置里那个 TeX Live** 的绝对路径；找不到就原样返回。

        ★★ 为什么非做不可（2026-10-06 实测踩到，隐蔽度极高）：
          Windows 的 `CreateProcess` 找可执行文件用的是**父进程自己的 PATH**
          —— `subprocess(env=...)` 里那份 PATH **只对孙进程生效**
          （例如 latexmk 自己再去拉 xelatex）。实测：把 `env["PATH"]` 设成只含
          `F:\\texlive\\2025\\bin\\windows`，再 spawn `xelatex`，跑出来的仍是
          `C:\\tools\\TinyTeX\\...`；而「只存在于临时目录里」的 exe 名字直接
          FileNotFoundError。

          本机 PATH 里 `C:\\tools\\TinyTeX\\bin\\windows` 排在
          `F:\\texlive\\2025\\bin\\windows` **前面**，于是同一份 `self.env`：
            · 步骤 7 命令是 `latexmk` → 命中 TinyTeX 的 latexmk，
              但它拉起的 `xelatex` 读的是子进程环境（含 texlive_bin）→ 是 F: 的，
              所以**一直没暴露**；
            · 步骤 7b 命令是 `xelatex` → **直接命中 TinyTeX**，而 TinyTeX 没有
              `cmap.sty` → `! LaTeX Error: File 'cmap.sty' not found`、
              `No pages of output` → 重排白跑一趟。

          修法就是**别依赖 PATH**：凡是在 `texlive_bin` 里能找到的（xelatex /
          latexmk / makeindex / pdfinfo / pdffonts），一律换成绝对路径。
        """
        d = self.cfg.texlive_bin.strip()
        if d:
            for ext in (".exe", ""):
                p = Path(d) / (name + ext)
                if p.is_file():
                    return str(p)
        return name

    def which(self, name: str) -> str | None:
        """工具在哪 —— **优先配置里的 TeX Live**，与真正执行时看到的一致。"""
        d = self.cfg.texlive_bin.strip()
        if d:
            for ext in (".exe", ""):
                p = Path(d) / (name + ext)
                if p.is_file():
                    return str(p)
        return (shutil.which(name, path=self.env.get("PATH", ""))
                or shutil.which(name))

    # ---------------------------------------------------------------- 日志
    def _open_log(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            self._log_fp = (self.root / "gui-build.log").open(
                "w", encoding="utf-8", errors="replace")
        except OSError:
            self._log_fp = None

    def _section(self, name: str, mode: str = "a") -> None:
        """切换当前分节日志（文件名与 bash 脚本用的完全一致）。"""
        with self._io_lock:
            if self._sec_name == name and self._sec_fp:
                return
            if self._sec_fp:
                try:
                    self._sec_fp.close()
                except Exception:
                    pass
                self._sec_fp = None
            self._sec_name = ""
            if not name:
                return
            try:
                self._sec_fp = (self.root / name).open("w" if mode == "w" else "a",
                                                       encoding="utf-8", errors="replace")
                self._sec_name = name
            except OSError:
                self._sec_fp = None

    def _close_logs(self) -> None:
        for fp in (self._sec_fp, self._log_fp):
            try:
                if fp:
                    fp.close()
            except Exception:
                pass
        self._sec_fp = self._log_fp = None

    def _reopen_logs(self) -> None:
        """`_close_logs()` 之后按需重开 —— **只重开还在磁盘上的那些，且用 append**。

        ★★ 为什么不能直接再调一次 `_open_log()`（2026-10-06 修）：
          ① `_open_log()` 用的是 `"w"` —— 一重开就把前半段日志**截断**了；
          ② 步骤 10 会把日志**本身**当过程文件删掉。删掉的就不该再重开，
             否则根目录里又冒出一个空的 `gui-build.log`，与「只留成品 PDF」
             的承诺相违（`clean_mode=build` 不删日志时才需要接着写）。
        所以这里逐项 `exists()` 判断：在 → 以 append 打开；不在 → 保持 None
        （`_file()` 对 None 是安全的，会直接跳过）。
        """
        self._sec_fp = self._log_fp = None
        for name, attr in ((self._sec_name, "_sec_fp"),
                           ("gui-build.log", "_log_fp")):
            if not name:
                continue
            try:
                p = self.root / name
                setattr(self, attr,
                        p.open("a", encoding="utf-8", errors="replace")
                        if p.exists() else None)
            except OSError:
                setattr(self, attr, None)

    def _file(self, line: str) -> None:
        with self._io_lock:
            for fp in (self._sec_fp, self._log_fp):
                if fp:
                    try:
                        fp.write(line + "\n")
                    except Exception:
                        pass

    def _flush_files(self) -> None:
        with self._io_lock:
            for fp in (self._sec_fp, self._log_fp):
                if fp:
                    try:
                        fp.flush()
                    except Exception:
                        pass

    # ---------------------------------------------------------------- 执行
    def run(self, cmd: list[str], cwd: Path | None = None,
            section: str | None = None, capture: bool = False,
            quiet: bool = False, timeout: float | None = None):
        """跑一条命令，边跑边把输出写进日志文件（关键行同时送进界面）。

        - capture=True：返回 (退出码, 全部输出文本)；否则只返回退出码
        - quiet=True  ：不把输出送界面，也不报"退出码/用时"（取值用的小命令）

        完整输出**永远**写进 <root>/gui-build.log 和当前分节日志，
        所以界面过滤掉的那些行随时能回查 —— 与 bash 脚本把输出重定向到
        $ROOT/pdf-build.log 的做法一致。
        """
        if section:
            self._section(section)
        self.rep.check_cancel()
        # ★★ 先把工具名换成配置里那个 TeX Live 的绝对路径（见 `_tool` 的说明）。
        #   Windows 上 `env=` 里那份 PATH 对「本进程直接 spawn 的命令」**无效**，
        #   不换的话 xelatex / pdfinfo / pdffonts 都会落到 PATH 上第一个发行版
        #   （本机是 TinyTeX，缺 cmap.sty，步骤 7b 的重排因此全军覆没）。
        if cmd:
            cmd = [self._tool(cmd[0]), *cmd[1:]]
        self.rep.log(f"$ {cmdline(cmd)}", level="cmd")
        self._file(f"$ {cmdline(cmd)}")
        t0 = time.monotonic()
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(cwd) if cwd else None, env=self.env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                bufsize=1, creationflags=CREATE_NO_WINDOW,
                start_new_session=not IS_WIN)
        except OSError as e:
            raise Fail(f"无法启动命令 {cmd[0]}：{e}") from e

        self._proc = proc
        kept: list[str] = []
        n = 0
        # ★★ 长步骤心跳（2026-10-30 加）★★
        #   sphinx 读入阶段常常十几秒才吐一行，三个版本并行时用户看到的是
        #   「只有一个面板在动」—— 其实三个都在跑（doctrees 每分钟都有写入），
        #   只是另外两个的日志太安静。这里每 30 秒打一行心跳（带已用时长与
        #   最新百分比），任何版本卡死或退出都能一眼看出来。
        last_pct = [""]
        hb_stop = threading.Event()
        # ★ 阶段计时（2026-10-30 加）：把 sphinx 的「读入 / 写出」两段分别记时。
        #   用户问过「为什么 3.13 的步骤 6 只要 14 分钟，3.14/3.15 要 23 分钟」，
        #   而日志里只有总用时 —— 分不出来是读入慢还是写 LaTeX 慢。这里记：
        #     读入 = 第一条 "reading sources" 到最后一条
        #     写出 = 第一条 "writing output" 到最后一条
        #   结束后打一行，下次直接看这一行就有数（含篇数与 -j）。
        ph = {"read": [0.0, 0.0], "write": [0.0, 0.0], "docs": 0}

        def _heartbeat() -> None:
            tool_name = Path(cmd[0]).name if cmd else "命令"
            while not hb_stop.wait(30.0):
                tag = f"，最新进度 {last_pct[0]}" if last_pct[0] else ""
                try:
                    self.rep.log(f"… 仍在运行（{tool_name} 已用 "
                                 f"{human_dur(time.monotonic() - t0)}{tag}）",
                                 level="meta")
                except Exception:                        # noqa: BLE001
                    return

        hb = threading.Thread(target=_heartbeat, daemon=True, name="run-heartbeat")
        if not quiet:
            hb.start()
        # ★ 超时看门狗（2026-10-31 加）：镜像「半死不活」时 git clone 会挂几分钟
        #   都不返回。给了 timeout 就到点杀掉整个进程树，让调用方换下一个镜像。
        timed_out = [False]
        dog: threading.Timer | None = None
        if timeout and timeout > 0:
            def _on_timeout() -> None:
                timed_out[0] = True
                try:
                    kill_tree(proc.pid)
                except Exception:                        # noqa: BLE001
                    pass

            dog = threading.Timer(float(timeout), _on_timeout)
            dog.daemon = True
            dog.start()
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                # ★ 先剥 ANSI 再往任何地方送（日志文件、界面、进度条）：
                #   Sphinx 8 在 Windows 上管道里也着色（见 ANSI_ESC 的说明），
                #   不剥的话日志里全是 `[2K[01m` 之类的乱码。
                line = strip_ansi(raw.rstrip("\r\n"))
                self._file(line)
                if capture:
                    kept.append(line)
                # Sphinx 的进度行 → 直接喂给「当前步骤」进度条（HTML / LaTeX 两步）。
                # 这样 0/1 的哑进度条会变成真实的 0~100%，并能看到正在解析哪篇文档。
                m_prog = (SPHINX_PROG.search(line)
                          if self._cur_row in SPHINX_STEP_ROWS else None)
                if m_prog:
                    last_pct[0] = f"{m_prog.group(1)}%"
                    _now = time.monotonic()
                    if "reading sources" in line:
                        if not ph["read"][0]:
                            ph["read"][0] = _now
                        ph["read"][1] = _now
                        ph["docs"] += 1
                    elif "writing output" in line:
                        if not ph["write"][0]:
                            ph["write"][0] = _now
                        ph["write"][1] = _now
                    self.rep.sub(self._cur_row, int(m_prog.group(1)), 100,
                                 SPHINX_PROG.sub("", line).strip()[-32:])
                if not quiet and (self.cfg.verbose_log or m_prog
                                  or NOTABLE.search(line)):
                    self.rep.log(line, level="raw")
                n += 1
                if n % 500 == 0:
                    # 兜底：即使 stop() 没能杀掉进程树，也能在这里中断
                    self.rep.check_cancel()
            proc.wait()
        finally:
            if dog is not None:
                dog.cancel()
            hb_stop.set()
            self._proc = None
        self.rep.check_cancel()          # 命令被 kill 时，Cancelled 在这里抛出
        rc = proc.returncode
        if timed_out[0]:
            self.rep.log(f"  超时（{timeout:.0f}s 没跑完）已中止", level="warn")
            rc = rc or -9
        if not quiet and ph["read"][0]:
            rd = ph["read"][1] - ph["read"][0]
            wr = (ph["write"][1] - ph["write"][0]) if ph["write"][0] else 0.0
            self.rep.log(
                f"  读入 {human_dur(rd)}（{ph['docs']} 篇，-j {self.cfg.sphinx_jobs()}，"
                f"约 {ph['docs'] / max(rd, 1e-6) * 60:.0f} 篇/分）"
                + (f" · 写出 {human_dur(wr)}" if wr else ""), level="meta")
        if not quiet:
            self.rep.log(f"  ↳ 退出码 {rc}，用时 {time.monotonic() - t0:.1f}s", level="meta")
            if rc != 0:
                self.rep.log(f"  （完整输出见 "
                             f"{self.root / (section or 'gui-build.log')}）", level="warn")
        self._flush_files()
        return (rc, "\n".join(kept)) if capture else rc

    def capture(self, cmd: list[str], cwd: Path | None = None,
                section: str | None = None) -> tuple[int, str]:
        """跑命令并取回全部输出（不刷界面，但完整输出仍写进日志文件）。"""
        rc, out = self.run(cmd, cwd=cwd, section=section, capture=True, quiet=True)
        return rc, out

    # ---------------------------------------------------------- 内置工具
    def tool(self, name: str, fn, argv: list[str], cwd: Path | None = None,
             section: str | None = None,
             quiet: bool = False) -> tuple[int, str]:
        """在**本进程内**跑一个内置工具（原 tools/<name>.py，现已并进本文件）。

        ★ 2026-10-04 改：以前这里是「起一个 python 子进程去跑 tools/xxx.py」。
          现在工具已经内联进本文件（见第六节），直接调函数 —— 于是：

            * **只需要携带一个 .py 文件**，不用再带一整个 tools/ 目录；
            * 工具的输出判据（`MISSING <n>` / `ALIASED <n>` …）只有一份实现，
              不可能出现「脚本改了、主程序还在按老判据解析」这种分叉；
            * 不会再因为「找不到带 pypdf 的解释器」而整段跳过验收报告
              （run()/capture() 那种外部调用必须先猜解释器，内联后就是本进程）。

        ★ 日志行为与 `run()` 保持一致：完整输出进 `<root>/<section>`，
          关键行（或 `--verbose`）送界面 —— 于是既有的分节日志、
          `rename.log` / `merge.log` 这些文件照旧会生成。
        """
        if section:
            self._section(section)
        self.rep.check_cancel()
        head = "$ " + " ".join([name, *[str(a) for a in argv]])
        self._file(head)
        if not quiet:
            self.rep.log(head, level="cmd")
        t0 = time.monotonic()
        rc, out = _tool_run(fn, argv, cwd=cwd)
        for line in out.splitlines():
            # 只剥进日志/界面的这一份；返回值 `out` 保持原样（调用方要按
            # `MISSINGFILE <路径>` 这类 ASCII 判据解析，别去动它）。
            self._file(strip_ansi(line))
            if not quiet and (self.cfg.verbose_log or NOTABLE.search(line)):
                self.rep.log(strip_ansi(line), level="raw")
        if not quiet:
            self.rep.log(f"  ↳ 退出码 {rc}，用时 {time.monotonic() - t0:.1f}s",
                         level="meta")
            if rc != 0:
                self.rep.log(f"  （完整输出见 "
                             f"{self.root / (section or 'gui-build.log')}）", level="warn")
        self._flush_files()
        return rc, out

    def prepare_i18n_extra(self) -> Path | None:
        """把补充译文铺到 `<root>/i18n-extra/`，返回那个目录（没有就返回 None）。

        ★★ 2026-10-31 起：程序**不再内置正文译文** ★★
          正文一律来自上游 python-docs-zh-cn 的 .po（步骤 2 每次 clone/fetch 最新，
          步骤 3 铺进 Doc/locales）。程序里只保留标题表（`TITLES`）。
          这里只负责「额外的补丁」：配了 `i18n_extra_url`（http 清单 / 目录前缀 /
          `file://` / 本机目录都认）就每次运行实时抓一份；没配就什么都不做。
        """
        dest = self.root / "i18n-extra"
        url = (self.cfg.i18n_extra_url or "").strip()
        try:
            n = prepare_i18n_extra(dest, url)
        except OSError as e:                         # 写不进构建根（权限 / 磁盘满）
            import tempfile
            alt = Path(tempfile.mkdtemp(prefix="i18n-extra-"))
            try:
                n = prepare_i18n_extra(alt, url)
            except OSError:
                self.rep.log(f"      补充译文落地失败（{e}），这一步跳过", level="warn")
                return None
            self.rep.log(f"      {dest} 写不进去（{e}），改用临时目录 {alt}", level="warn")
            dest = alt
        if url:
            self.rep.log(f"      补充译文：已按 {url} 实时抓到 {n} 个文件", level="meta")
        elif n == 0:
            self.rep.log("      补充译文：程序不内置正文译文，正文全部用上游 .po"
                         "（步骤 2 已取最新；要额外打补丁就配「补充译文地址」）",
                         level="meta")
            return None                      # 没有补丁 → 别把空目录塞给下游
        return dest

    # ---------------------------------------------------------------- 工具
    def pdf_pages(self, pdf: Path) -> int | None:
        if not pdf.is_file() or pdf.stat().st_size == 0:
            return None
        rc, out = self.capture(["pdfinfo", str(pdf)])
        m = re.search(r"^Pages:\s+(\d+)", out, re.M)
        return int(m.group(1)) if m else None

    def count_invalid_utf8(self, log: Path) -> int:
        return read_text_safe(log).count("Invalid UTF-8")

    def resolve_state(self) -> None:
        """按已有产物推断各路径，这样可以从任意步骤起步。"""
        self.doc = self.root / P_CPYTHON / "Doc"
        self.vp = self.resolve_venv()
        self.latex = self.doc / "build" / "latex"
        self.zh_src = Path(self.cfg.zh_src).expanduser()

    @staticmethod
    def _venv_python(venv: Path) -> Path:
        win = venv / "Scripts" / "python.exe"
        return win if win.is_file() else venv / "bin" / "python"

    def resolve_venv(self) -> Path:
        """找到构建用的 venv。

        顺序：配置里指定的 → <root>/venv → 邻近目录的常见名字。
        其中优先挑「真的装了 sphinx」的那个 —— 本机实测那份叫 sphinx-venv，
        不是 <root>/venv，所以这里必须探测。
        """
        cands: list[Path] = []
        if self.cfg.venv.strip():
            cands.append(Path(self.cfg.venv.strip()))
        cands.append(self.root / P_VENV)
        for base in (self.root, self.root.parent):
            for nm in ("sphinx-venv", "docbuild-venv", "docs-venv", "venv", ".venv"):
                cands.append(base / nm)

        existing = [self._venv_python(c) for c in cands]
        existing = [p for p in existing if p.is_file()]
        # 去重且保持顺序
        seen: set[str] = set()
        uniq = [p for p in existing if not (str(p) in seen or seen.add(str(p)))]
        for py in uniq:
            try:
                r = subprocess.run([str(py), "-c", "import sphinx"],
                                   capture_output=True, timeout=30,
                                   creationflags=CREATE_NO_WINDOW)
                if r.returncode == 0:
                    return py
            except Exception:
                continue
        if uniq:
            return uniq[0]
        return self.root / P_VENV / "Scripts" / "python.exe"

    def need_venv(self) -> Path:
        """取 venv python；没有就给出可操作的报错。"""
        vp = self.vp or self.resolve_venv()
        if not Path(vp).is_file():
            raise Fail(
                f"找不到构建用的 venv：{vp}\n"
                f"        请先跑「步骤 4 虚拟环境与依赖」，"
                f"或在左侧「构建 venv」里直接指定已装好 sphinx 的 venv。")
        self.vp = Path(vp)
        # ★ 把 venv 的 site-packages 登记成 pypdf 的备用搜索目录（见 `_import_pypdf`）。
        #   步骤 4 一定会把 pypdf 装进 venv，而 exe 内置的那份在个别运行状态下读不到
        #   （2026-10-30 实测：三版本并行跑完 40 分钟后，步骤 8/9 同时报缺 pypdf，
        #   同一个 exe 新起进程手动跑却正常）。pypdf 是纯 Python，跨小版本直接用。
        for sp in (self.vp.parent.parent / "Lib" / "site-packages",):
            try:
                if sp.is_dir():
                    _register_pypdf_dir(sp)
            except OSError:
                pass
        return self.vp


    # =======================================================================
    #  步骤 0 —— 前置检查
    # =======================================================================
    def step0(self) -> str:
        if not self.which("git"):
            raise Fail("找不到 git，请先安装并加入 PATH")
        if not Path(self.python).is_file():
            alt = self.which("python3") or self.which("python")
            if not alt:
                raise Fail(f"找不到 Python 解释器：{self.python}")
            self.python = alt
        for tool in ("xelatex", "latexmk"):
            if not self.which(tool):
                raise Fail(
                    f"找不到 {tool}。请把 TeX Live 的 bin 目录填进「TeX Live bin」，"
                    f"当前填的是：{self.cfg.texlive_bin or '(空)'}")
        if not self.which("makeindex"):
            raise Fail("找不到 makeindex（步骤 7 的索引全靠它）。"
                       "请把 TeX Live 的 bin 目录填进「TeX Live bin」")
        # ★ 步骤 7 里 latexmk 会执行 `python makeindex-fix.py …`（修索引的脚本）：
        #   venv 路径含中文，不能写进 latexmk 的 -e（按 UTF-8 解析会炸），
        #   所以按名字调 python —— 必须确保 PATH 里有 python。
        if not self.which("python"):
            raise Fail("PATH 里找不到 python：步骤 7 的索引修复脚本要靠它启动。"
                       "把装有 python 的目录填进「构建 venv」，或让 python 进 PATH")

        rc, out = self.capture([self.python, "--version"])
        self.rep.log(f"Python  : {out.strip() or '(取不到版本)'}", level="ok")
        rc, out = self.capture(["xelatex", "--version"])
        self.rep.log(f"XeLaTeX : {out.splitlines()[0] if out.splitlines() else '?'}",
                     level="ok")
        for tool in ("latexmk", "makeindex", "pdfinfo", "pdffonts", "python"):
            w = self.which(tool)
            self.rep.log(f"  {tool:<10} {w or '缺失'}", level="meta")
        return (f"Python/TeX 工具链就绪；TeX Live = {self.cfg.texlive_bin}"
                f"；版本 {self.cfg.version}（分支 {self.cfg.branch}）")

    # =======================================================================
    #  步骤 1 —— 取 CPython Doc 源（稀疏克隆）
    # =======================================================================
    def git_clone(self, repo: str, dest: Path, branch: str, label: str,
                  explicit: str = "", sparse: bool = False,
                  timeout: float = 300.0) -> str:
        """克隆仓库，**失败自动换镜像**；返回真正用到的镜像名。

        ★★ 为什么要有这一步（2026-10-31 用户实拍）★★
          只写一个代理前缀时，它一挂三件事一起废：三个版本全卡在步骤 1，
          日志只有一句 `Could not connect to server after 210 ms`。
          现在按 `GH_MIRRORS` 依次试（ghproxy.net → gh-proxy.com → ghfast.top →
          xget → githubproxy.cc → gitclone → 直连），每个都有超时看门狗，
          成功后记住它——同一次运行里克隆翻译仓库会优先用这个能用的。

        `explicit` 是配置里「CPython 仓库地址 / 翻译仓库地址」的完整 URL，
        一旦填了就排在最前面（尊重用户显式选择），失败仍会回退。
        """
        cands = self.cfg.git_urls(repo, explicit)
        if self._gh_good:                     # 这次已经验证过的镜像优先
            cands.sort(key=lambda kv: 0 if kv[0] == self._gh_good else 1)
        errors: list[str] = []
        for i, (name, url) in enumerate(cands, 1):
            if dest.exists():
                self._force_clean(dest, f"上一次没克隆成的 {dest.name}")
            self.rep.log(f"  [{i}/{len(cands)}] {label}：用 {name} 克隆分支 {branch}",
                         level="info" if i == 1 else "warn")
            self.rep.log(f"        {url}", level="meta")
            cmd = ["git", "-c", "http.lowSpeedLimit=2000", "-c", "http.lowSpeedTime=25",
                   "clone", "--depth", "1"]
            if sparse:
                cmd += ["--filter=blob:none", "--sparse"]
            cmd += ["--branch", branch, url, str(dest)]
            t0 = time.monotonic()
            rc = self.run(cmd, cwd=self.root, section="clone.log", timeout=timeout)
            if rc == 0 and (dest / ".git").is_dir():
                self._gh_good = name
                # ★ 记住这次能用的前缀（写回配置对象，GUI 关闭时随之保存）：
                #   下一轮直接从它开始，不用再花一次超时去试挂掉的那个。
                #   只在内置「自动」模式下记；用户手填的前缀不动。
                if not (self.cfg.gh or "").strip() and name != "直连":
                    self.cfg.gh = url.replace(repo, "").rstrip("/")
                self.rep.log(f"  ✔ {label} 已就位（{name}，"
                             f"用时 {human_dur(time.monotonic() - t0)}）", level="ok")
                return name
            errors.append(f"{name}（退出码 {rc}）")
            self.rep.log(f"  ✘ {name} 不通，换下一个镜像", level="warn")
        raise Fail(
            f"{label}克隆失败：内置镜像全部试过 —— " + "、".join(errors) +
            "\n  可在「GitHub 代理」里填一个你自己能用的前缀"
            "（例：https://ghproxy.net/https://github.com 或 https://xget.xi-xu.me/gh），"
            "\n  或直接填「CPython 仓库地址 / 翻译仓库地址」。")

    def _git_refresh(self, repo: Path, branch: str, label: str) -> None:
        """把已有克隆更新到远端最新（★「从网站实时调取」）。

        fetch 失败（断网 / 代理挂了）不算致命：留着本地那份继续用，只报一条警告。
        """
        rc = self.run(["git", "-C", str(repo), "fetch", "--depth", "1",
                       "origin", branch], cwd=repo)
        if rc != 0:
            self.rep.log(f"{label} fetch 失败（网络？），继续用本地已有版本", level="warn")
            return
        rc = self.run(["git", "-C", str(repo), "reset", "--hard", "FETCH_HEAD"], cwd=repo)
        if rc == 0:
            _, head = self.capture(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"])
            self.rep.log(f"{label} 已更新到 origin/{branch} @ {head.strip()}", level="ok")

    def _git_with_mirrors(self, repo: Path, args: list[str], label: str,
                          attempts: int = 0, timeout: float = 240.0) -> int:
        """在**已存在的克隆**上跑 git 子命令，失败就换镜像重试（改 origin）。

        ★★ 为什么需要（2026-10-31 实测）★★
          `--filter=blob:none` 的克隆只是「骨架」，真正的文件要在
          `sparse-checkout set` 那一步才从 origin 按需拉（promisor fetch）。
          这一步同样是联网，代理断流时报：
            error: RPC failed; curl 18 transfer closed ...
            fatal: could not fetch <sha> from promisor remote
          只重试同一个 origin 没用 —— 镜像本身在抖。这里每次失败就把 origin
          换成候选表里的下一个（ghproxy.net → gh-proxy.com → ghfast.top …），
          成功后记住这个镜像，后面的步骤继续用它。
        """
        cands = self.cfg.git_urls("python/cpython", self.cfg.cpython_url)
        if self._gh_good:
            cands.sort(key=lambda kv: 0 if kv[0] == self._gh_good else 1)
        if attempts and attempts > 0:
            cands = cands[:max(1, attempts)]
        last = 1
        for i, (name, url) in enumerate(cands, 1):
            self.run(["git", "-C", str(repo), "remote", "set-url", "origin", url],
                     quiet=True)
            self.rep.log(f"  [{i}/{len(cands)}] {label}：走 {name}", level="meta")
            last = self.run(["git", "-c", "http.lowSpeedLimit=2000",
                             "-c", "http.lowSpeedTime=25", "-C", str(repo), *args],
                            timeout=timeout)
            if last == 0:
                self._gh_good = name
                return 0
            self.rep.log(f"  ✘ {label} 在 {name} 上断了（退出码 {last}），换下一个镜像",
                         level="warn")
        return last

    def _git_show(self, cpy: Path, rel: str):
        """`git show HEAD:<rel>`（按需只拉这一个 blob），失败换镜像重试。

        返回值形状与 `subprocess.run(..., capture_output=True)` 一致
        （`.returncode` / `.stdout` / `.stderr`），调用点照原样用。
        """
        cands = self.cfg.git_urls("python/cpython", self.cfg.cpython_url)
        if self._gh_good:
            cands.sort(key=lambda kv: 0 if kv[0] == self._gh_good else 1)
        last = subprocess.CompletedProcess([], 1, b"", b"no mirror configured")
        for name, url in cands:
            self.run(["git", "-C", str(cpy), "remote", "set-url", "origin", url],
                     quiet=True)
            last = subprocess.run(
                ["git", "-c", "http.lowSpeedLimit=2000", "-c", "http.lowSpeedTime=25",
                 "-C", str(cpy), "show", f"HEAD:{rel}"],
                capture_output=True, creationflags=CREATE_NO_WINDOW)
            if last.returncode == 0 and last.stdout:
                self._gh_good = name
                return last
        return last

    def _ensure_sparse(self, cpy: Path) -> None:
        """确保稀疏检出里有 SPARSE_PATHS 的全部路径。

        ★ 为什么「已有克隆」也要跑一遍：稀疏路径是**逐步补出来的**，历史上漏过两次：

          * `Include` —— 早期漏了，`patchlevel.py` 读不到 `Include/patchlevel.h`，
            Sphinx 直接崩；
          * `Lib/profiling/sampling` —— 3.15 的 Tachyon 配图在那里，漏了以后
            library 与 whatsnew 两册的 latexmk 退出码 12；
          * `Grammar` —— `reference/grammar.rst` 用 literalinclude 引
            `Grammar/python.gram`，漏了以后**《完整的语法规范》整章空白**
            （3.13/3.14/3.15 全中，那一章本该 20 多页）；
          * `Parser` —— `library/ast.rst` 引 `Parser/Python.asdl`。

          直接重跑会走「已存在 → 跳过克隆」分支，于是老目录**永远**补不上
          这些项 —— 报错还离病根很远。sparse-checkout set 是幂等的，
          多跑一次只补差集，很便宜（秒级）。

        ★ 这也是步骤 1 的**第二次联网**（--filter=blob:none 的 blob 现在才拉），
          经代理时常见的失败是：
            error: RPC failed; curl 56 Recv failure: Connection was reset
            error: 2182 bytes of body are still expected
            fatal: early EOF / fetch-pack: invalid index-pack output
          属于断流，不是配置错；克隆对象库已经在了，重试不用重头。
        """
        # ★ 这一步才是真正把 blob 从网上拉下来（--filter=blob:none 的补取）。
        #   代理断流时只重试同一个 origin 没用，改为**换镜像重试**。
        rc = self._git_with_mirrors(cpy, ["sparse-checkout", "set", *SPARSE_PATHS],
                                   "稀疏检出", timeout=300.0)
        if rc != 0:
            raise Fail(
                "git sparse-checkout set 在所有镜像上都失败了，"
                + " / ".join(SPARSE_PATHS) + " 没取全。"
                "常见原因是 GitHub 代理断流（日志里找 curl 18/56 / early EOF）；"
                "直接重跑即可 —— 克隆已在，不会从零开始；"
                "或把「GitHub 代理」填成你自己能用的那个前缀。")

    def _ensure_doc_ref_files(self, cpy: Path) -> int:
        """把「Doc 引用到、但磁盘上没有」的文件自动补回来；返回补上的条数。

        判据来自 `tools/check-doc-refs.py`（GUI 与 bash 共用同一份实现），
        它报的 `MISSINGFILE <仓库相对路径>` 是待补清单，`MISSINGKIND <路径> <kind>`
        给出**这个路径到底是单文件还是目录**。两类分别处理：

        * **目录**（如整个 `Grammar/` 从来没进过稀疏检出）→
          `git sparse-checkout add <目录>`（幂等、只补差集）；
        * **单文件**（如 `Lib/test/exception_hierarchy.txt`、
          `Modules/expat/COPYING`）→ `git show HEAD:<路径>`，
          走同一条按需拉取（promisor）通道只取那一个 blob。
          cone 模式的最小单位是**目录**，而 `Lib/test/` 有几万个文件 ——
          为一个 2 KB 的文本把整个目录拉下来不值得。

        ★★ 曾经的 bug：这里（以及 `check-doc-refs.py` 里的同一处）用
          「最后一段带不带 `.`」猜文件/目录。`Modules/expat/COPYING`
          **没有扩展名**，于是被当成目录、拼出一条必然失败的命令：

              git sparse-checkout set Doc Misc/NEWS.d ... Modules/expat/COPYING
              fatal: 'Modules/expat/COPYING' is not a directory;
                     to treat it as a directory anyway, rerun with --skip-checks

          于是自动补件**静静失效**，只剩一句「补目录失败（多为代理断流）」
          —— 病因被指到一个无关方向，真实缺口（3.15 的 `Doc/license.rst`
          新增 include 它）永远补不上，步骤 6 每次卡在同一处。
          现在类型由 `tools/check-doc-refs.py` 问 git（`ls-tree` 的 objecttype）
          得出，**本函数不再做任何形状猜测**：判据只有一处实现，也就不可能再分叉。

        ★ 为什么值得自动做：这两类缺件的后果都是**静默的** ——
          `literalinclude` 缺了，Sphinx 不报错、`.tex` 里什么都不写，
          PDF 里那一整节就没了（对用户来说就是「文档少了内容」，而构建全绿）。
          上游每次新增这类引用，这里都能自动跟上，不必等有人发现。
        """
        doc = cpy / "Doc"
        if not doc.is_dir():
            return 0

        def missing_now() -> list[tuple[str, str]]:
            # ★ 内置工具（原 tools/check-doc-refs.py），进程内调用：不起子进程，
            #   也就不会「找不到解释器就静默跳过自检」。
            _rc, txt = self.tool("check-doc-refs", cdr_main, [str(doc), "--list"],
                                 quiet=True)
            return self._parse_missing(txt)

        miss = missing_now()
        if not miss:
            return 0

        dirs = [rel for rel, kind in miss if kind == "tree"]
        files = [rel for rel, kind in miss if kind != "tree"]

        if dirs:
            self.rep.log("稀疏检出里缺这些目录：" + "、".join(dirs)
                         + "　→ 自动并入 sparse-checkout", level="warn")
            # ★ 用 `add` 而不是 `set`：`set` 是**全集**，要把现有路径全重列一遍，
            #   而 `add` 天然幂等、只加不减，不会误删 `_ensure_sparse` 之外的东西。
            # ★ 失败要换镜像重试（这一步同样要从网上拉 blob，见 _git_with_mirrors）
            self._git_with_mirrors(cpy, ["sparse-checkout", "add", *dirs],
                                   "补目录", timeout=300.0)

        done = 0
        for rel in files:
            tgt = cpy / rel
            tgt.parent.mkdir(parents=True, exist_ok=True)
            p = self._git_show(cpy, rel)
            if p.returncode != 0 or not p.stdout:
                err = p.stderr.decode("utf-8", "replace").strip().splitlines()
                self.rep.log(f"      按需取 {rel} 失败（退出码 {p.returncode}）"
                             + (f"：{err[-1][:160]}" if err else ""), level="err")
                continue
            tgt.write_bytes(p.stdout)
            done += 1
            self.rep.log(f"      按需取回 {rel}（{len(p.stdout)} 字节，"
                         f"只拉这一个 blob，不拉整个目录）", level="ok")

        left = [rel for rel, _k in missing_now()]
        if left:
            self.rep.log("仍有补不上的：" + "、".join(left)
                         + "（多为代理断流，重跑本步即可）", level="err")
        return done

    def step1(self) -> str:
        cpy = self.root / P_CPYTHON
        conf = cpy / "Doc" / "conf.py"
        branch = self.cfg.branch
        if conf.is_file() and self.cfg.skip_clone_if_exists:
            self.rep.log(f"已存在 {conf}，跳过克隆", level="ok")
            if self.cfg.refresh_sources and self.cfg.download_sources:
                self._git_refresh(cpy, branch, "CPython 源码")
            # ★ 老克隆可能漏了后加的稀疏路径（见 _ensure_sparse 注释）
            self._ensure_sparse(cpy)
            self._ensure_doc_ref_files(cpy)
        else:
            if cpy.exists():
                self.rep.log(f"清理旧目录 {cpy}", level="meta")
                self._force_clean(cpy, "旧 CPython 源码目录")
            self.root.mkdir(parents=True, exist_ok=True)
            # ★ 多个镜像自动回退（见 git_clone 的说明）：单一代理挂了不会整轮失败
            self.git_clone("python/cpython", cpy, branch, "CPython 源码",
                           explicit=self.cfg.cpython_url, sparse=True)
            # ★★ 坑：Include 必须一起取 ★★ 见 _ensure_sparse
            #    （Doc 的 patchlevel.py 要读 Include/patchlevel.h；Misc/NEWS.d 是
            #      Doc/Makefile 的 build 目标要的；Lib/profiling/sampling 见 SPARSE_PATHS）
            self._ensure_sparse(cpy)
            self._ensure_doc_ref_files(cpy)

        # 验证 Include/patchlevel.h —— 上面那个坑的自检
        pl = cpy / "Include" / "patchlevel.h"
        if not pl.is_file():
            raise Fail(f"缺少 {pl}：稀疏克隆漏了 Include，Sphinx 会立刻崩。"
                       f"请执行 git -C {cpy} sparse-checkout set "
                       + " ".join(SPARSE_PATHS))

        # ★ cwd 必须是 Doc/：patchlevel.py 里是 `./../Include/patchlevel.h`
        #   （相对**当前目录**），不设 cwd 就会拿启动目录去拼 → FileNotFoundError，
        #   于是版本号恒为 "?"，还连带一句「与所选版本不一致」的假警告。
        #   Sphinx 自己构建时 cwd 就是 Doc/，所以这里照它来。
        rc, out = self.capture(
            [self.python, str(cpy / "Doc" / "tools" / "extensions" / "patchlevel.py")],
            cwd=cpy / "Doc")
        ver = out.strip().splitlines()[-1] if out.strip() else "?"
        self.rep.log(f"patchlevel → {ver}", level="ok")
        if not ver.startswith(self.cfg.version):
            self.rep.log(f"注意：源码版本号 {ver} 与所选版本 {self.cfg.version} 不一致，"
                         f"请确认分支 {branch} 是否正确", level="warn")
        return f"CPython {branch} 源码就绪，版本号 {ver}"

    # =======================================================================
    #  步骤 2 —— 准备中文翻译 .po
    # =======================================================================
    def step2(self) -> str:
        branch = self.cfg.branch
        local = Path(self.cfg.zh_src).expanduser() if self.cfg.zh_src.strip() else None

        if local and local.is_dir():
            # 高级用法：显式指定本地翻译源（默认留空 = 联网下载）
            zh = local
            n = sum(1 for _ in zh.rglob("*.po"))
            self.rep.log(f"使用本地翻译源：{zh}（{n} 个 .po）", level="ok")
            if self.cfg.download_sources:
                self.rep.log("（本地翻译源不会联网更新；要联网就把它清空）", level="meta")
        elif not self.cfg.download_sources:
            raise Fail("「从网站实时下载」被关掉了，但「本地翻译源」是空的。"
                       "要么打开联网下载，要么指定一个本地 python-docs-zh-cn 目录")
        else:
            zh = self.root / "zh-cn"
            if zh.is_dir() and self.cfg.skip_clone_if_exists:
                self.rep.log(f"使用已克隆的 {zh}（分支 {branch}）", level="meta")
                if self.cfg.refresh_sources:
                    self._git_refresh(zh, branch, "翻译源")
            else:
                if zh.exists():
                    self._force_clean(zh, "旧翻译源目录")
                self.root.mkdir(parents=True, exist_ok=True)
                # 同样走镜像回退；刚才克隆 CPython 成功的那个会优先
                self.git_clone("python/python-docs-zh-cn", zh, branch, "翻译源",
                               explicit=self.cfg.zh_url)
        self.zh_src = zh
        if not zh.is_dir():
            raise Fail(f"翻译源目录不存在：{zh}")
        return f"翻译源 {zh.name}（分支 {branch}）"

    # =======================================================================
    #  步骤 3 —— 把 .po 按目录层级装进 locales
    # =======================================================================
    def step3(self) -> str:
        if self.doc is None:
            self.resolve_state()
        assert self.doc is not None
        zh = self.zh_src
        if zh is None or not zh.is_dir():
            raise Fail("翻译源还没准备好，请先跑步骤 2")

        dst = self.doc / "locales" / self.cfg.lang / "LC_MESSAGES"
        # 脚本是 `rm -rf $DOC/locales` —— 整棵清掉重装，避免残留旧译文。
        if (self.doc / "locales").exists():
            self._force_clean(self.doc / "locales", "旧 locales")
        dst.mkdir(parents=True, exist_ok=True)

        # ★★ 坑：不要写成 `cp "$ZH"/library/*.po "$DST"/` ★★
        #   路径含空格/中文 + library 下 326 个文件 → 命令行超 Windows 上限，
        #   bash 的 glob 静默失败（表面 cp 成功，实际一个都没拷）。
        #   Python 的 shutil.copy2 是逐个文件系统调用，没有命令行长度问题。
        copied = 0
        seen_dirs: set[str] = set()
        for src in sorted(zh.rglob("*.po")):
            rel = src.relative_to(zh)
            if any(part.startswith(".") for part in rel.parts):
                continue
            seen_dirs.add(str(rel.parent) if len(rel.parts) > 1 else "(根目录)")
            tgt = dst / rel
            tgt.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, tgt)
            copied += 1

        total = sum(1 for _ in dst.rglob("*.po"))
        src_total = sum(1 for _ in zh.rglob("*.po"))
        missing = [d for d in ZH_SUBDIRS if d not in {p.name for p in dst.iterdir() if p.is_dir()}]
        self.rep.log(f"已装 .po：{total} 个（源 {src_total} 个，拷贝 {copied} 个）", level="ok")
        self.rep.log(f"目录：{'、'.join(sorted(seen_dirs))}", level="meta")
        if missing:
            self.rep.log(f"警告：翻译源里缺少这些目录 {missing}，对应页面会保留英文",
                         level="warn")
        if total == 0:
            raise Fail("一个 .po 都没装上，检查翻译源目录结构")
        if total != src_total:
            self.rep.log("警告：装进去的数量与源不一致，可能有文件被跳过", level="warn")

        n_alias, n_extra = self._alias_po(zh, dst)
        total = sum(1 for _ in dst.rglob("*.po"))
        extra_note = (f"（另有 {n_extra} 个用本项目补充译文）" if n_extra else "")
        return (f"{total} 个 .po 已就位" + extra_note
                + (f"（含接回 {n_alias} 个被搬走的译文）" if n_alias else ""))

    # -----------------------------------------------------------------------
    def _alias_po(self, zh: Path, dst: Path) -> tuple[int, int]:
        """给「上游搬走了源文件、译文还留在旧目录」的页面把译文接回新路径。

        ★ 为什么必须做：Sphinx 是按**源文件的相对路径**去
          `LC_MESSAGES/<同样的相对路径>.po` 找译文的。CPython 3.14 把整章
          `Doc/library/stdtypes.rst` 搬去了 `Doc/builtins/stdtypes.rst`，
          而 python-docs-zh-cn 的 `3.14` 分支里译文仍在 `zh-cn/library/*.po`
          —— 路径一对不上，Sphinx **不报错、不警告、翻译进度还是 100%**，
          那一页就原样保留英文。实测《11Python 内置参考手册》整册 196 页
          全是英文，构建日志一片绿，谁也看不出来。

        判据来自 `tools/alias-po.py`（GUI 与 bash 共用同一份实现）：
        拿 `.po` 的 msgid（= 英文原文）去 `.rst` 原文里找，命中率达标才认。

        ★ 第二类漏译：官方**根本没翻**这一页。实测把 zh-cn 的 535 个 .po 全扫一遍，
          `Doc/builtins/index.rst`（章标题 + 引言）与 `Doc/builtins/time-complexity.rst`
          的最佳配对都是 0.00 —— 不是路径问题，是上游确实没译。这类页面用
          `sphinx-pdf/i18n-extra/` 里**本项目自补**的 .po 补上（`--extra`）。

        ★ 第三类漏译：**原文只改了大小写，msgid 就失配了**。3.15 实测
          `Doc/builtins/functions.rst` 的章标题从 `Built-in Functions` 改成
          `Built-in functions`，译文条目仍写着旧 msgid → 不算命中 → 那一章的
          书签静默变成 `Built-in functions`（3.14 还是「内置函数」），
          同样**零报错、零 warning**。工具会按「大小写折叠后唯一对应、且译文含
          中文」把历史译文接回去（末尾 `DRIFTED <n>`；实测 549 个 .po 里只有 1 条）。

        返回 (接回的被搬走译文数, 补上的缺译页数)。
        """
        cmd = [str(zh), "--doc", str(self.doc), "--locale", str(dst)]
        extra = self.prepare_i18n_extra()
        if extra is not None:
            cmd += ["--extra", str(extra)]
        _rc, out = self.tool("alias-po", alpo_main, cmd)
        for ln in out.splitlines():
            s = ln.strip()
            if s.startswith(("ALIAS ", "EXTRA ", "DRIFT ")):
                self.rep.log("  " + s, level="ok")
        m = re.search(r"^ALIASED (\d+)", out, re.M)
        n = int(m.group(1)) if m else 0
        m2 = re.search(r"^EXTRAED (\d+)", out, re.M)
        n_extra = int(m2.group(1)) if m2 else 0
        m3 = re.search(r"^DRIFTED (\d+)", out, re.M)
        n_drift = int(m3.group(1)) if m3 else 0
        if n:
            self.rep.log(f"  ^ 这 {n} 个页面在源仓库里就是英文（源目录被上游搬过），"
                         f"接回译文后 PDF 反而比官网完整", level="warn")
        if n_extra:
            self.rep.log(f"  ^ 这 {n_extra} 个页面上游**根本没有译文**，"
                         f"用的是本项目自带的补充译文（{extra}）", level="warn")
        if n_drift:
            # ★ 第三类哑失败：原文只改了一个字母的大小写（3.15 的
            #   `Built-in Functions` → `Built-in functions`），msgid 一字之差
            #   就不算命中 → 那一章的书签静默变回英文，而日志全绿。
            #   工具已按「大小写折叠后唯一对应、且译文含中文」把历史译文接回去。
            self.rep.log(f"  ^ 这 {n_drift} 条译文因**原文只改了大小写**而失配"
                         f"（不修就会静默显示英文），已按同一标题接回历史译文",
                         level="warn")
        return n, n_extra

    # =======================================================================
    #  步骤 4 —— venv 与依赖
    # =======================================================================
    def _pip_attempts(self) -> list[tuple[str, list[str], str]]:
        """pip 依次尝试的 (源, 追加参数, 为什么这么做)。

        ★ 顺序按「代价从小到大」，只有真失败才往下走：
          1) 配置的源                  —— 正常情况一次过，不额外花时间
          2) 同一个源 + `--no-cache-dir` —— 治本地 pip 缓存被污染（最常见）
          3) 官方源 + `--no-cache-dir`   —— 治镜像本身坏了；国内会慢，但只慢这一步
        """
        idx = (self.cfg.pip_index or "").strip() or OFFICIAL_INDEX
        out: list[tuple[str, list[str], str]] = [(idx, [], "用配置的源")]
        if idx.rstrip("/") != OFFICIAL_INDEX.rstrip("/"):
            out.append((idx, ["--no-cache-dir"], "同一个源 + 清缓存"))
        out.append((OFFICIAL_INDEX, ["--no-cache-dir"], "官方源 + 清缓存"))
        return out

    def _pip_install(self, pkgs: list[str]) -> int:
        """装依赖；失败时**自动换一种办法再试**，返回最后一次的退出码。

        ★ 为什么不能「失败就抛」：实测在清华源上撞过
          `THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE`
          —— 下载下来的 wheel 与索引里登记的 sha256 对不上（镜像上的文件被换过，
          或本地 pip 缓存坏了）。清缓存 / 换源立刻就好，这类失败**与代码无关**。
          把它变成「自动退一步 + 一句人话结论」，比让用户去读几十行 pip 日志有用。
        """
        plans = self._pip_attempts()
        last = 1
        for n, (idx, extra, why) in enumerate(plans, 1):
            if n > 1:
                self.rep.log(f"pip 重试 {n}/{len(plans)}：{why}"
                             f"（-i {idx} {' '.join(extra)}）".rstrip(), level="warn")
            rc, out = self.run(
                [str(self.vp), "-m", "pip", "install",
                 "--retries", "5", "--timeout", "30",
                 "-i", idx, *extra, *pkgs],
                section="pip.log", capture=True)
            last = rc
            if rc == 0:
                if n > 1:
                    self.rep.log(f"pip 第 {n} 次尝试成功（{why}）", level="ok")
                return 0
            hint = pip_hint(out)
            if hint:
                self.rep.log(f"这一次失败的原因：{hint}", level="warn")
        return last

    def _pip_plan(self) -> tuple[list[str], list[str]]:
        """这一版要装什么 → `(pip 参数, 就绪判据的模块名)`。

        ★★ 为什么不能所有版本共用一份清单（2026-11-03 实测）★★
        内置 `PIP_PACKAGES` 写的是 `sphinx<9.0.0`，装出来是 8.1.3。而官方各分支
        `Doc/requirements.txt` 钉的版本天差地别：

            3.10 → sphinx==3.4.3（还钉了 docutils==0.17.1 / jinja2==3.0.3）
            3.11 → 见该分支 requirements.txt
            3.12 → sphinx~=8.2.0
            3.13+ → 与内置清单相容（已跑通，不动）

        拿 Sphinx 8 去编 3.10 的 Doc，等于用五年后的工具链编五年前写的
        `Doc/tools/extensions/*.py` —— 步骤 6 必挂。所以 **3.12 及更早一律改用
        官方自己的 requirements.txt**（它连 docutils/jinja2 一起钉好，最忠实）。

        两条附带约束：
          · SVG 转换器**只在真有 SVG 时才装** —— `sphinxcontrib-svg2pdfconverter`
            装上去会把老 Sphinx 顶掉，而 3.10~3.12 的 Doc 根本没有 SVG；
          · `pypdf` 始终装（步骤 9 合并册与验收报告要用，官方清单里没有）。
        """
        doc = self.doc
        if doc is None:
            try:
                self.resolve_state()
                doc = self.doc
            except Exception:
                doc = None
        req = doc / "requirements.txt" if doc else None
        if req is not None and req.is_file() and ver_tuple(self.cfg.version) <= (3, 12):
            cons = doc / "constraints.txt"
            pkgs = ["-r", str(req)]
            if cons.is_file():
                pkgs += ["-c", str(cons)]
            pkgs += ["pypdf>=5"]
            return pkgs, ["sphinx", "python_docs_theme", "pypdf"]
        return list(PIP_PACKAGES), list(READY_MODULES)

    def step4(self) -> str:
        # venv 位置：配置指定 > 自动探测（优先真的装了 sphinx 的那个）> <root>/venv
        vp = self.resolve_venv()
        if not Path(vp).is_file():
            venv_dir = (Path(self.cfg.venv.strip()) if self.cfg.venv.strip()
                        else self.root / P_VENV)
            self.rep.log(f"没有可用的 venv，创建 {venv_dir}", level="info")
            rc = self.run([self.python, "-m", "venv", str(venv_dir)])
            if rc != 0:
                raise Fail(f"创建 venv 失败：{venv_dir}")
            vp = self._venv_python(venv_dir)
        self.vp = Path(vp)
        if not self.vp.is_file():
            raise Fail(f"venv 里的 Python 不存在：{self.vp}")
        self.rep.log(f"venv python → {self.vp}", level="meta")

        pkgs, ready_mods = self._pip_plan()
        if pkgs[:1] == ["-r"]:
            self.rep.log(f"老版本（{self.cfg.version}）：按官方 Doc/requirements.txt 装依赖",
                         level="info")
        ready = self.run([str(self.vp), "-c",
                          "import " + ", ".join(ready_mods)], section="pip.log") == 0
        if ready and self.cfg.skip_pip_if_ready:
            self.rep.log("依赖已就绪，跳过 pip 安装（省时间）", level="ok")
        else:
            if ready:
                self.rep.log("依赖已就绪，但按设置仍然重装", level="meta")
            rc = self.run([str(self.vp), "-m", "pip", "install", "--upgrade", "pip",
                           "--retries", "3", "--timeout", "30",
                           "-q", "-i", self.cfg.pip_index], section="pip.log")
            if rc != 0:
                self.rep.log("pip 自升级失败，继续尝试装依赖（不影响出 PDF）", level="warn")
            rc = self._pip_install(pkgs)
            if rc != 0 and pkgs[:1] == ["-r"]:
                # 官方清单装不上（网络/包撤下/环境不合）→ 退回内置清单，至少不比原来差
                self.rep.log("按官方 requirements.txt 装不上，退回内置清单再试一次",
                             level="warn")
                rc = self._pip_install(list(PIP_PACKAGES))
            if rc != 0:
                raise Fail(
                    "pip 安装依赖失败（已依次试过：配置源 → 同源清缓存 → 官方源），"
                    f"看 {self.root / 'pip.log'}\n"
                    "  若日志里说 sha256 对不上：多半是镜像上那份包被换过、或本地 pip "
                    "缓存坏了；直接点这个版本的「重试」即可，也可以用官方源再试。")

        rc, out = self.capture([str(self.vp), "-c",
                                "import sphinx, python_docs_theme;"
                                "print('sphinx', sphinx.__version__)"])
        self.rep.log(out.strip() or "依赖自检未通过", level="ok")

        # ★★ venv 现在才真正就绪，而 self.env 是 __init__ 时定死的 ★★
        #   **首建**时 venv 还不存在，`_venv_scripts_dir()` 拿到 None，
        #   PATH 里就没有 venv\Scripts —— 步骤 7 的 `python makeindex-fix.py`
        #   会解析到用户系统里随便哪个 python（2026-10-28 实测：解析到用户 PATH
        #   里另一套 Python，makeindex 全部失败）。这里重建一次（幂等）。
        self.env = self._make_env()

        if self.doc is None:
            self.resolve_state()
        assert self.doc is not None
        if self.cfg.keep_build_dir:
            self.rep.log("按设置保留已有 build/ 目录（增量构建）", level="meta")
        else:
            b = self.doc / "build"
            if b.exists():
                self.rep.log(f"清空 {b}（保证从零构建）", level="meta")
                self._force_clean(b, "旧 build 目录")
        # 步骤 6 会生成 build/latex，这里预先把变量指向它
        self.latex = self.doc / "build" / "latex"
        return f"venv 就绪，sphinx {out.split('sphinx', 1)[-1].strip() if out else '?'}"

    # =======================================================================
    #  步骤 5 —— 构建 HTML
    # =======================================================================
    def step5(self) -> str:
        if not self.cfg.build_html:
            self.rep.log("按设置跳过 HTML 构建（只影响 HTML 验证，不影响 PDF）", level="warn")
            return "已跳过"
        self.need_venv()
        assert self.doc
        rc = self.run([str(self.vp), "-m", "sphinx", "-b", "html",
                       "-d", "build/doctrees-html", "-j", self.cfg.sphinx_jobs(),
                       "-D", f"language={self.cfg.lang}",
                       ".", "build/html"],
                      cwd=self.doc, section="html-build.log")
        log = self.root / "html-build.log"
        warn = sum(1 for ln in read_text_safe(log).splitlines() if ln.startswith("WARNING"))
        self.rep.log(f"HTML 退出码={rc}  警告={warn}", level="ok" if rc == 0 else "err")
        idx = self.doc / "build" / "html" / "index.html"
        if rc == 0 and idx.is_file():
            self.rep.log(f"产物：{idx}", level="meta")
        if rc != 0:
            self.rep.log("HTML 构建失败，但 PDF 不一定受影响（可关掉本步后重跑）",
                         level="warn")
        return f"HTML 完成，{warn} 条警告"

    # =======================================================================
    #  步骤 6 —— 构建 LaTeX 源
    # =======================================================================
    @staticmethod
    def _refmissing(text: str) -> int:
        """从工具输出里取 `REFMISSING <n>`；取不到返回 -1（当作「说不清」）。"""
        for ln in text.splitlines():
            if ln.startswith("REFMISSING "):
                try:
                    return int(ln.split(" ", 1)[1])
                except ValueError:
                    return -1
        return -1

    @staticmethod
    def _parse_missing(text: str) -> list[tuple[str, str]]:
        """从 `check-doc-refs.py` 的输出里取 [(仓库相对路径, 类型), …]。

        `MISSINGFILE <路径>` 给出**缺哪些**；`MISSINGKIND <路径> <blob|tree|?>`
        给出**它是单文件还是目录**（由工具问 git 得出 —— 那边 `_kind()` 里记着
        「用有没有点猜类型」踩过的坑：`Modules/expat/COPYING` 被当成目录，
        于是拼出一条必然 `fatal` 的 `sparse-checkout set`，自动补件静静失效）。

        类型缺失时按 `'?'` 处理，调用方当**单文件**走 `git show`
        （对文件永远安全）。★ 全项目只此一处解析，两个调用方共用。
        """
        kind: dict[str, str] = {}
        order: list[str] = []
        for ln in text.splitlines():
            if ln.startswith("MISSINGFILE "):
                rel = ln.split(" ", 1)[1].strip()
                if rel and rel not in kind:
                    order.append(rel)
                    kind[rel] = "?"
            elif ln.startswith("MISSINGKIND "):
                rel, _sep, k = ln.split(" ", 1)[1].strip().rpartition(" ")
                if rel:
                    kind[rel] = k or "?"
        return [(rel, kind.get(rel, "?")) for rel in order]

    def _guard_doc_refs(self) -> None:
        """步骤 6 / 7 之前扫一遍「Doc/ 之外的引用」；缺了**先自动补**，补不上才停。

        ★ 唯一实现是 `tools/check-doc-refs.py` —— bash 侧调的是同一份，
          判据不可能再分叉（这条教训本项目付过两次学费）。
          它查三类指令：`image`/`figure`、`literalinclude`、`include`。

        为什么值得在动手编之前先花几秒：

        * `literalinclude` / `include` 目标缺失 → Sphinx **只留一条 warning**，
          `.tex` 里什么都不写 → **PDF 里整节空白**，全程没有任何报错。
          实测 3.13 / 3.14 / 3.15 的《完整的语法规范》整章只剩标题 + 两行引言
          （`Grammar/python.gram` 没被稀疏克隆取到），而它本该 20 多页；
          `builtins/exceptions.rst` 引的 `Lib/test/exception_hierarchy.txt` 同理，
          「异常层次结构」那一节也会整段消失。
        * `image` / `figure` 缺失 → 原始反斜杠路径进 `.tex` → 未定义控制序列 →
          latexmk 退出码 12、整册不出 PDF（报错点离病根隔了两层工具）。

        发现缺口时**先尝试自动补**（`_ensure_doc_ref_files`）—— 这类缺件最要命的地方
        就是「它只留一条 warning，没人会在意」。
        """
        assert self.doc
        rc, text = self.tool("check-doc-refs", cdr_main, [str(self.doc)], quiet=True)
        n = self._refmissing(text)
        if n:
            self.rep.log(f"发现 {n} 处「Doc 引用了、但磁盘上没有」的文件，"
                         "先尝试自动补……", level="warn")
            self._ensure_doc_ref_files(self.root / P_CPYTHON)
            rc, text = self.tool("check-doc-refs", cdr_main, [str(self.doc)], quiet=True)
            n = self._refmissing(text)
        for ln in text.splitlines():
            s = ln.strip()
            if not s or s.startswith(("MISSINGFILE ", "MISSINGKIND ", "REFMISSING ")):
                continue
            self.rep.log(f"      {s}", level="warn" if n else "meta")
        if rc != 0 or n:
            # 自动补已经跑过一轮；走到这里说明还差几处。给出的补救命令**按类型**分开：
            # 目录用 sparse-checkout add、单文件用 git show。
            # ★ 老版本这里一律打印 `sparse-checkout set <SPARSE_PATHS>` ——
            #   既漏掉了缺的那一项，又把单文件塞进只收目录的命令里，
            #   于是用户照抄也修不好（3.15 的 Modules/expat/COPYING 就是这样）。
            miss = self._parse_missing(text)
            cpy_s = str(self.root / P_CPYTHON).replace("\\", "/")
            dirs = [rel for rel, k in miss if k == "tree"]
            files = [rel for rel, k in miss if k != "tree"]
            plan: list[str] = []
            if dirs:
                plan.append(f"      git -C {cpy_s} sparse-checkout add "
                            + " ".join(dirs))
            plan += [f"      git -C {cpy_s} show HEAD:{rel} > {cpy_s}/{rel}"
                     for rel in files]
            raise Fail(
                f"文档引用了 Doc/ 之外的 {n} 处文件，但它们不在（稀疏克隆没取到）。\n"
                "  Sphinx **不会因此报错**：literalinclude / include 缺失 → "
                "`.tex` 里什么都不写 → PDF 里整节空白；\n"
                "  image / figure 缺失 → 反斜杠路径进 .tex → 未定义控制序列 → "
                "latexmk 退出码 12。\n"
                "  已自动补过一轮（目录走 sparse-checkout add / 单文件走 "
                "git show 按需拉 blob）；仍差上面列出的这几处，"
                "多半是 GitHub 代理断流 —— 直接重跑本步即可，或手动执行：\n"
                + "\n".join(plan))
        self.rep.log("Doc 越界引用自检：都齐", level="ok")

    #: 真正的 SVG 插图指令：`.. image:: x.svg` / `.. figure:: x.svg`。
    #: ★ 只认这种：`.. raw:: html` + `:file: a.svg` 是 HTML 专用的，LaTeX 阶段
    #:   根本不碰它（3.13 的 howto/logging.rst 就是这种写法，所以 3.13 从不触发
    #:   cairosvg —— 这就是「同一台机器，3.13 好好的、3.14/3.15 全崩」的全部原因）。
    _SVG_IMAGE_RE = re.compile(r"^\s*\.\.\s+(?:image|figure)::\s*\S+\.svg\s*$",
                               re.I | re.M)

    def _svg_images(self) -> list[str]:
        """文档里**会被转成 PDF** 的 SVG 图（返回相对 `Doc/` 的路径）。"""
        if self.doc is None or not self.doc.is_dir():
            return []
        hits: list[str] = []
        try:
            files = list(self.doc.rglob("*.rst"))
        except OSError:
            return []
        for p in files:
            try:
                if self._SVG_IMAGE_RE.search(read_text_safe(p)):
                    hits.append(str(p.relative_to(self.doc)))
            except (OSError, ValueError):
                continue
        return hits

    def _sphinx_major(self) -> int:
        """构建 venv 里的 Sphinx 主版本号（问不到就按 99 处理 = 当新版本）。"""
        rc, out = self.capture([str(self.vp), "-c", "import sphinx;print(sphinx.__version__)"])
        m = re.match(r"(\d+)", (out or "").strip())
        return int(m.group(1)) if m else 99

    def _ensure_mo_files(self) -> None:
        """把源目录 `locales/` 下的 .po 预编译成 .mo —— **Sphinx 3.x 必须这么做**。

        ★ 现象（2026-11-03 实测 3.10 + Sphinx 3.4.3）：正文**整册英文**，
          0 条 warning，验收报告全绿（页数、书签、索引都正常），
          只有封面和页眉是中文（那是步骤 6b 硬改的），看着像「只是标题没翻译」。
        ★ 真因在日志的第 3、5 行，两行连着看才看得懂：
              loading translations [zh_CN]... done          ← 先加载翻译
              building [mo]: targets for 495 po files ...   ← 之后才编译 .po
              writing output... locales/zh_CN/.../xxx.mo    ← 而且写进了 **outdir**
          Sphinx 3.x 的 MOFilesBuilder 把 .mo 生成到 `build/latex/locales/…`，
          而翻译是从 **srcdir** 的 `locales/` 读的 —— 两边不是一个地方；
          加上「先加载、后编译」的顺序，本轮永远读不到刚编出来的 .mo。
          Sphinx 4.0 起改成写源码目录，所以 3.13+（8.x）一直正常 —— 只有老版本中招。
        ★ 解法：用 babel（Sphinx 自带依赖）直接把 .po 编到源目录旁边，
          让它 `loading translations` 时就有 .mo 可读。
        """
        if self.doc is None:
            return
        loc = self.doc / "locales"
        if not loc.is_dir() or not any(loc.rglob("*.po")):
            return
        script = (
            "import sys, pathlib\n"
            "try:\n"
            "    from babel.messages import mofile\n"
            "    from babel.messages.pofile import read_po\n"
            "except ImportError:\n"
            "    print('NO_BABEL'); sys.exit(0)\n"
            "root = pathlib.Path(sys.argv[1]); n = skip = bad = 0\n"
            "for po in root.rglob('*.po'):\n"
            "    mo = po.with_suffix('.mo')\n"
            "    if mo.is_file() and mo.stat().st_mtime >= po.stat().st_mtime:\n"
            "        skip += 1\n"
            "        continue\n"
            "    try:\n"
            "        with po.open('rb') as f: cat = read_po(f)\n"
            "        with mo.open('wb') as f: mofile.write_mo(f, cat)\n"
            "        n += 1\n"
            "    except Exception:\n"
            "        bad += 1\n"
            "print(f'COMPILED {n} SKIPPED {skip} BAD {bad}')\n"
        )
        rc, out = self.capture([str(self.vp), "-c", script, str(loc)],
                               section="mo-build.log")
        if "NO_BABEL" in (out or ""):
            self.rep.log("venv 里没有 babel，跳过 .mo 预编译 —— 老版本会出英文正文", level="warn")
            return
        last = (out or "").strip().splitlines()[-1] if (out or "").strip() else ""
        self.rep.log(f"预编译 .po → .mo（Sphinx 3.x 的 .mo 会写错目录，先补上）："
                     f"{last or '无输出'}", level="ok")

    def _cairo_probe(self) -> tuple[bool, str]:
        """在**构建 venv** 里试一次 `import cairosvg`（结果缓存，失败给最后一行）。"""
        if self._cairo_state is not None:
            return self._cairo_state
        if not self.vp:
            self._cairo_state = (True, "")
            return self._cairo_state
        try:
            p = subprocess.run(
                [str(self.vp), "-c", "import cairosvg"],
                env=self.env, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
                creationflags=CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            # 探针自己出问题不该拦住构建：真坏了步骤 6 会给真错误
            self._cairo_state = (True, "")
            return self._cairo_state
        if p.returncode == 0:
            self._cairo_state = (True, "")
        else:
            lines = (p.stderr or p.stdout or "").strip().splitlines()
            self._cairo_state = (False, lines[-1] if lines else f"退出码 {p.returncode}")
        return self._cairo_state

    def step6(self) -> str:
        self.need_venv()
        assert self.doc
        conf = self.doc / "conf.py"
        if not conf.is_file():
            raise Fail(f"找不到 {conf}")
        self._guard_doc_refs()

        # ★★ conf.py 的 SVG 转换器：rsvg → cairosvg ★★
        #   conf.py 的可选扩展里写死 'sphinxcontrib.rsvgconverter'，它要调外部程序
        #   rsvg-convert（Windows 上没有），结果是只留一行软告警、SVG 原样进 LaTeX，
        #   之后报 `! LaTeX Error: Cannot determine size of graphic in xxx.svg`，
        #   c-api.pdf 直接编不过。
        #
        # ★★ 判据是「这一版的 Doc 里**到底有没有 SVG**」，不是「conf.py 里有没有
        #   这串字」—— 后者会把 3.10~3.12 整批误杀（2026-11-03 实测）：
        #     3.10 的 conf.py 只有 236 行，压根没有 SVG 转换器；
        #     3.12 的 `_OPTIONAL_EXTENSIONS` 只有 `sphinxext.opengraph`；
        #     `sphinxcontrib.rsvgconverter` 是 3.13 才随 SVG 插图一起加进来的。
        #   老版本既没有 SVG、也不需要转换器，硬要求「必须改名成功」= 步骤 6 必失败。
        txt = read_text_safe(conf)
        old = "sphinxcontrib.rsvgconverter"
        new = "sphinxcontrib.cairosvgconverter"
        svgs = self._svg_images()
        if old in txt:
            conf.write_text(txt.replace(old, new), encoding="utf-8")
            self.rep.log(f"conf.py：{old} → {new}", level="ok")
        elif new in txt:
            self.rep.log("conf.py 已经是 cairosvgconverter，跳过改写", level="meta")
        elif svgs:
            # 有 SVG 却没注册转换器（上游刚引入 SVG 的那一版会这样）→ 补一行，
            # 否则 SVG 原样进 LaTeX，`Cannot determine size of graphic` 会打死一整册。
            conf.write_text(
                txt + "\n# 由本工具补充：SVG 转 PDF（rsvg-convert 在 Windows 上没有）\n"
                      f"extensions.append({new!r})\n", encoding="utf-8")
            self.rep.log(f"conf.py 里没有 SVG 转换器，已追加 extensions.append({new!r})",
                         level="warn")
        else:
            self.rep.log("本版本的 Doc 没有 SVG 插图（conf.py 里也没有转换器），无需改写",
                         level="meta")
        if svgs and new not in read_text_safe(conf):
            raise Fail(f"文档里有 {len(svgs)} 处 SVG 插图，却没能把它写进 conf.py：\n"
                       f"  {new}\n  请手工看 {conf} 里的 extensions 是怎么写的。")

        # ★★ gettext_compact —— 老版本 conf.py 缺这一行，后果是整册英文 ★★
        #   Sphinx 默认 gettext_compact = True，含义是「同一顶层目录共用一份 .mo」
        #   （`library/*` 全去找 `locales/zh_CN/LC_MESSAGES/library.mo`）。
        #   而 python-docs-zh-cn 是**每页一个 .po**（`library/array.po`），
        #   于是 Sphinx 一个 catalog 都匹配不上 —— 正文全英文、**0 条 warning**、
        #   进度 100%、页数书签索引全都正常。实测 3.10 的 conf.py 只有 236 行、
        #   压根没有这一项；3.13+ 才有，所以此前从没暴露。
        #   幂等：已经写了这行的版本原样不动。
        txt2 = read_text_safe(conf)
        if "gettext_compact" not in txt2:
            conf.write_text(
                txt2 + "\n# 由本工具补充：译文是**每页一个** .po/.mo。老版本 conf.py 没写\n"
                       "# 这一项时 Sphinx 默认 True（每个顶层目录共用一份 .mo），会一个都\n"
                       "# 匹配不上 → 整册英文且零 warning。\ngettext_compact = False\n",
                encoding="utf-8")
            self.rep.log("conf.py 里没有 gettext_compact，已补上 = False"
                         "（不加这行，逐页译文一个都匹配不上，正文会整册英文）",
                         level="warn")

        # ★★ 开编之前先确认「SVG → PDF」这条路真能走（2026-10-23 加）★★
        #   以前这里是裸跑 sphinx：CairoSVG 缺 cairo 运行库时，
        #   `cairosvgconverter.is_available()` 里 `import cairosvg` 抛的是 **OSError**
        #   （它只 except ImportError），冒泡成未捕获异常 → sphinx-build 退出码 2。
        #   实测 3.14.9 / 3.15.1 各白跑 17 分钟，最后只留一段 Python traceback。
        #   现在提前几秒拦下，并给出能照做的三条办法。
        if self.cairo_dir:
            in_path = self.cairo_dir.lower() in self.env.get("PATH", "").lower()
            self.rep.log(f"cairo 运行库：{self.cairo_dir}"
                         f"（{'已加进子进程 PATH' if in_path else '⚠ 但不在子进程 PATH 里'}）",
                         level="meta" if in_path else "warn")
        if svgs:          # 上面判断 conf.py 时已经扫过一次，这里直接用
            cairo_ok, why = self._cairo_probe()
            if not cairo_ok:
                if "No module named" in why:
                    raise Fail(
                        "构建 venv 里没有 cairosvg（步骤 4 的依赖没装全）：\n"
                        f"  {why}\n"
                        "  重跑步骤 4 即可（图形界面里点这个版本的「重试」也走这条路）。")
                lst = "、".join(svgs[:3]) + (f" 等 {len(svgs)} 个文件" if len(svgs) > 3 else "")
                raise Fail(
                    "文档里有 SVG 插图，但构建 venv 用不了 cairosvg —— "
                    "**cairo 运行库缺失**：\n"
                    f"  {why}\n"
                    "  为什么会把整轮打死：sphinxcontrib-cairosvgconverter 的 "
                    "is_available() 只捕获 ImportError，而 cairocffi 找不到 "
                    "libcairo-2.dll 抛的是 OSError → 冒泡成未捕获异常 → "
                    "sphinx-build 退出码 2（以前要白跑十几分钟才看到）。\n"
                    f"  需要转换的图：{lst}\n"
                    "  三个办法（任选一条，做完 **重启本程序**）：\n"
                    "    ① 把含 libcairo-2.dll 的目录加进系统 PATH"
                    "（本机现成的一份：C:\\Program Files\\gnuplot\\bin）；\n"
                    "    ② 装 GTK3 Runtime（自带 libcairo-2.dll），同样把它加进 PATH；\n"
                    "    ③ 设环境变量 PDFBUILDER_CAIRO_DIR=<那个目录>，"
                    "本程序会自动把它加进子进程 PATH（不用改系统）。")
            self.rep.log(f"SVG 转换器可用（{len(svgs)} 个 rst 带 SVG 插图）", level="ok")
        else:
            self.rep.log("文档里没有 `.. image:: *.svg`，这一步不需要 cairo", level="meta")

        # ★ Sphinx 3.x 的 .mo 会编到 outdir（不是源目录），本轮加载时读不到 →
        #   正文整册英文、零 warning。构建前先把 .mo 补到源目录（见 _ensure_mo_files）。
        if self._sphinx_major() < 4:
            self._ensure_mo_files()

        # ⚠️ 不要加 Doc/Makefile 里的 --fail-on-warning：翻译有 fuzzy 条目会直接中断
        rc = self.run([str(self.vp), "-m", "sphinx", "-b", "latex",
                       "-d", "build/doctrees", "-j", self.cfg.sphinx_jobs(),
                       "-D", f"language={self.cfg.lang}",
                       ".", "build/latex"],
                      cwd=self.doc, section="latex-build.log")
        self.latex = self.doc / "build" / "latex"
        if not self.latex.is_dir():
            raise Fail(f"没有生成 {self.latex}，看 {self.root / 'latex-build.log'}")

        roots = list_root_tex(self.latex)
        svg_n = len(list(self.latex.glob("*.svg")))
        self.rep.log(f"生成 .tex：{len(list(self.latex.glob('*.tex')))} 个"
                     f"（其中带 \\documentclass 的册子 {len(roots)} 个）", level="ok")
        self.rep.log(f"残留 .svg：{svg_n} 个（应为 0）", level="ok" if svg_n == 0 else "err")
        if rc != 0:
            raise Fail(f"LaTeX 构建失败（退出码 {rc}），看 {self.root / 'latex-build.log'}")
        if svg_n != 0:
            raise Fail(f"还有 {svg_n} 个 SVG 没被转成 PDF：SVG 转换器没生效，"
                       f"c-api.pdf 会编不过")
        if not roots:
            raise Fail("一个带 \\documentclass 的 .tex 都没有，latex_documents 没生效")
        return f"{len(roots)} 个册子 .tex 已生成"

    # =======================================================================
    #  步骤 6b —— 封面标题中文化
    # =======================================================================
    def step6b(self) -> str:
        if not self.cfg.localize_titles:
            self.rep.log("按设置跳过封面标题中文化", level="warn")
            return "已跳过"
        self.need_venv()
        assert self.latex
        rc, out = self.tool("localize-titles", loct_main, ["."], cwd=self.latex,
                            section="title-localize.log")
        if rc != 0:
            raise Fail(f"封面标题中文化失败，看 {self.root / 'title-localize.log'}")
        # 复核：把改完的 \title 打出来（\title 同时被 sphinxmanual.cls 用于页眉）
        shown = 0
        for name in ("whatsnew", "tutorial", "using", "reference", "library",
                     "extending", "c-api", "installing", "faq", "builtins",
                     "howto-perf_profiling"):
            f = self.latex / f"{name}.tex"
            if not f.is_file():
                continue
            m = re.search(r"\\title\{(.*?)\}", read_text_safe(f, 200000), re.S)
            if m:
                self.rep.log(f"  {name:<22} → {m.group(1)}", level="meta")
                shown += 1

        # 反查正文里的中文。踩过的坑：把「语言」设成 en，11 册标题照样被改成中文，
        # 界面全绿、日志也没有一条 "! " 错误，但 38 册正文全是英文；
        # 而页眉那点中文因为 FreeSans 没有汉字字形被静默丢掉，只在日志里刷
        # `Missing character: There is no 安 (U+5B89) in font [FreeSansBold.otf]`。
        stats = [(len(CJK_RE.findall(read_text_safe(f))), f.stem)
                 for f in list_root_tex(self.latex)]
        cjk_total = sum(n for n, _ in stats)
        names = [name for n, name in stats if n < CJK_MIN_PER_BOOK]

        # ★★ 「整批都没有中文」必须**当场打死**，不能只记一行日志 ★★
        #   2026-11-03 实测（3.10）：2319 页全英文、**0 条 warning**、
        #   验收报告全绿（册数/页数/书签/索引全对），只有封面和页眉是中文
        #   —— 因为老版本 conf.py 缺 gettext_compact，逐页 .po 一个都没匹配上。
        #   那轮就是这么「绿着」把英文 PDF 发出去的。判据分两档：
        #     · 汉字总量极低（< 2000）且过半册子近乎无中文  → 整批没接上 = 硬失败
        #     · 只有个别册中文少                          → 上游没译，正常，只 warn
        if stats and str(self.cfg.lang).lower().startswith("zh") \
                and cjk_total < 2000 and len(names) > len(stats) / 2:
            raise Fail(
                f"译文没接上：{len(names)}/{len(stats)} 册的正文几乎没有中文"
                f"（整批合计只有 {cjk_total} 个汉字）。\n"
                "  这不是「上游没译」，是 .po 一个都没被 Sphinx 用上。三个已知原因：\n"
                "    ① conf.py 缺 `gettext_compact = False` —— 3.10/3.11 的 conf.py\n"
                "       没有这一项，Sphinx 默认 True 会去找 `library.mo`，\n"
                "       而译文是每页一个（`library/array.mo`）；\n"
                "    ② .mo 不存在 —— Sphinx 3.x 把自己的 .mo 编到 outdir，\n"
                "       翻译却从 srcdir 读（本程序已用 babel 预编译绕过）；\n"
                "    ③ 「语言」不是 zh_CN，或译文分支与该版本对不上。")

        if names:
            self.rep.log(f"  注：{len(names)} 册正文中文很少（{'、'.join(names[:5])}"
                         f"{' 等' if len(names) > 5 else ''}）——上游 zh-CN 尚未翻译，属正常",
                         level="warn")
        return f"封面/页眉标题已中文化（{shown} 册）"

    # ------------------------------------------------------- 步骤 7 的并发编译
    def _resolve_jobs(self, n: int) -> int:
        """并发数：配置 `jobs` 优先，0/负 = 自动（CPU 核数-1，上限 AUTO_JOBS_CAP）。"""
        try:
            j = int(getattr(self.cfg, "jobs", 0) or 0)
        except (TypeError, ValueError):
            j = 0
        if j <= 0:
            j = min(max((os.cpu_count() or 4) - 1, 1), AUTO_JOBS_CAP)
        return max(1, min(j, max(n, 1)))

    def _run_book_tex(self, tex: Path, latex: Path, logf: Path,
                      append: bool = False) -> int:
        """在工作线程里跑一册的 latexmk；整份输出写进 `logf`，返回退出码。

        `append=True` 时把输出**追加**到 `logf`（重试时用 —— 头一遍的日志要留着，
        否则重试成功后就看不出「第一次到底为什么失败」了）。

        ★ 为什么不复用 `self.run()`：它的分节日志是**全局单例**（`_sec_fp`），
          并发时几册会轮流把句柄切走、写出来的日志彻底交错。这里改成**每册一个
          独立日志文件**，最后由 `_merge_book_logs()` 按册序拼回 pdf-build.log。

        ★★ latexmk 必须用 `-e` 覆盖 `$makeindex` ★★
          latexmkrc 里是 `$makeindex = 'internal xindy ...'`（不带 -s python.ist），
          xindy 吃不了 makeindex 格式的 python.ist → 返回 256 → latexmk 在第 2 遍前
          中止、退出码 12 → PDF 看着正常，其实只有第 1 遍：目录空白、满屏 '??'。
          `-e` 在 `-r latexmkrc` 之后求值，所以能覆盖。
          覆盖成的不再是裸 makeindex，而是「makeindex + 修 .ind」的同名脚本
          （tools/fix-index.py 拷成 makeindex-fix.py）：索引页码要变成超链接，
          必须在 xelatex 读到 .ind **之前**就带 \\hyperpage，而 latexmk 的次序是
          xelatex → makeindex → xelatex → xelatex。
        ⚠️ 命令里只能出现 ASCII：`-e` 的字符串 latexmk 按 UTF-8 解析，路径带中文
          （…/Python 文档/…）会报 `Malformed UTF-8 character (fatal)`。所以脚本先
          拷一份到 latex 目录（ASCII 名 makeindex-fix.py），再用 PATH 里的 python 启动。
        """
        name = tex.stem
        # ★ 不再手删中间产物 ★（2026-09-27 改）
        #   以前这里 unlink 掉 pdf/aux/toc/out/ind/ilg/idx/log/fdb_latexmk/fls
        #   十个后缀，是为了防 latexmk 认为「已是最新」而跳过重排（改了 .rst 却
        #   编不出新内容）。但每册 10 个 × 38 册 = **380 次删除**，在受管环境里会
        #   撞上「批量删除保护」（单个 turn 累计 50 次就要人工确认）：后台跑直接被
        #   拦，每册都报 `SAFE_DELETE_BULK_CONFIRM_REQUIRED`，整轮编译判失败。
        #   改用 latexmk 自带的 `-gg`：忽略依赖数据库、强制把各步骤重跑一遍
        #   （.aux/.toc/.idx 的删与重建都在 latexmk 进程内部完成，不经过调用方），
        #   效果与手删等价，却不会产生删除风暴。
        #   ⚠️ 旧 .pdf 由 latexmk 覆盖；只有它真的失败时旧 PDF 才会留下，而收尾
        #      「PDF 存在且非空」的判据仍然有效。
        # ★ 索引样式文件不写死 ★ Sphinx 从 1.x 到 8.x 一直叫 python.ist，但这是它的
        #   内部命名，不是承诺。3.4.3 这种五年老的版本上万一换了名，写死 `-s python.ist`
        #   会让 makeindex 直接失败 → .ind=0 → 每册都没有索引（且 PDF 看着「正常」）。
        #   这里按目录里的实际文件取：优先 python.ist，否则取第一个 *.ist，都没有就不加 -s。
        ist = ""
        if (latex / "python.ist").is_file():
            ist = "-s python.ist "
        else:
            cand = sorted(latex.glob("*.ist"))
            if cand:
                ist = f"-s {cand[0].name} "
                self.rep.log(f"索引样式文件不是 python.ist，改用 {cand[0].name}（本版本 Sphinx 换过名）",
                             level="warn")
        cmd = [self._tool("latexmk"),                      # ★ 绝对路径，别靠 PATH
               "-pdf", "-gg", "-file-line-error", "-r", "latexmkrc",
               "-e", "$makeindex = q{python makeindex-fix.py %O "
                     + ist + "-o %D %S};",
               tex.name]
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(latex), env=self.env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                bufsize=1, creationflags=CREATE_NO_WINDOW,
                start_new_session=not IS_WIN)
        except OSError as e:
            raise Fail(f"无法启动 latexmk：{e}") from e
        with self._io_lock:
            self._procs.add(proc)
        try:
            with logf.open("a" if append else "w",
                           encoding="utf-8", errors="replace") as fh:
                assert proc.stdout is not None
                for raw in proc.stdout:
                    # 同上：进日志前先剥 ANSI（latexmk/perl 一般不着色，
                    # 但它拉起的 xelatex 在某些 TeX 发行版上会）。
                    line = strip_ansi(raw.rstrip("\r\n"))
                    fh.write(line + "\n")
                    if self.cfg.verbose_log or NOTABLE.search(line):
                        with self._io_lock:
                            self.rep.log(line, level="raw")
                fh.flush()
            proc.wait()
        finally:
            with self._io_lock:
                self._procs.discard(proc)
        return proc.returncode

    def _merge_book_logs(self, book_log: dict[str, Path],
                         roots: list[Path]) -> None:
        """把并发时各册的 `pdf-build-<册名>.log` 按册序拼回 `pdf-build.log`。

        拼完把分册日志**挪进 `pdf-build-parts/` 留档**（不是删）：
        · 内容已经全在 pdf-build.log 里，但分册文件另有价值 —— 排查某一册时
          只需读它自己的日志，不用在几 MB 的合并日志里翻。
        · 为什么用 `os.replace` 而不是 `unlink()`：38 册的删除会撞上受管环境的
          「批量删除保护」（turn 内累计 50 次就要确认），后台跑会被整轮拦下。
          rename 不触发该保护。

        串行模式（jobs=1）下 `book_log` 里也是这些文件，逻辑一样。
        """
        self._section("pdf-build.log", mode="w")   # 现在才正式打开（内容全新）
        with self._io_lock:
            fp = self._sec_fp
            if fp is None:
                return
            for tex in roots:
                src_log = book_log.get(tex.stem)
                fp.write(f"\n===== {tex.stem} =====\n")
                if src_log and src_log.is_file():
                    try:
                        with src_log.open(encoding="utf-8", errors="replace") as inp:
                            shutil.copyfileobj(inp, fp)
                    except OSError:
                        pass
            try:
                fp.flush()
            except Exception:
                pass
        try:
            parts = self.root / "pdf-build-parts"
            parts.mkdir(exist_ok=True)
        except OSError:
            return
        for src_log in book_log.values():
            if not src_log.is_file():
                continue
            try:
                os.replace(src_log, parts / src_log.name)
            except OSError:
                pass

    # =======================================================================
    #  步骤 7 —— 编译 PDF
    # =======================================================================
    def step7(self) -> str:
        self.need_venv()
        assert self.latex
        latex = self.latex
        if not (latex / "latexmkrc").is_file():
            raise Fail(f"找不到 {latex / 'latexmkrc'}（Sphinx 依据 latex_engine=xelatex 生成）")
        # ★ 从 --only 7 / 重试之类的中途重跑进来时没走 step4，self.env 还是
        #   __init__ 那份 —— 首建场景里 PATH 缺 venv\Scripts（见 step4 里的说明）。
        #   这里兜底重建一次（幂等），保证 `python makeindex-fix.py` 一定解析到
        #   venv 解释器。
        self.env = self._make_env()
        # ★ 从--only 8 之类的中途重跑进来时，也要拦一次（否则白编 13 分钟再挂）
        self._guard_doc_refs()

        # ★ 待编册子：只取带 \documentclass 的根文件，按体积**降序**（大册先开工）
        #   ★ 2026-10-31 改（原来是升序「小册先出」）：这是典型的 LPT 调度问题。
        #   升序会把最大的那册（05 标准库，2434 页）留到最后才提交，等它开工时
        #   别人都干完了 —— 实测 3.15 那轮步骤 7 用了 912s，其中 428s（47%）是
        #   「只有 1 册在跑、另外 4 个 slot 全空」。降序后大册从第 0 秒就占一个
        #   slot 跑到底，其余 slot 同时把 38 册小册消化掉，墙钟 ≈ 大册自己的耗时。
        #   ⚠️ bash 里必须写 /usr/bin/sort —— Windows 的 C:/WINDOWS/system32/sort.exe
        #      在 PATH 里更靠前，不认 -n 且不吐 stdout，整条管道会静默变空。
        #      Python 的 sorted(key=size) 天然没有这个问题。
        roots = list_root_tex(latex)
        # ★ 只重编指定册（`--books reference` / 配置「只编这几册」）★
        #   补一条稀疏路径、改一个 .rst，往往只影响一两册；全编 39 册要四十分钟，
        #   而这些册的 PDF 步骤 8 会按同名覆盖，其余册的成品保持原样、不受影响。
        want = [s.strip() for s in
                (self.cfg.books or "").replace("，", ",").split(",") if s.strip()]
        if want:
            matched = {p.stem for p in roots
                       if any(w == p.stem or w in p.stem for w in want)}
            miss = [w for w in want if not any(w in m or w == m for m in matched)]
            if miss:
                raise Fail(
                    "只编这几册的名单里有对不上的：" + "、".join(miss) + "\n"
                    f"  可用的册名（共 {len(roots)} 个）："
                    + "、".join(p.stem for p in roots)
                    + "\n  提示：这里用的是 .tex 的文件名（reference / library / tutorial"
                      " / whatsnew / c-api …），不是中文册名。")
            roots = [p for p in roots if p.stem in matched]
            self.rep.log("★ 只编这几册：" + "、".join(p.stem for p in roots)
                         + "（其余册的成品不在本次范围内，不会被改动）", level="warn")
        roots.sort(key=lambda p: p.stat().st_size, reverse=True)
        self.rep.log(f"待编 {len(roots)} 册（按体积降序：最大那册先开工，"
                     f"其余 slot 同时吃小册）", level="info")

        # ★ 分节日志**先留空**：`_run_book_tex()` 会把每册的原始输出发给界面，
        #   而 `_TeeReporter` 会顺手把界面消息也写进「当前分节日志」—— 并发时几册
        #   同时写同一个 pdf-build.log 就交错成一锅粥。所以跑编译期间不挂分节日志
        #   （原始输出仍然全进 gui-build.log），结束后由 `_merge_book_logs()`
        #   按册序一次性写出干净的 pdf-build.log。
        section = "pdf-build.log"
        self._section("")

        # ★ 把「修索引」的**转发器**放到 latex 目录（ASCII 文件名），给 latexmk 当
        #   $makeindex 用。为什么非要放文件、为什么是转发器而不是整份脚本：
        #   见 `_emit_makeindex_fix()` 的说明 —— 一句话，latexmk 只能调外部命令，
        #   但实现本身仍然只有主程序里那一段。
        _emit_makeindex_fix(latex / "makeindex-fix.py")
        self.rep.log("索引修复脚本已就位：makeindex-fix.py（替代裸 makeindex）", level="meta")

        failed: list[str] = []
        bad_books: set[str] = set()          # 日志里有汉字缺字形的册子
        idx_books: list[str] = []            # 生成了索引的册子
        total = len(roots)
        t_all = time.monotonic()

        # ── 并发编译 ────────────────────────────────────────────────────────
        # ★ 2026-09-27 改：以前是 `for tex in roots: latexmk …` 一册一册串行，
        #   全编 38 册要 35~40 分钟。latexmk 全是 CPU 密集的外部进程，彼此**不共享
        #   任何中间文件**（每册有自己的 .aux/.toc/.idx/.ind/.log，都按 jobname 区分），
        #   共享的只有只读的 .sty 与图片，所以用线程池并发是安全的，18 核上接近线性提速。
        #   ⚠️ 唯一被并发破坏的是**日志**：`self.run()` 的分节日志是全局单例，几册会
        #     轮流把句柄切走。所以这里不走 run()，改成每册一个 pdf-build-<册名>.log，
        #     跑完再按册序拼回 pdf-build.log（内容与串行时一模一样）。
        jobs = self._resolve_jobs(total)
        if jobs > 1:
            self.rep.log(f"并发编译：{jobs} 册同时跑（共 {total} 册，CPU "
                         f"{os.cpu_count()} 核）；各册日志先分别落盘，"
                         f"结束后按册序合并进 pdf-build.log", level="info")
        book_log: dict[str, Path] = {}
        results: dict[str, tuple[int, float]] = {}
        done = 0

        def compile_one(tex: Path) -> tuple[str, int, float]:
            """跑一册（可能在工作线程里）。返回 (册名, 退出码, 用时秒)。"""
            name = tex.stem
            logf = self.root / f"pdf-build-{name}.log"
            self.rep.check_cancel()
            with self._io_lock:
                self.rep.log(f"[{now_hms()}] 开始编译 {name}", level="step")
            t0 = time.monotonic()
            try:
                rc = self._run_book_tex(tex, latex, logf)
            finally:
                book_log[name] = logf
            return name, rc, time.monotonic() - t0

        if jobs <= 1:                                  # 串行（`--jobs 1` 的退路）
            for tex in roots:
                nm_, rc_, secs_ = compile_one(tex)
                results[nm_] = (rc_, secs_)
                done += 1
                self.rep.sub(8, done, total, tex.stem)
                self.rep.log(f"      [{done}/{total}] {nm_} 结束"
                             f"（退出码 {rc_}，用时 {secs_:.1f}s）", level="meta")
        else:
            with ThreadPoolExecutor(max_workers=jobs, thread_name_prefix="tex") as ex:
                futs = {ex.submit(compile_one, tex): tex for tex in roots}
                for fut in as_completed(futs):
                    tex = futs[fut]
                    try:
                        nm_, rc_, secs_ = fut.result()
                    except Cancelled:
                        for f2 in futs:                # 没开跑的先取消
                            f2.cancel()
                        raise
                    except Exception as e:             # noqa: BLE001
                        self.rep.log(f"      {tex.stem} 编译中断：{e}", level="err")
                        results[tex.stem] = (-1, 0.0)
                        continue
                    results[nm_] = (rc_, secs_)
                    done += 1
                    self.rep.sub(8, done, total, tex.stem)
                    self.rep.log(f"      [{done}/{total}] {nm_} 结束"
                                 f"（退出码 {rc_}，用时 {secs_:.1f}s）", level="meta")

        # ── 失败册串行重试（★ 偶发故障的兜底）──────────────────────────────
        # ★★ 为什么必须要有这一步 ★★
        #   并发编译实测出现过 `xelatex.exe: fwrite: Broken pipe`：xelatex 写到
        #   某一页时管道断掉、进程返回 1，latexmk 于是报
        #     `pdflatex: Command for 'pdflatex' gave return code 1` + 退出码 12，
        #   而那一册的 `.log` 里**一条 LaTeX 错误都没有**（TeX 自己的诊断是
        #   “Broken pipe”，与 .rst 内容无关）。3.15 实测：39 册里 2 册中招
        #   （howto-sorting / howto-logging-cookbook），而且落在**不同批次**；
        #   把这两册单独重编，一次就成功 —— 典型的偶发（进程/管道/杀软实时扫描
        #   17 MB 的 .tex 与几百 MB 的中间文件）。
        #   这类失败不该让用户自己去发现「重跑一次就好了」，所以这里自动兜。
        #   思路与 `merge-pdf.py` 那个 WinError 5 退避重试一致。
        # ⚠️ 重试**串行**跑：并发本来就是把负载摊开，重试时让路反而更容易过。
        # ⚠️ 触发判据 = **本次运行退出码非 0** 或 **没出 PDF**。
        #   ★ 为什么不能只看「PDF 在不在」：上一轮留下的旧 PDF 还在，某册这轮
        #     编崩了也会被判「成功」—— 重试逻辑就形同虚设（这正是它一开始的漏洞）。
        #   ★ 为什么不能只看「退出码」：latexmk 对「最后一页越界/rerun 未收敛」
        #     这类长尾会保守地返回非 0，但 PDF 完全可用 —— 所以**最终验收**仍以
        #     「PDF 存在且非空」为准（见下面 `pdf_n < tex_n` 那两行）。
        RETRY_ROUNDS = 2
        for attempt in range(1, RETRY_ROUNDS + 1):
            if attempt == 1:
                # 第一轮：退出码非 0 **或** 没出 PDF 都算「这次没编干净」，给一次机会。
                bad = [t for t in roots
                       if results.get(t.stem, (0, 0.0))[0] != 0
                       or not self.pdf_pages(latex / f"{t.stem}.pdf")]
            else:
                # ★ 第二轮只追「连 PDF 都没有」的。只是退出码非 0、PDF 已经好好的
                #   册子再全量编一遍纯属浪费 —— `library` 一册就要 8 分钟，
                #   而它的 PDF 已经可用（最终验收本来就以「PDF 存在且非空」为准）。
                bad = [t for t in roots
                       if not self.pdf_pages(latex / f"{t.stem}.pdf")]
            if not bad:
                break
            self.rep.log(f"      {len(bad)} 册这次没编成，串行重试（第 "
                         f"{attempt}/{RETRY_ROUNDS} 轮）："
                         + "、".join(t.stem for t in bad), level="warn")
            for tex in bad:
                self.rep.check_cancel()
                logf = self.root / f"pdf-build-{tex.stem}.log"
                with logf.open("a", encoding="utf-8", errors="replace") as fh:
                    fh.write(f"\n===== 第 {attempt} 轮串行重试 =====\n")
                t0 = time.monotonic()
                rc = self._run_book_tex(tex, latex, logf, append=True)
                secs = time.monotonic() - t0
                results[tex.stem] = (rc, secs)
                pages = self.pdf_pages(latex / f"{tex.stem}.pdf")
                if pages and rc == 0:
                    self.rep.log(f"      重试后 OK   {tex.stem}  {pages} 页"
                                 f"（退出码 0，用时 {secs:.1f}s）", level="ok")
                elif pages:
                    # ★ 别把「有 PDF 但仍有告警」写成 OK：受控故障测试里注入一个
                    #   未定义控制序列，PDF 照样出得来、latexmk 仍返回 12 ——
                    #   这类要如实说出来，否则日志会给出「一切正常」的假象。
                    self.rep.log(f"      重试后 PDF 已出（{pages} 页），"
                                 f"但 latexmk 仍有告警（退出码 {rc}）—— "
                                 f"看 pdf-build-{tex.stem}.log", level="warn")
                else:
                    self.rep.log(f"      重试后仍失败  {tex.stem}"
                                 f"（退出码 {rc}）", level="err")

        # ── 逐册收尾：页数 / 索引自检 / 缺字形（在主线程，很快）────────────
        for k, tex in enumerate(roots, 1):
            name = tex.stem
            rc, secs = results.get(name, (-1, 0.0))
            self.rep.check_cancel()
            self.rep.sub(8, k, total, name)
            pages = self.pdf_pages(latex / f"{name}.pdf")
            if pages:
                self.rep.log(f"      OK   {name}  {pages} 页"
                             f"（latexmk 退出码 {rc}，用时 {secs:.1f}s）", level="ok")
            else:
                self.rep.log(f"      失败  {name}  latexmk 退出码 {rc}，没出可用 PDF",
                             level="err")
                failed.append(name)

            # 索引自检（就地看 .ind，不重编）：分组标题 + 页码超链接 + 断点是否齐了
            ind = latex / f"{name}.ind"
            if ind.is_file() and ind.stat().st_size > 0:
                links, syms, bad_ind, brk, longest = self._ind_summary(ind)
                idx_books.append(name)
                # ★ brk == 0 只在「这本确实有长条目」时才算异常：纯英文 howto 册
                #   本来就没有超过栏宽（≈42 字符）的条目，断点天然是 0，不能报警。
                need_brk = longest > 42
                lvl = "ok" if (links and syms == 1 and bad_ind == 0
                               and (brk or not need_brk)) else "warn"
                self.rep.log(f"      索引：{links} 个页码链接"
                             f"　非字母标题 {'有' if syms else '无'}"
                             f"　断点 {brk}"
                             f"　最长条目 {longest} 字符"
                             f"　非法字节 {bad_ind}", level=lvl)
                if need_brk and not brk:
                    self.rep.log("      注意：有长条目却一个断点都没有 → 会长到压到隔壁栏"
                                 "（makeindex 没走 makeindex-fix.py 那个转发器）", level="warn")

            # 顺手看一眼 .log 里的缺字告警：汉字没字形 = 字体链里没有 CJK 字体。
            # 正常 zh_CN 构建里这一项是 0（含中文的册子由 Fandol 兜底）；
            # 一旦成片出现，几本都是「语言没设成 CJK」，封面中文会被整段丢掉。
            log = latex / f"{name}.log"
            if log.is_file():
                miss = [c for c in MISSING_CHAR_RE.findall(read_text_safe(log))
                        if CJK_RE.match(c)]
                if miss:
                    bad_books.add(name)
                    sample = "".join(sorted(set(miss))[:8])
                    self.rep.log(f"      注意：{len(miss)} 处汉字没有字形可用"
                                 f"（{sample}）→ 字体链里没有 CJK 字体", level="warn")

        # 把并发时各册的独立日志按册序拼回 pdf-build.log（串行时同样处理）
        self._merge_book_logs(book_log, roots)

        # 统计：只认「有 .tex 且有同名非空 .pdf」
        tex_n = len(roots)
        pdf_n = sum(1 for f in roots if (latex / f"{f.stem}.pdf").is_file()
                    and (latex / f"{f.stem}.pdf").stat().st_size > 0)
        ind_n = len(list(latex.glob("*.ind")))
        self.rep.log(f"tex={tex_n}  pdf={pdf_n}  ind={ind_n}"
                     f"　总用时 {human_dur(time.monotonic() - t_all)}", level="info")
        if bad_books:
            level = "err" if len(bad_books) > tex_n / 2 else "warn"
            self.rep.log(f"★ {len(bad_books)}/{tex_n} 册的编译日志里有汉字缺字形"
                         f"（{'、'.join(sorted(bad_books)[:6])}"
                         f"{' 等' if len(bad_books) > 6 else ''}）", level=level)
            if len(bad_books) > tex_n / 2:
                self.rep.log("  成片出现＝整数套册子都没有 CJK 字体：把「语言」设成 "
                             "en 时 Sphinx 不加载 xeCJK，正文会退回英文原文，"
                             "封面/页眉里的中文（步骤 6b 改的）则整段消失。", level="err")
                self.rep.log("  ⇒ 改回 zh_CN 后重跑 2→3 和 6→8。", level="err")
            else:
                self.rep.log("  少数册子属正常：上游正文里夹的生僻符号/古字，"
                             "FreeFont 没有字形（如 howto-unicode 的 ♞♟）。", level="warn")
        if failed:
            raise Fail(f"以下册子未出可用 PDF：{' '.join(failed)}"
                       f"（日志：{self.root / section}）\n"
                       "  已经串行重试过两轮。若日志里是 "
                       "`xelatex.exe: fwrite: Broken pipe` / "
                       "`gave return code 1` 而 `.log` 里没有 LaTeX 错误，"
                       "那是偶发的进程/管道故障（杀软实时扫描大 .tex 时常见），"
                       "再重跑一次本步通常就好；连续复现才需要查内容。")
        if pdf_n < tex_n:
            raise Fail(f"有 PDF 未生成（{pdf_n}/{tex_n}），看 {self.root / section}")
        if ind_n == 0:
            raise Fail("索引一个都没生成（.ind=0）：makeindex 不在 PATH，"
                       "或 $makeindex 覆盖没生效")
        return (f"{pdf_n} 册全部编译成功，{len(idx_books)} 册带索引"
                f"（分组标题 + 页码超链接 + 长条目断点，共 {ind_n} 个 .ind）")

    @staticmethod
    def _ind_summary(ind: Path) -> tuple[int, int, int, int, int]:
        """(页码链接数, 非字母标题数, 含非法 UTF-8 的行数, 断点数, 最长条目正文字符数)。"""
        raw = ind.read_bytes()
        links = raw.count(b"\\hyperpage{")
        syms = raw.count("\\bigletter {非字母}".encode())
        # \allowbreak：长模块路径（importlib.resources.abc.ResourceReader 之类）
        # 的断行点。缺了就说明 makeindex 没走我们的包装 → 索引会压到隔壁栏。
        brk = raw.count(b"\\allowbreak")
        bad = 0
        for ln in raw.split(b"\n"):
            try:
                ln.decode("utf-8")
            except UnicodeDecodeError:
                bad += 1
        # 最长条目正文有多长（字符）—— 用来判断「这本索引到底需不需要断点」。
        # ★ 必须先把 \allowbreak{} 去掉再量，否则补完断点后长度虚高，判据自相矛盾。
        #   索引是双栏，栏宽约 255pt，10pt FreeMono 每字符 6pt → 一行约 42 字符，
        #   超过就溢出、就会压到隔壁栏。
        longest = 0
        for ln in raw.replace(b"\\allowbreak{}", b"").split(b"\n"):
            try:
                s = ln.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if "\\item" not in s:
                continue
            head = s.split("\\hyperpage{")[0]
            longest = max(longest, len(head) - len("\\item \\spxentry{}"))
        return links, syms, bad, brk, longest

    # =======================================================================
    #  步骤 7b —— 索引自检（分组标题 + 页码超链接 + 长条目断点）
    # =======================================================================
    def step7b(self) -> str:
        if not self.cfg.fix_index:
            self.rep.log("按设置跳过索引自检", level="warn")
            return "已跳过"
        self.need_venv()
        assert self.latex
        latex = self.latex
        # ★ 这一步是「自检」，正常情况下应该什么都不用做 ★
        #   索引的四个毛病全都在步骤 7 里修掉了（$makeindex 换成 fix-index.py，
        #   修好的 .ind 被第 2 遍 xelatex 直接读到）：
        #     · 坏分组标题（\bigletter 只写了 UTF-8 首字节）→ 页面上的 �
        #     · {\sphinxsymbolsname} / {\sphinxnumbersname} 是空的 → 补成「非字母」「数字」
        #     · 页码没有 \hyperpage → 点不动
        #     · 长模块路径（importlib.resources.abc.ResourceReader 一类）不能断行
        #       → 溢出压到隔壁栏（叠字）→ 补 \allowbreak
        #   这里用 --check 逐册核对；只有异常情况（例如上次构建留下的旧 .ind、
        #   手工改了 .ind）才会真的动手，并且要重排那几册才生效。
        rc, out = self.tool("fix-index", fidx_main, [".", "--check"], cwd=latex,
                            quiet=True)
        need_fix = rc != 0
        section = "pdf-build.log"
        if not need_fix:
            inds = list(latex.glob("*.ind"))
            links = syms = bad = brk = 0
            for ind in inds:
                l, s, b, k, _longest = self._ind_summary(ind)
                links += l
                syms += s
                bad += b
                brk += k
            self.rep.log(f"索引自检通过：{len(inds)} 个 .ind，"
                         f"页码链接 {links} 个，非字母标题 {syms} 处，"
                         f"断点 {brk} 个，非法字节 {bad}",
                         level="ok")
        else:
            self.rep.log("索引自检发现还没修好的 .ind，开始补救", level="warn")
            if out.strip():
                self.rep.log(out.strip().splitlines()[-1], level="meta")
            # ★ 这里原来写的是 `[str(self.vp), str(tool), ".", "--version", …, "--list"]`
            #   —— 内联（2026-10-04）时 `tool = self.tools / "fix-index.py"` 那行删了，
            #   这四处却还在按「起子进程跑 tools/fix-index.py」的老形状写，于是
            #   步骤 7b 一跑就 `NameError: name 'tool' is not defined`（实测炸在下面
            #   那次复检上）。现在统一走进程内的 `self.tool("fix-index", fidx_main, …)`。
            #   顺带去掉 `--version`：fix-index **没有**这个选项（它不按版本号改名），
            #   旧写法里那个值会被 argparse 当成 paths 里的一个路径 —— 本来就多余。
            rc2, lst = self.tool("fix-index", fidx_main, [".", "--list"],
                                 cwd=latex, quiet=True)
            affected = [ln.strip() for ln in lst.splitlines() if ln.strip().endswith(".ind")]
            self.rep.log(f"受影响册子 {len(affected)} 个：{' '.join(affected)}", level="info")
            for j, ind in enumerate(affected, 1):
                self.rep.check_cancel()
                name = ind[:-4]                       # ★ 是重排 <name>.tex，不是 .ind 本身
                self.rep.sub(9, j, len(affected), name)
                self.rep.log(f"[{now_hms()}] ({j}/{len(affected)}) 重排 {name}", level="step")
                self._file(f"\n===== [{now_hms()}] 索引重排 {name} =====")
                # 修 .ind（这次是真的写盘）
                self.tool("fix-index", fidx_main, [ind], cwd=latex, section=section)
                # ★★ 判据必须盯「**这一遍真的编出来了**」（2026-10-06 修）★★
                #   旧写法只看「PDF 存在且页数 > 0」—— 而 xelatex 一旦失败，
                #   上一遍留下的**旧 PDF 还在那儿**，于是白跑一趟也报成功。
                #   实测踩到：xelatex 落到 TinyTeX、`cmap.sty` 找不到、
                #   `No pages of output`，这一步照样打印「OK 192 页」并宣布
                #   「索引已补救（9 册重排）」—— 用户看到的还是坏索引，日志全绿。
                #   现在三个判据一起上：退出码 + PDF **真的被重写**（mtime 变了）+ 非法字节。
                pdf = latex / f"{name}.pdf"
                before = pdf.stat().st_mtime_ns if pdf.is_file() else -1
                rc_x = 0
                for _ in range(2):                    # 第 1 遍读新 .ind 写新 .toc；第 2 遍定页码
                    rc_x = self.run([self._tool("xelatex"), "-interaction=nonstopmode",
                                     "-file-line-error", f"{name}.tex"],
                                    cwd=latex, section=section)
                log = latex / f"{name}.log"
                if re.search(r"Rerun to get|Label\(s\) may have changed",
                             read_text_safe(log)):
                    self.rep.log("      日志要求 Rerun，补第 3 遍", level="meta")
                    rc_x = self.run([self._tool("xelatex"), "-interaction=nonstopmode",
                                     "-file-line-error", f"{name}.tex"],
                                    cwd=latex, section=section)
                after = pdf.stat().st_mtime_ns if pdf.is_file() else -1
                bad = self.count_invalid_utf8(log)
                pages = self.pdf_pages(pdf)
                if rc_x == 0 and bad == 0 and pages and after != before:
                    self.rep.log(f"      OK  {pages} 页  非法UTF8=0", level="ok")
                else:
                    first_err = next(
                        (l.strip() for l in read_text_safe(log).splitlines()
                         if l.startswith("! ")), "（日志里没有 '! ' 开头的错误行）")
                    pdf_note = ("没有更新（No pages of output？）" if after == before
                                else f"{pages} 页")
                    raise Fail(
                        f"重排 {name} 失败：xelatex 退出码 {rc_x}，"
                        f"PDF {pdf_note}，非法字节 {bad}\n"
                        f"      首个错误：{first_err}\n"
                        f"      完整日志：{log}")
            affected_n = len(affected)
        # 复检：现在应该全齐了
        rc3, out3 = self.tool("fix-index", fidx_main, [".", "--check"],
                              cwd=latex, quiet=True)
        if rc3 != 0:
            raise Fail("索引自检仍未通过，详见 "
                       f"{self.root / 'index-fix.log'}（可单独跑 "
                       f"`--tool fix-index <latex 目录>` 看逐册明细）")
        # 顺手把明细写进日志文件，便于排查
        self.tool("fix-index", fidx_main, ["."], cwd=latex, section="index-fix.log")

        # 日志里不该再有 Invalid UTF-8（坏分组标题会让 XeTeX 报这个）
        badlines = 0
        for lg in latex.glob("*.log"):
            badlines += self.count_invalid_utf8(lg)
        self.rep.log(f"索引非法字节自检：日志里 Invalid UTF-8 共 {badlines} 条（应为 0），"
                     f"详见 {self.root / 'index-fix.log'}", level="ok" if badlines == 0 else "err")
        if badlines != 0:
            raise Fail(f"还有日志报 Invalid UTF-8，请检查 {self.root / 'index-fix.log'}")
        if not need_fix:
            return "索引自检通过（分组标题 + 页码超链接 + 长条目断点齐备）"
        return f"索引已补救（{affected_n} 册重排），非法字节 0"

    # =======================================================================
    #  步骤 8 —— 收集 + 验收 + 重命名
    # =======================================================================
    def step8(self) -> str:
        assert self.latex
        latex = self.latex
        out = self.outdir
        out.mkdir(parents=True, exist_ok=True)

        copied, skipped = 0, 0
        for pdf in sorted(latex.glob("*.pdf")):
            if self.cfg.prune_extra_pdf and not (latex / f"{pdf.stem}.tex").is_file():
                skipped += 1                      # SVG 转出来的插图 PDF，不是册子
                continue
            shutil.copy2(pdf, out / pdf.name)
            copied += 1
        self.rep.log(f"复制 {copied} 个 PDF 到 {out}"
                     + (f"（跳过 {skipped} 个插图 PDF）" if skipped else ""), level="ok")

        # 验收样本：与参考样张同纸型 / 中文走 Fandol 字体
        sample = out / "tutorial.pdf"
        if sample.is_file():
            rc, info = self.capture(["pdfinfo", str(sample)])
            m = re.search(r"^Pages:\s+(\d+)", info, re.M)
            ps = re.search(r"^Page size:\s+(.*)$", info, re.M)
            self.rep.log(f"样本 tutorial.pdf：页数 {m.group(1) if m else '?'}"
                         f"　纸型 {(ps.group(1).strip() if ps else '?')}", level="meta")
            rc, fonts = self.capture(["pdffonts", str(sample)])
            fando = sum(1 for ln in fonts.splitlines() if "Fandol" in ln)
            self.rep.log(f"Fandol 字体命中 {fando} 条"
                         f"{'（中文排版正常）' if fando else '（★ 异常：中文可能没走 Fandol）'}",
                         level="ok" if fando else "warn")

        # ── 重命名 ────────────────────────────────────────────────────────
        # ★ 2026-09-26 改：以前这里自带一份 `RENAME_MAP` 在程序里就地改名 ——
        #   而 `rename-pdf.sh` 是第二份、`tools/merge-pdf.py` 的表是第三份，
        #   三份靠手工同步，实测漏同步过两次（asyncio 那册名、3.14 才有的 0925）。
        #   现在映射只在 `tools/name_map.py` 一处，重命名逻辑只在
        #   `tools/rename-pdf.py` 一处 —— GUI 与 bash 走**同一条代码路径**，
        #   行为不可能再分叉。
        #   它还会顺手报出「本版本本就没有」/「应当有却缺」/「未收录产物」三类，
        #   并给出行 ASCII 标记（RENAMED/KEPT/MISSING/UNPRODUCED/UNKNOWN/EXTRA）。
        self._namemap_check()
        rc, text = self.tool("rename-pdf", rnpdf_main,
                             [str(out), "--version", self.cfg.version],
                             cwd=out, section="rename.log")
        marks: dict[str, int] = {}
        for ln in text.splitlines():
            m = re.match(r"^([A-Z_]+) (\d+)\s*$", ln)
            if m:
                marks[m.group(1)] = int(m.group(2))
                continue
            s = ln.strip()
            if not s:
                continue
            if "未收录产物" in s or "[警告]" in s:
                self.rep.log(f"      {s}", level="warn")
            elif s.startswith(("已改名", "已是目标名", "RENAMED")):
                self.rep.log(f"      {s}", level="ok")
            else:
                self.rep.log(f"      {s}", level="meta")
        renamed = marks.get("RENAMED", 0)
        kept = marks.get("KEPT", 0)
        miss = marks.get("MISSING", 0)
        unprod = marks.get("UNPRODUCED", 0)
        unknown = marks.get("UNKNOWN", 0)
        nfail = marks.get("FAILED", 0)
        self.rep.log(f"已重命名 {renamed} 册，已是目标名 {kept} 册"
                     f"（本版本本就没有 {unprod} 册）",
                     level="ok" if (miss + unknown + nfail) == 0 else "warn")
        if miss:
            self.rep.log(f"★ 本版本应当有、但没编出来 {miss} 册 —— "
                         "多为该册在步骤 7 编译失败，去 latex-build.log 搜它的名字",
                         level="err")
        if unknown:
            self.rep.log(f"★ 有 {unknown} 个未收录产物：它保持英文名、"
                         "且**不会进合并册**。按上面的提示在 "
                         "name_map.py 的 HOWTO 表补一行即可", level="err")
        if nfail:
            self.rep.log(f"★ {nfail} 个改名失败（见上）", level="err")
        if rc != 0 and not (miss or unknown or nfail):
            self.rep.log(f"重命名退出码 {rc}（未见具体问题，请查日志）", level="warn")

        # 残留英文名自查：重命名漏了哪些？——这是「重命名不出问题」的最后一道闸
        stray = sorted(p.name for p in out.glob("howto-*.pdf"))
        if stray:
            self.rep.log(f"★ 目录里仍有 {len(stray)} 个英文名分册："
                         f"{'、'.join(stray[:6])}{'…' if len(stray) > 6 else ''}"
                         "（它们不会进合并册）", level="err")

        # 验收报告
        # ★ 以前这里要先「找一个带 pypdf 的解释器」，找不到就整段跳过 ——
        #   内联之后 report 就是本进程里的一个函数，而 pypdf 是
        #   `requirements.txt` 的既有依赖（GUI 那份 venv 里一定有）。
        if self.cfg.gen_report:
            rc, _ = self.tool("report", rpt_main,
                              [str(out), str(latex), "--version", self.cfg.version],
                              section="report.log")
            rpt = out / "验收报告.md"
            if rc == 0 and rpt.is_file():
                self.rep.log(f"验收报告：{rpt}", level="ok")
            elif rc == 0:
                # report 以前只 print 不落盘，这里以前会**谎报**路径；
                # 现在落盘了，所以不再按退出码下结论，改按文件在不在。
                self.rep.log(f"报告跑完了，但没看到 {rpt}", level="warn")
            else:
                self.rep.log("验收报告生成失败（不影响 PDF）", level="warn")

        n = len(list(out.glob("*.pdf")))
        return f"产物 {n} 个 PDF 已就绪 → {out}"

    # =======================================================================
    #  步骤 9 —— 合并成一册（带完整书签）
    # =======================================================================
    def step9(self) -> str:
        if not self.cfg.merge_pdf:
            self.rep.log("未勾选「步骤 9：合并成一册」，跳过", level="warn")
            return "已跳过"
        out = self.outdir
        assert out

        # 先 --list 一遍：把「缺哪册」和最终目录树提前暴露出来（这时还没花时间合并）
        # ★ `--list` 不需要 pypdf（merge-pdf 里是懒加载），所以哪怕 pypdf 有问题，
        #   也要能先把「缺哪册」看清（2026-09-26 改；内联后这一层顾虑已经很薄了）。
        # ★ 必须带 --version：清单第一项是 `01Python <版本> 有什么新变化`，
        #   不传就默认 3.14 → 3.15 构建会误报 `MISSING 1`。
        self._namemap_check()
        _, listing = self.tool("merge-pdf", mgpdf_main,
                               [str(out), "--version", self.cfg.version, "--list"],
                               cwd=out, quiet=True)
        lmarks: dict[str, int] = {}
        for ln in listing.splitlines():
            m = re.match(r"^([A-Z_]+) (\d+)\s*$", ln)
            if m:
                lmarks[m.group(1)] = int(m.group(2))
                continue
            s = ln.strip()
            if not s:
                continue
            if s.startswith("!!") or "未收录产物" in s:
                self.rep.log(f"      {s}", level="warn")      # 版本传错 / 未收录产物
            elif s.startswith(("共 ", "本版本本就没有", "另有")):
                self.rep.log(f"      {s}", level="info")
        if lmarks.get("UNPRODUCED"):
            self.rep.log(f"      （其中 {lmarks['UNPRODUCED']} 册是**本版本本就没有**的，"
                         "不算缺册 —— 有些 howto 是后来的版本才加的）", level="meta")
        # ★ 判据用 ASCII 标记，不用中文「缺 0 册」：中文匹配在非 UTF-8 locale 会失配。
        #   MISSING 现在只数「本版本应当有却缺」；版本门控掉的不算 —— 3.13 的合并
        #   以前就是被这个误拒过（0925远程调试附加协议 是 3.14 才新增的）。
        if lmarks.get("MISSING", 1) != 0 or not listing.strip():
            det = next((x.strip() for x in listing.splitlines() if "缺" in x),
                       listing.strip()[-300:] or "（脚本没有输出）")
            raise Fail("合并前检查没通过：有的分册还不在输出目录里，"
                       f"先跑完步骤 8。\n{det}")
        # 未收录产物不会让合并失败，但会**静默少一章** —— 一定要说出来
        if lmarks.get("UNKNOWN"):
            self.rep.log(f"★ 有 {lmarks['UNKNOWN']} 个未收录产物**不会进合并册**"
                         "（映射表里没有它），按上面的提示在 name_map 的 HOWTO 表补一行",
                         level="err")

        name = (self.cfg.merge_name or "").strip()
        if name and not name.lower().endswith(".pdf"):
            name += ".pdf"
        # ★ 默认名带**完整版本号 + 日期**：Python 3.13.16 文档 20261017.pdf
        out_name = name or self.cfg.default_merge_name()

        cmd = [str(out), "--version", str(self.cfg.version),
               "--full-version", self.cfg.full_version()]
        if name:
            cmd += ["-o", name]
        t0 = time.monotonic()
        rc, text = self.tool("merge-pdf", mgpdf_main, cmd, cwd=out, section="merge.log")
        if rc != 0:
            tail = text.strip().splitlines()[-1] if text.strip() else "（无输出）"
            raise Fail(f"合并失败（退出码 {rc}）：{tail}")
        for ln in text.strip().splitlines():
            if ln.startswith(("  页数合计", "  书内跳转链接")):
                self.rep.log(f"      {ln.strip()}", level="meta")
        merged = out / out_name
        if not merged.is_file():
            raise Fail(f"合并命令跑完了，但没看到产物 {merged}")
        pages = self.pdf_pages(merged)
        mb = merged.stat().st_size / 1024 / 1024
        self.rep.log(f"      {out_name}　{pages or '?'} 页　{mb:.1f} MB　"
                     f"用时 {human_dur(time.monotonic() - t0)}", level="ok")
        return f"合并册 {out_name}（{pages} 页）→ {out}"

    # =======================================================================
    #  步骤 10 —— 清理过程文件
    # =======================================================================
    def step10(self) -> str:
        mode = (self.cfg.clean_mode or "none").strip()
        if mode not in ("build", "all"):
            self.rep.log("清理范围是「不清理」，跳过", level="warn")
            return "已跳过"
        assert self.root
        targets: list[Path] = []
        if mode == "build":
            # 大头就是这里：HTML + LaTeX + 中间件，动辄几个 GB
            targets = [self.root / P_CPYTHON / "Doc" / "build"]
        else:
            targets = [self.root / P_CPYTHON, self.root / P_VENV, self.root / "zh-cn"]
            # 分册日志留档目录（见 _merge_book_logs）：属过程文件，一并清掉
            targets += [self.root / "pdf-build-parts"]
            # 运行时铺出来的补充译文（内置那份是权威副本，删了下次会自动重铺）
            targets += [self.root / "i18n-extra"]
            targets += sorted(self.root.glob("*.log"))
        targets = [t for t in targets if t.exists()]
        if not targets:
            return "没有可清理的过程文件"

        # ★ 安全闸：任何一项都不能包含（或等于）成品 PDF 目录，否则直接拒绝
        outdir = (self.outdir or self.root).resolve()
        for t in targets:
            r = t.resolve()
            if r == outdir or outdir.is_relative_to(r):
                raise Fail(f"拒绝清理 {r}：它包含成品 PDF 目录 {outdir}")

        # 先算体积再删，日志里留个账
        total = 0
        for t in targets:
            total += self._du(t)
        self.rep.log(f"将删除 {len(targets)} 项，约 {total / 1024 / 1024:.0f} MB：",
                     level="warn")
        for t in targets:
            self.rep.log(f"      · {t}", level="meta")

        freed, failed = 0, []
        # ★ 先把自己打开的日志句柄关掉：Windows **不允许删本进程正打开的文件**，
        #   不关就必然留下 gui-build.log / 当前分节 .log 删不掉 ——
        #   这正是用户反馈的「删除过程文件经常失败」里最常见的一条。
        #   ⚠ 是 `self.` 不是 `self.rep.`：这两个是 **Pipeline 自己的**方法
        #     （`_open_log`/`_close_logs` 在「日志」一节），
        #     `self.rep` 是 ConsoleReporter / GUI reporter，从来没有这两个方法。
        #     实测（2026-10-06）：写成 `self.rep._close_logs()` 会在 **--cli** 下
        #     直接 `AttributeError`，而 GUI 下被 `_TeeReporter.__getattr__` 转发后
        #     同样炸 —— 步骤 10 一进去就失败，等于「清理过程文件」整个不可用。
        self._close_logs()
        try:
            for t in targets:
                sz = self._du(t)
                try:
                    # ★ 强制删除：清只读位（git 的 pack/*.idx 是只读的）+
                    #   长路径前缀（深目录叠中文路径会超 MAX_PATH）+ 重试 + rd 兜底
                    force_delete(t, log=lambda m: self.rep.log(m, level="meta"))
                    freed += sz
                except OSError as e:
                    # 典型：杀软 / 上一次没退干净的 xelatex 还占着句柄
                    failed.append(f"{t.name}（{e.strerror or e}）")
        finally:
            self._reopen_logs()       # 只重开没被删掉的那些（见 _reopen_logs）
        self.rep.log(f"     已释放 {freed / 1024 / 1024:.0f} MB", level="ok")
        if failed:
            self.rep.log(f"     {len(failed)} 项没删掉（多为还占着句柄，"
                         f"关掉程序后可手删）：{'、'.join(failed[:6])}"
                         + ("…" if len(failed) > 6 else ""), level="warn")
        return (f"清理完成，释放 {freed / 1024 / 1024:.0f} MB"
                + (f"（{len(failed)} 项被占用）" if failed else ""))

    @staticmethod
    def _du(p: Path) -> int:
        """目录/文件体积（字节）；算不出来就当 0，只影响日志里的数字。"""
        try:
            if p.is_file():
                return p.stat().st_size
            if p.is_dir():
                return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        except OSError:
            pass
        return 0

    def _force_clean(self, p: Path, what: str = "旧目录") -> None:
        """强制删掉一个过程目录/文件；实在删不掉就**明确报警**（绝不静默当成功）。

        ★ 为什么不能用 `shutil.rmtree(p, ignore_errors=True)`：它把「删不掉」
          吞掉了。实测后果 —— 旧 `cpython/` 没删掉（`.git/objects/pack` 下的
          `.pack`/`.idx` 是**只读**的，rmtree 直接 PermissionError），紧接着
          `git clone` 因为「目标目录非空」失败，报错却指向 git，方向完全错了。
        """
        if _deleted(p):
            return
        try:
            force_delete(p, log=lambda m: self.rep.log(m, level="meta"))
        except OSError as e:
            self.rep.log(f"警告：{what} {p} 删不掉（{e.strerror or e}）"
                         f"—— 后续步骤可能因残留而失败", level="warn")

    # ★ 这里原有 `_report_python()` / `_plain_python()` 两个「找解释器」的辅助函数
    #   （一个要求能 import pypdf、一个只要求标准库），服务于「起子进程跑 tools/xxx.py」。
    #   2026-10-04 工具内联之后它们彻底没用了：工具的代码就在本进程里，
    #   pypdf 也是本程序 requirements 的既有依赖 —— 于是「找不到带 pypdf 的解释器，
    #   整段跳过验收报告」这类静默降级路径一并消失。

    def _namemap_check(self) -> None:
        """跑一次内置的 `name_map --check`（映射表自身的完整性自检）。

        ★ 盯的是「以后手工补一行映射时最容易犯的错」：编号撞车、文件名重复、
          slug 拼错、分组名不认识、`MIN_VERSION` 指向不存在的 slug。
          这些错构建时**都不报**，要到「两册同名互相覆盖」或「合并册静默少一章」
          才暴露。所以真正用到映射的两步（重命名、合并）之前各查一次。
        """
        try:
            rc, out = self.tool("name-map", nm_cli, ["--check"], quiet=True)
        except Exception:                                     # noqa: BLE001
            return
        if rc == 0:
            self.rep.log(f"      映射表自检：{out.strip().splitlines()[-1] if out.strip() else 'OK'}",
                         level="meta")
        else:
            for ln in out.strip().splitlines():
                self.rep.log(f"      {ln.strip()}", level="err")
            self.rep.log("★ name_map 自检没过 —— 分册名/编号可能撞车，"
                         "合并册会缺章或错位，请先按上面的问题清单修掉", level="err")

    # =======================================================================
    #  调度
    # =======================================================================
    def main(self, steps: list[int] | None = None) -> tuple[bool, str]:
        """按顺序执行。返回 (是否全部成功, 结束语)。"""
        self.resolve_state()
        self._open_log()
        self._file(f"# 构建开始 {time.strftime('%Y-%m-%d %H:%M:%S')}")
        for k, v in asdict(self.cfg).items():
            self._file(f"#   {k} = {v}")
        # 上面那些字段留空时（root / outdir / venv / tools_dir 默认都是空 = 自动推算），
        # 单看配置文件根本不知道这次到底建到哪个目录 —— 事后排错最需要的就是它。
        self._file("# --- 解析后的实际取值 ---")
        for k, v in (("root", self.root), ("outdir", self.outdir),
                     ("tools_dir", self.tools), ("venv", self.vp or ""),
                     ("branch", self.cfg.branch)):
            self._file(f"#   {k} = {v}")
        self._flush_files()

        todo = steps if steps is not None else [s[0] for s in STEPS]
        ok_all, msg = True, "全部步骤完成"
        t0 = time.monotonic()
        try:
            for row in todo:
                if row not in STEP_BY_ROW:
                    continue
                _row, label, title, _sub = STEP_BY_ROW[row]
                self._cur_row = row
                self.rep.step_begin(row, title)
                t1 = time.monotonic()
                self._file(f"\n===== 步骤 {label} {title} =====")
                try:
                    summary = self.STEP_FUNCS[row](self)
                except Cancelled:
                    self.rep.step_end(row, False, "已停止", time.monotonic() - t1)
                    raise
                except Fail as e:
                    self.rep.log(f"[错误] {e}", level="err")
                    self.rep.step_end(row, False, str(e)[:120], time.monotonic() - t1)
                    ok_all, msg = False, f"步骤 {label}（{title}）失败：{e}"
                    break
                except Exception as e:                      # noqa: BLE001
                    import traceback
                    tb = traceback.format_exc()
                    self._file(tb)
                    self.rep.log(tb, level="err")
                    self.rep.step_end(row, False, f"{type(e).__name__}: {e}",
                                      time.monotonic() - t1)
                    ok_all, msg = False, f"步骤 {label}（{title}）异常：{type(e).__name__}: {e}"
                    break
                self.rep.step_end(row, True, summary, time.monotonic() - t1)
        finally:
            self._file(f"\n# 构建结束，用时 {human_dur(time.monotonic() - t0)}")
            self._flush_files()
            self._close_logs()
        if ok_all:
            msg = f"全部完成，用时 {human_dur(time.monotonic() - t0)}"
        return ok_all, msg

    # 各步骤的实例方法（STEP_FUNCS 按行号索引，见文件末尾的字典）
    def _run_step0(self): return self.step0()
    def _run_step1(self): return self.step1()
    def _run_step2(self): return self.step2()
    def _run_step3(self): return self.step3()
    def _run_step4(self): return self.step4()
    def _run_step5(self): return self.step5()
    def _run_step6(self): return self.step6()
    def _run_step7(self): return self.step6b()
    def _run_step8(self): return self.step7()
    def _run_step9(self): return self.step7b()
    def _run_step10(self): return self.step8()
    def _run_step11(self): return self.step9()
    def _run_step12(self): return self.step10()

    STEP_FUNCS = {
        0: _run_step0, 1: _run_step1, 2: _run_step2, 3: _run_step3, 4: _run_step4,
        5: _run_step5, 6: _run_step6, 7: _run_step7, 8: _run_step8, 9: _run_step9,
        10: _run_step10, 11: _run_step11, 12: _run_step12,
    }


# =============================================================================
# 五、命令行 reporter（--cli 用，也方便无头冒烟测试）
# =============================================================================

def _cli_color_enabled() -> bool:
    """命令行输出要不要用 ANSI 颜色。

    ★ 只在**真的接在终端上**时才上色（`isatty()`）。管道 / 重定向（`> x.log`、
      bash 脚本、我们的冒烟测试）里一律不上色 —— 那些 `\\033[1;32m` 字节进了
      日志文件就是一堆看不懂的乱码，跟 Sphinx 那个问题（见 ANSI_ESC）是同一类。
    ★ 顺便认 `NO_COLOR`（社区约定，任意非空值即禁用）。
    """
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return bool(sys.stdout is not None and sys.stdout.isatty())
    except Exception:                                # noqa: BLE001
        return False


def _cli_paint(text: str, code: str) -> str:
    """给命令行输出上色 —— **只在真的接终端时**（见 `_cli_color_enabled`）。

    ★ 别在 `print()` 里硬写 `\\033[1;32m`：重定向到文件时那些字节就是乱码
      （`exe --cli > log` 实测会留下 `[1;32m…[0m`）。
    """
    return f"\033[{code}m{text}\033[0m" if _cli_color_enabled() else text


class ConsoleReporter:
    _C = {"step": "\033[1;36m", "ok": "\033[1;32m", "err": "\033[1;31m",
          "warn": "\033[1;33m", "meta": "\033[2m", "cmd": "\033[2m", "info": ""}
    _R = "\033[0m"

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        self.cur: tuple[int, int, str] | None = None
        self._color = _cli_color_enabled()

    def _p(self, text: str, level: str) -> None:
        """往终端打一行。**打不出去不能算失败。**

        ★ 实测踩到：`--check | head -14` 这种「读者提前关管道」的场景下，
          `print(..., flush=True)` 会抛 `OSError: [Errno 22] Invalid argument`
          （Windows 上关掉的管道就长这样），于是整个 `--check` 崩掉，
          还把一份 Traceback 写成 `gui-startup-error.log` ——
          看着像「程序启动就坏了」，其实只是 `head` 读够了就走了。
          CLI 工具不该因为「没人看输出」而失败，所以这里忽略写输出的错误。
        """
        pre = self._C.get(level, "") if self._color else ""
        if "\r" in text:
            text = text.replace("\r", "")
        try:
            print(f"{pre}{text}{self._R if pre else ''}", flush=True)
        except OSError:                              # 管道被关掉 / 句柄失效
            pass

    def log(self, text: str, level: str = "info") -> None:
        self._p(text, level)

    def step_begin(self, i: int, title: str) -> None:
        _r, label, _t, _s = STEP_BY_ROW[i]
        self._p(f"\n==> 步骤 {label}  {title}", "step")

    def step_end(self, i: int, ok: bool, summary: str, secs: float) -> None:
        _r, label, title, _s = STEP_BY_ROW[i]
        self._p(f"    {'✔' if ok else '✘'} [{label}] {title}　{summary}　({human_dur(secs)})",
                "ok" if ok else "err")

    def sub(self, i: int, done: int, total: int, label: str = "") -> None:
        bar = int(done / max(total, 1) * 28)
        print(f"\r    [{'█' * bar}{'░' * (28 - bar)}] {done}/{total} {label:<28}",
              end="", flush=True)
        if done >= total:
            print(flush=True)

    def check_cancel(self) -> None:
        return

# =============================================================================
# 六、内置工具（原 sphinx-pdf/tools/*.py —— 2026-10-04 内联，**唯一实现**）
# =============================================================================
# ★ 为什么内联：以前主程序要起子进程去调 tools/ 下 8 个脚本，于是「携带本工具」
#   意味着要带走一整个目录；而且任何一份被改动而另一份没跟上，就会静默分叉
#   （本项目为此吃过两次亏：分册名映射表三份、越界引用判定三份）。
#   现在：下面这一段是唯一实现，tools/ 下那些文件只剩几行的**转发器**
#   （转调 `pdf_builder_multi.py --tool <名字>`），bash 脚本与手工排查照旧能用。
#
# ★ 每个工具的代码都是**原样搬过来的**（注释一行没动），仍以「命令行形状」工作：
#   自己读 `sys.argv`、自己 print 到 stdout。调用方用 `_tool_run()` 把这两样临时
#   接管掉 —— 内联前后行为逐字节一致，也不必重写任何一段工具逻辑。
#
# ★ 唯一必须留在磁盘上的是「修索引」：latexmk 的 `$makeindex` 只能调外部命令，
#   所以步骤 7 会在 latex 目录释放一个 makeindex-fix.py 转发器（ASCII 名，
#   见 `_emit_makeindex_fix`）。它内部再调回本程序，逻辑同样只有一份。


#: pypdf 的**备用搜索目录**（构建 venv 的 site-packages 等），由 `need_venv()` 登记。
#: 见 `_import_pypdf()` 里 2026-10-30 的说明。
_PYPDF_DIRS: list[str] = []


def _register_pypdf_dir(d: object) -> None:
    """登记一个「可能装着 pypdf 的目录」（venv 的 site-packages 等）。"""
    try:
        s = str(Path(str(d)))
    except (TypeError, ValueError):
        return
    if s and s not in _PYPDF_DIRS:
        _PYPDF_DIRS.append(s)


def _import_pypdf(what: str = "本工具"):
    """按需导入 `pypdf`；缺了就给一句**能照做**的提示，而不是裸 ModuleNotFoundError。

    ★ 为什么不能写在模块级：主程序刻意只在图形界面段才要求 PyQt6，
      `--cli` / `--check` / `--tool` 都该能在「只装了标准库」的解释器里跑。
      （内联前 verify-pdf / report / check-pdf-gaps 各有一份模块级
      `from pypdf import PdfReader`，那正是「没装 pypdf 就整程序起不来」的来源。）
    ★ 抛 SystemExit：`_tool_run` 会把它转成「打印这句话 + 退出码 1」，
      与「命令行脚本自己发现缺依赖」的表现一致。

    ★★ 2026-10-30 加备用搜索目录 ★★
      实测：三版本并行跑了 40 分钟后，步骤 8 的验收报告与步骤 9 的合并**同时**
      报「当前解释器里没有 pypdf」，而同一个 exe 新起进程手动跑 `--tool merge-pdf`
      完全正常（3949 页合并成功，说明 pypdf 确实打在 exe 里）。
      也就是说内置那份在个别运行状态下读不到。步骤 4 一定把 pypdf 装进了构建
      venv，而 pypdf 是**纯 Python**（跨 3.13/3.14/3.15 直接 import 没问题）——
      这里就把 venv 的 site-packages 当备用路径，读不到内置的就从 venv 导。
      真的都没有时，报错里带上**真实的 ImportError 原因**，不再是一句干巴巴的
      「没有 pypdf」（那样完全没法判断是打包缺了、还是运行期出了别的问题）。
    """
    try:
        import pypdf  # noqa: F401
        return pypdf
    except ImportError as exc:
        err: BaseException = exc
    for d in list(_PYPDF_DIRS):
        if d in sys.path:
            continue
        sys.path.insert(0, d)
        try:
            import pypdf  # noqa: F401
            return pypdf
        except ImportError as exc2:            # 这个目录里也没有 → 换下一个
            err = exc2
            try:
                sys.path.remove(d)
            except ValueError:
                pass
    raise SystemExit(
        f"{what}需要 pypdf，但当前解释器里没有：\n"
        f"  {sys.executable}\n"
        f"  原因：{type(err).__name__}: {err}\n"
        "装它：python -m pip install pypdf\n"
        "或者直接用图形界面跑（它会在 C:\\pypdfbuild\\gui-venv 里自动装好）。"
    ) from err


# ---------------------------------------------------------------------------
# 内置工具：name_map.py（原样内联，逻辑一行未改）
#   入口：nm_cli
# ---------------------------------------------------------------------------
# """Python 中文分册 PDF 的 **唯一命名真源**。
#
# ★ 为什么要有这个文件
#     2026-09-26 实测踩到：分册名映射在**三个地方**各写了一份 ——
#       * `rename-pdf.sh`         （slug → 中文文件名）
#       * `tools/merge-pdf.py`    （中文文件名 → 书签标题 + 分组）
#       * `gui/pdf_builder_multi.py`（slug → 中文文件名，一份 RENAME_MAP）
#     三份都要手工同步，且都**写死了 3.14 的版本号**。后果实测过两次：
#       * 改完 `RENAME_MAP` 的 asyncio 名，`merge-pdf.py` 没跟着改 → `MISSING 1`；
#       * 3.13 建出来时 `--list` 报 `MISSING 1`（`0925远程调试附加协议`），
#         因为 `MIN_VERSION` 只登记了 `0929`、漏了 3.14 才新增的 `0925`。
#     所以：**一切映射只在本文件里定义**，重命名 / 合并 / GUI 全部 import 它。
#
# ★ 命名口径（与外部参考样张的区别）
#     参考样张 `命名.txt` 用长名「09Python 指南NN」；**本项目统一简化为「09NN」**。
#     `命名.txt` 是外部参考，**原样保留、不改**。
#
# ★ 版本门控
#     上游会随版本**新增/移除** howto。新版本独有的册子必须登记进 `MIN_VERSION`，
#     否则：
#       * 高版本目录：没事；
#       * 低版本目录：`--list` 会报「缺 1 册」而拒绝合并（其实是本版本本就没有）。
#     登记后低版本会把它标成 `UNPRODUCED`（本版本无此册），不计入 `MISSING`。
#
#      实测三版本（2026-09-26）：
#         3.13 → 37 册（缺 0925、0929）
#         3.14 → 38 册（缺 0929）
#         3.15 → 39 册（全）
#
# ★ 未知产物（上游又加了新 howto 而我们没登记）
#     工具不会静默吞掉：会列为 `UNKNOWN` 并提示补哪一行、有哪些空号可用。
# """


# ---------------------------------------------------------------------------
# 主分册：8 册一级 + 2 册尾部（faq / builtins）
#   每项：(上游产物名, 目标文件名, 合并册书签标题)
#   ★ 目标文件名里的 `3.14` 会被 `--version` 替换（`whatsnew` 那一项）。
# ---------------------------------------------------------------------------
MAIN: list[tuple[str, str, str]] = [
    ('whatsnew',   '01Python {V} 有什么新变化',       'Python的新变化'),
    ('tutorial',   '02Python 教程',                    'Python 教程'),
    ('using',      '03Python安装和使用',               'Python安装和使用'),
    ('reference',  '04Python 语言参考手册',            'Python 语言参考手册'),
    ('library',    '05Python 标准库',                  'Python 标准库'),
    ('extending',  '06扩展和嵌入 Python 解释器',       '扩展和嵌入 Python 解释器'),
    ('c-api',      '07Python C API 参考手册',          'Python/C API 参考手册'),
    ('installing', '08安装 Python 模块',               '安装 Python 模块'),
    # ★ 只有 3.10 及更早才有这一册：3.11 起上游把《Distributing Python Modules》
    #   并进了 installing，`Doc/distributing/` 目录直接消失。实测 3.10 的
    #   `Doc/conf.py` 里 `latex_documents` 同时列了 installing 与 distributing。
    #   编号用 `09`（两位数），与 howto 的 `09xx` 四位号不冲突。
    ('distributing', '09分发 Python 模块',             '分发 Python 模块'),
]

#: 尾部两册（放最后，与参考图一致）
TAIL: list[tuple[str, str, str]] = [
    ('faq',      '10Python 常见问题',      'Python 常见问题'),
    ('builtins', '11Python 内置参考手册',  'Python 内置参考手册'),
]

#: howto 的总分组节点标题
HOWTO_ROOT_TITLE = 'Python 指南'

#: `MERGE_ORDER` 里代表「Python 指南 整块」的占位键（它不是真 slug）。
HOWTO_KEY = '__howto__'

#: ★ 合并册一级书签顺序（用 slug 表示）。
#:   与 `MAIN` / `TAIL` 的表内顺序**无关** —— 那两张表只管「改成什么名」，
#:   这里管「合并册里谁在前、谁在后」。
#:   `builtins` 特意夹在 `reference` 与 `library` 之间：语言参考手册 → 内置参考手册
#:   → 标准库，与官方目录的阅读顺序一致（内置类型/函数/异常是语言核心的延续，
#:   排在标准库模块之前）。2026-09-27 按用户要求调整，此前它排在整册最后。
MERGE_ORDER: list[str] = [
    'whatsnew', 'tutorial', 'using',
    'reference',
    'builtins',
    'library',
    'extending', 'c-api', 'installing', 'distributing',
    HOWTO_KEY,
    'faq',
]

# ---------------------------------------------------------------------------
# howto 分册（09xx）
#   每项：(上游产物名, 目标文件名, 合并册书签标题, 子分组)
#   表内顺序 = 同组内的书签顺序。
#   ★ 编号是**按主题固定**的，不随版本重排 —— 这样跨版本的文件名可比对。
#     代价是某个版本缺某主题时编号会**留空号**（如 3.13 没有 0925）。
#   ★ 表内顺序 = **合并册书签顺序**（不是编号升序）：`0929` 按上游 howto 索引页的
#     位置插在「高级开发」组的 0917 之后、0918 之前。两个维度不要混。
# ---------------------------------------------------------------------------
HOWTO: list[tuple[str, str, str]] = [
    # ★ 表内顺序 = 合并册书签顺序 = **09xx 编号升序**（`selfcheck` 会校验）。
    #   2026-09-27 起 `Python 指南` 下**不再分组**：各册平铺，与用户给的参考图一致。
    #   所以 0929 不能再插到 0917/0918 之间 —— 它按编号排在最后。
    ('howto-a-conceptual-overview-of-asyncio',
     '0901asyncio 的概念概述',              'asyncio 的概念概述'),
    ('howto-annotations',
     '0902注解最佳实践',                    '注解最佳实践'),
    ('howto-argparse',
     '0903argparse 教程',                   'argparse 教程'),
    ('howto-descriptor',
     '0904描述器指南',                      '描述器指南'),
    ('howto-enum',
     '0905Enum 指南',                       'Enum 指南'),
    ('howto-functional',
     '0906函数式编程指引',                  '函数式编程指引'),
    ('howto-ipaddress',
     '0907ipaddress模块介绍',               'ipaddress 模块介绍'),
    ('howto-logging',
     '0908日志指南',                        '日志指南'),
    ('howto-logging-cookbook',
     '0909日志专题手册',                    '日志专题手册'),
    ('howto-regex',
     '0910正则表达式指南',                  '正则表达式指南'),
    ('howto-sorting',
     '0911排序的技术',                      '排序的技术'),
    ('howto-unicode',
     '0912Unicode 指南',                    'Unicode 指南'),
    ('howto-urllib2',
     '0913如何利用 urllib 包获取网络资源',  '如何利用 urllib 包获取网络资源'),
    ('howto-curses',
     '0914用 Python 进行 Curses 编程',      '用 Python 进行 Curses 编程'),
    ('howto-free-threading-python',
     '0915Python 对自由线程的支持',         'Python 对自由线程的支持'),
    ('howto-free-threading-extensions',
     '0916自由线程的 C API 扩展支持',       '自由线程的 C API 扩展支持'),
    ('howto-isolating-extensions',
     '0917隔离扩展模块',                    '隔离扩展模块'),
    ('howto-mro',
     '0918Python 2.3 方法解析顺序',         'Python 2.3 方法解析顺序'),
    ('howto-sockets',
     '0919套接字编程指南',                  '套接字编程指南'),
    ('howto-timerfd',
     '0920定时器文件描述符指南',            '定时器文件描述符指南'),
    ('howto-cporting',
     '0921将扩展模块移植到 Python 3',       '将扩展模块移植到 Python 3'),
    ('howto-gdb_helpers',
     '0922使用 GDB 调试 C API 扩展和 CPython 内部代码',
     '使用 GDB 调试 C API 扩展和 CPython 内部代码'),
    ('howto-instrumentation',
     '0923使用 DTrace 和 SystemTap 检测CPython',
     '使用 DTrace 和 SystemTap 检测 CPython'),
    # ★ 书签标题原来错写成了英文 `Python support for the Linux perf profiler`
    #   （2026-09-26 从 3.14 合并册的书签树里查出来，是整棵树唯一的英文项）。
    ('howto-perf_profiling',
     '0924Python 对 Linux perf 性能分析器的支持',
     'Python 对 Linux perf 性能分析器的支持'),
    ('howto-remote_debugging',
     '0925远程调试附加协议',                '远程调试附加协议'),
    ('howto-argparse-optparse',
     '0926将 optparse 代码迁移至 argparse', '将 optparse 代码迁移至 argparse'),
    ('howto-clinic',
     '0927Argument Clinic 的用法',          'Argument Clinic 的用法'),
    ('howto-pyporting',
     '0928如何将 Python 2 代码移植到 Python 3',
     '如何将 Python 2 代码移植到 Python 3'),
    # 3.15 新增（MIN_VERSION 门控）。按「编号升序平铺」它排在最后。
    ('howto-abi3t-migration',
     '0929迁移到自由线程的稳定 ABI（abi3t）', '迁移到自由线程的稳定 ABI（abi3t）'),
]


# ---------------------------------------------------------------------------
# 版本门控：只在「某版本起」才存在的册子
#   key   = 上游产物名（slug，版本的稳定标识）
#   value = 最低版本 (major, minor)
#   ★ 判定规则：`当前版本 >= min` 时「必须有」；否则「本版本本就没有」，不算缺册。
#   ★ 新增条目时**必须同时验证**：高版本目录不报 MISSING、低版本目录也不报 MISSING。
# ---------------------------------------------------------------------------
MIN_VERSION: dict[str, tuple[int, int]] = {
    # ---- 静态册（MAIN / TAIL） ----
    # `Doc/builtins.rst` 是 3.13 才从 library 里拆出来的独立章。
    'builtins': (3, 13),

    # ---- howto：以下全部按 github.com/python/cpython 各分支的
    #      `Doc/howto/` 目录实测（2026-11-03 用 `--tool volumes --verify` 核过） ----
    'howto-enum':                  (3, 11),   # Enum HOWTO
    'howto-gdb_helpers':           (3, 11),   # GDB 调试辅助
    'howto-isolating-extensions':  (3, 11),   # 隔离扩展模块
    'howto-mro':                   (3, 12),   # 方法解析顺序
    'howto-perf_profiling':        (3, 12),   # Linux perf
    'howto-argparse-optparse':     (3, 12),   # optparse → argparse 迁移
    'howto-a-conceptual-overview-of-asyncio': (3, 13),
    'howto-timerfd':               (3, 13),
    'howto-free-threading-python': (3, 13),
    'howto-free-threading-extensions': (3, 13),
    # PEP 768「安全的外部调试器接口」是 3.14 新增，3.13 的 Doc/howto 里没有这篇。
    'howto-remote_debugging': (3, 14),
    # 3.15 新增（自由线程的稳定 ABI abi3t）。
    'howto-abi3t-migration': (3, 15),
}

#: ★ 上限门控：只在「某版本及之前」才有的册子（缺的版本不算缺册）。
#:   与 `MIN_VERSION` 合起来就是一条闭区间：`min <= 当前版本 <= max`。
MAX_VERSION: dict[str, tuple[int, int]] = {
    # 3.11 起《Distributing Python Modules》并入 installing，distributing/ 目录被删。
    'distributing': (3, 10),
}


def ver_tuple(v: str) -> tuple[int, int]:
    """'3.15' → (3, 15)；解析不出来当 (0, 0)，即「不门控」（任何版本都要求有）。"""
    try:
        parts = (str(v).split('.') + ['0'])[:2]
        return int(parts[0]), int(parts[1])
    except (ValueError, AttributeError):
        return (0, 0)


def _subst(name: str, version: str) -> str:
    """目标文件名里的版本号替换（`01Python 3.14 有什么新变化` → 当前版本）。

    ★ 只换文件名、不动书签标题：标题是本工具自己定的中文短语（如 `Python的新变化`），
      不含版本号，也不该被文件名影响。
    ★ 新写法用 `{V}` 占位（`01Python {V} 有什么新变化`）；老写法里写死的 `3.14`
      仍然照旧替换 —— 外部 `volumes.json` 与界面里两种都能用。
    """
    if not name:
        return name
    if '{V}' in name:
        return name.replace('{V}', str(version))
    return name.replace('3.14', str(version))


def min_version_of(slug: str) -> tuple[int, int]:
    return MIN_VERSION.get(slug, (0, 0))


def max_version_of(slug: str) -> tuple[int, int] | None:
    """上限（含）；`None` = 不设上限（该版本起一直有）。"""
    return MAX_VERSION.get(slug)


def has_in_version(slug: str, version: str) -> bool:
    """该 slug 在当前版本里**应当**存在（不区分「本版本没有」与「该有却缺」）。

    区间是闭区间：`min <= 当前版本 <= max`。上限用来表达「上游删掉了一册」——
    典型例子就是 3.10 之后消失的 `distributing`。没有上限时只看下限，
    所以老行为（只登记 MIN_VERSION）完全不变。
    """
    cur = ver_tuple(version)
    if min_version_of(slug) > cur:
        return False
    hi = max_version_of(slug)
    return hi is None or cur <= hi


# ---------------------------------------------------------------------------
# 外部配置：volumes.json
#   ★ 为什么要有它：册数**随版本变**，而且上游每年都会加/删几册。把表留在代码里
#     就只能改代码 + 重新打包。现在「加一个版本」「改一个文件名」都只是编辑这个
#     JSON（或界面里点几下），代码不动。
#   ★ 没有这个文件 = 用下面内置的表，行为与以前完全一致 —— 所以它是**可选覆盖**，
#     不是必需依赖。读坏了也只会打一行警告然后退回内置，绝不因此起不来。
# ---------------------------------------------------------------------------

#: 内置默认值快照 —— 外部文件读坏、或用户点「还原内置默认」时回到这里。
_EMBEDDED: dict[str, object] = {
    'MAIN': list(MAIN),
    'TAIL': list(TAIL),
    'HOWTO': list(HOWTO),
    'MERGE_ORDER': list(MERGE_ORDER),
    'MIN_VERSION': dict(MIN_VERSION),
    'MAX_VERSION': dict(MAX_VERSION),
    'HOWTO_ROOT_TITLE': HOWTO_ROOT_TITLE,
}

VOLUMES_FILENAME = 'volumes.json'
VOLUMES_SCHEMA = 2

#: 实际生效的外部文件路径（'' = 用的是内置表）。
VOLUMES_LOADED = ''
#: 加载结果的一句话说明（界面会显示，出问题时也靠它定位）。
VOLUMES_NOTE = '使用内置默认表'


def volumes_json_candidates() -> list[Path]:
    """到哪里找 `volumes.json`（按优先级）。

    ★ 顺序有意义：打包成 exe 时 `__file__` 指向解包临时目录，改那里等于白改，
      所以 **exe 所在目录优先**；其次是主程序同级的上一级（源码树里的
      `sphinx-pdf/volumes.json`）；最后是当前目录（临时试用）。
    """
    out: list[Path] = []
    env = os.environ.get('PDFBUILDER_VOLUMES', '').strip()
    if env:
        out.append(Path(env))
    if getattr(sys, 'frozen', False):
        out.append(Path(sys.executable).resolve().parent / VOLUMES_FILENAME)
    here = Path(__file__).resolve().parent
    out += [here / VOLUMES_FILENAME, here.parent / VOLUMES_FILENAME, Path.cwd() / VOLUMES_FILENAME]
    seen: set[str] = set()
    uniq: list[Path] = []
    for p in out:
        if str(p) not in seen:
            seen.add(str(p))
            uniq.append(p)
    return uniq


def volumes_json_path() -> Path | None:
    """现成可读的那一个；没有就 None（= 走内置表）。"""
    for p in volumes_json_candidates():
        if p.is_file():
            return p
    return None


def default_volumes_json_path() -> Path:
    """要写文件时写到哪儿 —— 源码树里是 `sphinx-pdf/volumes.json`。"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent / VOLUMES_FILENAME
    return Path(__file__).resolve().parent.parent / VOLUMES_FILENAME


def _restore_embedded() -> None:
    global MAIN, TAIL, HOWTO, MERGE_ORDER, MIN_VERSION, MAX_VERSION, HOWTO_ROOT_TITLE
    MAIN = list(_EMBEDDED['MAIN'])
    TAIL = list(_EMBEDDED['TAIL'])
    HOWTO = list(_EMBEDDED['HOWTO'])
    MERGE_ORDER = list(_EMBEDDED['MERGE_ORDER'])
    MIN_VERSION = dict(_EMBEDDED['MIN_VERSION'])
    MAX_VERSION = dict(_EMBEDDED['MAX_VERSION'])
    HOWTO_ROOT_TITLE = str(_EMBEDDED['HOWTO_ROOT_TITLE'])


def dump_volumes() -> dict:
    """把当前生效的表导成 JSON 结构（`--tool name-map --dump` 与界面保存都用它）。"""
    vols: list[dict] = []
    for slug, name, title in (*MAIN, *HOWTO, *TAIL):
        kind = 'main' if any(s == slug for s, _n, _t in MAIN) else (
            'tail' if any(s == slug for s, _n, _t in TAIL) else 'howto')
        item: dict[str, object] = {'slug': slug, 'name': name, 'title': title, 'kind': kind}
        lo = MIN_VERSION.get(slug)
        if lo:
            item['min'] = '%d.%d' % lo
        hi = MAX_VERSION.get(slug)
        if hi:
            item['max'] = '%d.%d' % hi
        vols.append(item)
    return {
        'schema': VOLUMES_SCHEMA,
        '_说明': ('分册配置。kind: main=前置册 / howto=Python 指南 / tail=尾部册。'
                 'min/max 是闭区间的版本上下限（省略 = 不限）。'
                 'name 里的 {V} 会替换成当前版本号。'
                 '改完跑 `--tool name-map --check` 自检，`--tool volumes --verify` 可对着 '
                 'github.com/python/cpython 各分支的 Doc/conf.py 在线核对。'),
        'howto_root_title': HOWTO_ROOT_TITLE,
        'merge_order': list(MERGE_ORDER),
        'volumes': vols,
    }


def load_volumes(path: str | Path | None = None, *, quiet: bool = False) -> str:
    """读外部 `volumes.json` 覆盖内置表；返回一句话说明。

    ★ 只在**全部校验通过**之后才替换全局表：宁可整份不用，也不要半份生效
      （半份生效的后果是「某几册名字对、某几册没名」，比完全失败更难查）。
    """
    global MAIN, TAIL, HOWTO, MERGE_ORDER, MIN_VERSION, MAX_VERSION
    global HOWTO_ROOT_TITLE, VOLUMES_LOADED, VOLUMES_NOTE

    p = Path(path) if path else volumes_json_path()
    if p is None or not p.is_file():
        _restore_embedded()
        VOLUMES_LOADED, VOLUMES_NOTE = '', '使用内置默认表'
        return VOLUMES_NOTE

    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('顶层不是对象')
        vols = data.get('volumes')
        if not isinstance(vols, list) or not vols:
            raise ValueError('缺少 volumes 数组')

        main: list[tuple[str, str, str]] = []
        tail: list[tuple[str, str, str]] = []
        howto: list[tuple[str, str, str]] = []
        lo_map: dict[str, tuple[int, int]] = {}
        hi_map: dict[str, tuple[int, int]] = {}
        buckets = {'main': main, 'tail': tail, 'howto': howto}
        slugs: set[str] = set()

        for i, item in enumerate(vols, 1):
            if not isinstance(item, dict):
                raise ValueError(f'第 {i} 条不是对象')
            slug = str(item.get('slug') or '').strip()
            name = str(item.get('name') or '').strip()
            title = str(item.get('title') or '').strip()
            kind = str(item.get('kind') or 'main').strip().lower()
            if not slug or not name:
                raise ValueError(f'第 {i} 条缺 slug 或 name')
            if kind not in buckets:
                raise ValueError(f'第 {i} 条 kind={kind} 不认识（只能是 main/tail/howto）')
            if slug in slugs:
                raise ValueError(f'slug 重复：{slug}')
            slugs.add(slug)
            buckets[kind].append((slug, name, title))
            for key, tgt in (('min', lo_map), ('max', hi_map)):
                raw = str(item.get(key) or '').strip()
                if raw and raw != '0.0':
                    tgt[slug] = ver_tuple(raw)
                    if tgt[slug] == (0, 0):
                        raise ValueError(f'{slug} 的 {key}={raw!r} 解析不出主次版本号')

        for slug in slugs:
            lo, hi = lo_map.get(slug), hi_map.get(slug)
            if lo and hi and lo > hi:
                raise ValueError(f'{slug} 的 min({lo[0]}.{lo[1]}) > max({hi[0]}.{hi[1]})')
        if not main or not howto:
            raise ValueError('main 或 howto 一册都没有（显然不对）')

        order = data.get('merge_order')
        if order is None:
            order = [s for s, _n, _t in (*main, *tail)] + [HOWTO_KEY]
        if not isinstance(order, list) or HOWTO_KEY not in order:
            raise ValueError(f'merge_order 必须是数组且含 {HOWTO_KEY} 占位')

        title_root = str(data.get('howto_root_title') or HOWTO_ROOT_TITLE)

        MAIN, TAIL, HOWTO = main, tail, howto
        MERGE_ORDER = [str(k) for k in order]
        MIN_VERSION, MAX_VERSION = lo_map, hi_map
        HOWTO_ROOT_TITLE = title_root
        VOLUMES_LOADED = str(p)
        VOLUMES_NOTE = (f'外部配置生效：{p}（{len(vols)} 条，'
                        f'{len(main)} 前置 / {len(howto)} 指南 / {len(tail)} 尾部）')
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as e:
        _restore_embedded()
        VOLUMES_LOADED = ''
        VOLUMES_NOTE = f'外部配置读不了，已退回内置表：{p} —— {e}'
        if not quiet:
            print(f'[警告] {VOLUMES_NOTE}', file=sys.stderr)
    return VOLUMES_NOTE


# 导入时生效一次（找不到文件就是内置表，行为与旧版完全一致）
load_volumes(quiet=True)



# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------

def all_entries() -> list[tuple[str, str]]:
    """全部 (slug, 目标文件名) —— **不过滤版本**，供重命名用。

    重命名必须拿到全集：低版本里那些「本版本没有」的条目，文件不存在会跳过；
    但如果**文件存在**（说明 MIN_VERSION 登记错了），要如实报出来。
    """
    out: list[tuple[str, str]] = []
    for slug, fname, _t in MAIN:
        out.append((slug, fname))
    for slug, fname, _t in HOWTO:
        out.append((slug, fname))
    for slug, fname, _t in TAIL:
        out.append((slug, fname))
    return out


def rename_plan(version: str) -> dict[str, str]:
    """{slug: 目标文件名}（全集，已按版本替换文件名里的版本号）。"""
    return {slug: _subst(fname, version) for slug, fname in all_entries()}


def expected(version: str) -> list[str]:
    """本版本**应当有**的目标文件名列表（已过滤版本门控）。"""
    out = []
    for slug, fname in all_entries():
        if has_in_version(slug, version):
            out.append(_subst(fname, version))
    return out


def fname_of(slug: str, version: str = '3.14') -> str | None:
    for s, f in all_entries():
        if s == slug:
            return _subst(f, version)
    return None


def used_numbers(version: str | None = None) -> list[str]:
    """已占用的 09xx 编号（排序后）。

    传 `version` 则只算**该版本实际会有**的册子 —— 版本门控掉的编号就是空号。
    """
    nums = []
    for slug, fname, _t in HOWTO:
        if version is not None and not has_in_version(slug, version):
            continue
        if fname[:4].isdigit():
            nums.append(fname[:4])
    return sorted(nums)


def spare_numbers(version: str | None = None) -> list[str]:
    """**空号**：0901 到最大编号之间没有被占用的号。

    上游新增 howto 时用它挑一个不撞车的号（例如 3.13 里 0925、0929 都是空号）。
    """
    used = set(used_numbers(version))
    if not used:
        return []
    hi = int(max(used))
    return ['%04d' % n for n in range(901, hi + 1) if '%04d' % n not in used]


# ---------------------------------------------------------------------------
# 合并册结构（步骤 9）
# ---------------------------------------------------------------------------

def build_spec(version: str = '3.14') -> list[tuple[str, str, int]]:
    """拍平表 [(文件名, 书签标题, 层级)]；文件名为 '' 表示分组节点。

    层级：0 = 一级分册 / `Python 指南` 根；1 = 直挂指南下的 howto。

    ★ 一级顺序由 `MERGE_ORDER` 决定（**不看 `MAIN` / `TAIL` 的表内顺序**）——
      `builtins` 因此可以夹在 reference 与 library 之间，而不是排在整册最后。
    ★ `Python 指南` 下**不再分组**：各册按 09xx 编号升序平铺（与参考图一致）。
    """
    def fn(name: str) -> str:
        return _subst(name, version) if name else name

    def keep(slug: str) -> bool:
        # ★ 必须走 has_in_version（同时看上限）—— 只看 MIN_VERSION 的话，
        #   3.10 的 `distributing` 会出现在 3.15 的合并册大纲里，然后因为文件不存在
        #   被判成 MISSING 而卡住合并。
        return has_in_version(slug, version)

    info: dict[str, tuple[str, str]] = {s: (n, t) for s, n, t in (*MAIN, *TAIL)}
    spec: list[tuple[str, str, int]] = []

    for key in MERGE_ORDER:
        if key == HOWTO_KEY:
            spec.append(('', HOWTO_ROOT_TITLE, 0))
            for slug, name, title in HOWTO:          # 表内顺序 = 编号升序
                if keep(slug):
                    spec.append((fn(name), title, 1))
            continue
        name, title = info[key]
        if keep(key):
            spec.append((fn(name), title, 0))
    return spec


def unproduced(version: str) -> list[tuple[str, str]]:
    """本版本**本就没有**的册子 → [(slug, 目标文件名)]，不是错误、只是提示。"""
    return [(s, _subst(f, version)) for s, f in all_entries()
            if not has_in_version(s, version)]


def brief(names: list[str], limit: int = 8) -> str:
    """长清单只显示前几个 —— 几十个名字铺一屏会把真正的结论埋掉。"""
    if len(names) <= limit:
        return '、'.join(names)
    return '、'.join(names[:limit]) + f' …（共 {len(names)} 个）'


def guess_version(pdf_dir) -> str | None:
    """目录里若有 `01Python X.Y 有什么新变化.pdf`，从它反推版本号。

    用来发现「`--version` 传错」这种最容易犯的错 —— 传错的后果是一批 `MISSING`
    假警报，而报错信息里完全看不出是版本传错了。重命名与合并都调它。
    """
    import re
    from pathlib import Path

    for pdf in sorted(Path(pdf_dir).glob('*有什么新变化.pdf')):
        m = re.search(r'(\d+\.\d+)', pdf.stem)
        if m:
            return m.group(1)
    return None


def selfcheck() -> list[str]:
    """自检映射表本身 —— 返回问题清单（空 = 没问题）。

    ★ 以后手工往 HOWTO 表补一行时最容易犯的错：编号撞车、文件名重复、
      slug 拼错、分组名写了个不存在的组、`MIN_VERSION` 的 slug 根本没登记。
      这些错误在构建时都不报，要到「两册同名被覆盖」或「合并册缺一章」才暴露。
      `python tools/name_map.py --check` 就是专门盯这个的。
    """
    problems: list[str] = []

    def dup(items: list[str], what: str) -> None:
        seen: set[str] = set()
        for it in items:
            if it in seen:
                problems.append(f'{what}重复：{it}')
            seen.add(it)

    all_slugs = [s for s, _f in all_entries()]
    all_fnames = [f for _s, f in all_entries()]
    dup(all_slugs, '上游产物名')
    dup(all_fnames, '目标文件名')
    dup(used_numbers(), '09xx 编号')

    # 编号必须是 4 位数字，且 09xx 段的号要能排上序
    for slug, fname, _t in HOWTO:
        if not (fname[:4].isdigit() and len(fname) >= 5):
            problems.append(f'howto 的文件名没以 4 位编号开头：{fname}（{slug}）')

    # ★ 表内顺序**必须**是编号升序。以前 0929 故意插在 0917/0918 之间（照上游
    #   `howto/index.rst` 的分组位置）；2026-09-27 起 `Python 指南` 不再分组、
    #   书签直接按表内顺序平铺 —— 于是「表内顺序」与「编号」不再是两个维度，
    #   插错位置就会让合并册的书签乱序。
    nums = [f[:4] for _s, f, _t in HOWTO]
    if nums != sorted(nums):
        first = next((f'{a} → {b}' for a, b in zip(nums, nums[1:]) if a > b), '?')
        problems.append(f'HOWTO 表不是编号升序（第一处 {first}）—— '
                        f'合并册的 Python 指南 直接按表内顺序排书签')

    # ★ MERGE_ORDER 必须与 MAIN / TAIL 一一对应：漏一册 → 合并册静默少一章；
    #   多一个不存在的键 → build_spec 直接 KeyError。
    top_slugs = [s for s, _n, _t in (*MAIN, *TAIL)]
    seen_keys = [k for k in MERGE_ORDER if k != HOWTO_KEY]
    dup(seen_keys, 'MERGE_ORDER 项')
    for k in seen_keys:
        if k not in top_slugs:
            problems.append(f'MERGE_ORDER 里的 {k} 不在 MAIN/TAIL 里')
    for s in top_slugs:
        if s not in seen_keys:
            problems.append(f'{s} 没写进 MERGE_ORDER（合并册里会少这一册）')

    # MIN_VERSION / MAX_VERSION 的 slug 必须真的存在，且区间本身要站得住
    known = set(all_slugs)
    for slug, ver in MIN_VERSION.items():
        if slug not in known:
            problems.append(f'MIN_VERSION 里的 {slug} 不在清单里（最低版本 {ver[0]}.{ver[1]}）')
    for slug, ver in MAX_VERSION.items():
        if slug not in known:
            problems.append(f'MAX_VERSION 里的 {slug} 不在清单里（最高版本 {ver[0]}.{ver[1]}）')
        lo = MIN_VERSION.get(slug)
        if lo and lo > ver:
            problems.append(f'{slug} 的版本区间反了：min {lo[0]}.{lo[1]} > '
                            f'max {ver[0]}.{ver[1]}')

    # 每个版本都要能自洽：门控掉的不能同时又被算进 expected
    for ver in KNOWN_VERSIONS:
        exp = expected(ver)
        if not exp:
            problems.append(f'{ver} 的应有清单是空的（门控写反了？）')
        if len(exp) != len(set(exp)):
            problems.append(f'{ver} 的应有清单里有重名')
        if not build_spec(ver):
            problems.append(f'{ver} 的合并册大纲是空的')
    return problems

# ---------------------------------------------------------------------------
# 内置工具：check-doc-refs.py（原样内联，逻辑一行未改）
#   入口：cdr_main
# ---------------------------------------------------------------------------
# """检查 Doc/ 里的 RST 是否引用了「在 Doc/ 之外、但又不存在」的文件。
#
# 为什么需要它
# ------------
# CPython 的文档并不全在 `Doc/` 里：
#
# * 语法全文   `Grammar/python.gram`      ← `reference/grammar.rst` 用 literalinclude
# * ASDL 定义  `Parser/Python.asdl`       ← `library/ast.rst` 用 literalinclude
# * Tachyon 配图 `Lib/profiling/sampling/_assets/tachyon-logo.png`
#                                         ← `whatsnew/3.15.rst` 等用 image
# * 版本号     `Include/patchlevel.h`     ← `Doc/tools/extensions/patchlevel.py` 读它
# * 变更日志   `Misc/NEWS.d/`             ← `Doc/Makefile` 的 build 目标
#
# 本项目用 `git clone --filter=blob:none --sparse` 只取需要的目录。**一旦漏取，
# Sphinx 不会报错**，两种后果都很隐蔽：
#
# * `literalinclude` / `include` —— 这段内容被**直接跳过**，`.tex` 里什么都不写
#   → **PDF 里整章空白**。实测 3.13 / 3.14 / 3.15 的《完整的语法规范》整章只剩
#   标题与两行引言（第 150 页空白、586 字节），因为 `Grammar/` 不在稀疏检出里 ——
#   那一章本该有 20 多页。
# * `image` / `figure` —— 把**原始相对路径**原样写进 `.tex`；Windows 上分隔符是
#   反斜杠，`..\\Lib\\profiling\\...` 里的 `\\Lib` `\\profiling` 全成了未定义控制序列
#   → xelatex 报错、latexmk 退出码 12、这一册整本不出 PDF。
#
# 所以「Doc 需要哪些 Doc/ 之外的文件」是一件**可以直接量出来的事实**，不该靠人记。
# 本脚本把它量出来，并和磁盘现状对照。
#
# 用法::
#
#     python tools/check-doc-refs.py <Doc 目录>
#     python tools/check-doc-refs.py <Doc 目录> --list    # 只列引用，不判缺失
#
# 输出（★ ASCII 标记，供 GUI / bash 判定；中文行只给人看）::
#
#     REFMISSING <n>   越界且缺失的引用条数（0 = 都齐）
#
# 退出码：0 = 都齐；1 = 有缺失（可继续跑，但 PDF 会静默少内容 / 编不过）；
# 2 = 参数或环境错误。
#
# 注意：本脚本**不碰网络**。唯一会用到 git 的地方是「判定一个路径是单文件还是目录」
# （`git ls-tree` 的 objecttype），见 `_kind()` —— `--filter=blob:none` 的仓库里
# tree 对象全在本地，所以这一步不触网。不是 git 仓库（比如从 tarball 解出来的 Doc）
# 时会自动退回启发式，脚本照样能跑。
#
# 输出除了给人看的说明，还有一串 **ASCII 标记**（供 GUI / bash 判定，见上面 `--list`）：:
#
#     MISSINGFILE <仓库相对路径>      缺哪个文件（GUI 的自动补件清单）
#     MISSINGKIND <仓库相对路径> <kind>  它是 blob（单文件）还是 tree（目录）
#                                     kind 取 `blob` / `tree` / `?`（判不出来）
#     REFMISSING <n>                  缺几条（0 = 都齐）
# """


import argparse
import re
import subprocess
import sys
from pathlib import Path

#: Doc 里会「走出 Doc/」的三种指令。
#: 刻意不含 `:file:` / `:source:` 这类角色 —— 它们只生成链接文本，不影响 PDF 内容。
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("图片", re.compile(r"^\.\.\s+(?:image|figure)::\s+(\S+)", re.M)),
    ("代码块", re.compile(r"^\.\.\s+literalinclude::\s+(\S+)", re.M)),
    ("包含", re.compile(r"^\.\.\s+include::\s+(\S+)", re.M)),
)


def scan(doc: Path) -> tuple[list[tuple[str, str, str, Path]], list[tuple[str, str, str, Path]]]:
    """扫一遍 Doc，返回 (所有以 `../` 开头的引用, 其中真正走出 Doc/ 的引用)。

    分两层是因为两者都值得知道，但含义不同：

    * 以 `../` 开头的很多（Doc 内部常见的兄弟目录互引，如 `../deprecations/`），
      它们**都在 Doc 里**，稀疏克隆取了 `Doc` 就一定有 —— 不用管；
    * 真正走出 `Doc/` 的才是要盯的（Grammar / Parser / Lib / Misc / Include），
      **稀疏检出必须显式包含它们**，否则就是静默少内容。
    """
    all_refs: list[tuple[str, str, str, Path]] = []
    outside: list[tuple[str, str, str, Path]] = []
    try:
        doc_real = doc.resolve()
    except OSError:
        doc_real = doc
    for rst in sorted(doc.rglob("*.rst")):
        try:
            text = rst.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for kind, pat in PATTERNS:
            for m in pat.finditer(text):
                tgt = m.group(1).strip()
                if not tgt.startswith("../") or "://" in tgt:
                    continue
                resolved = (rst.parent / tgt).resolve()
                rel = str(rst.relative_to(doc)).replace("\\", "/")
                all_refs.append((kind, rel, tgt, resolved))
                # ★ 判据用「解析后的路径是否还在 Doc/ 之下」，而不是「以 ../ 开头」：
                #   `../deprecations/x.rst` 从 Doc/library/ 出发仍在 Doc/ 内。
                if not resolved.is_relative_to(doc_real):
                    outside.append((kind, rel, tgt, resolved))
    return all_refs, outside


def need_paths(refs: list[tuple[str, str, str, Path]], repo_root: Path | None = None) -> list[str]:
    """从越界引用反推「稀疏检出至少要包含哪些条目」。

    * 目录形态的（如 `Grammar/python.gram`）报到**层级最深的一级**为止，
      但不超过三层 —— 报 `Lib` 会把整个标准库拖下来；
    * 单文件（如 `Lib/test/exception_hierarchy.txt`）要报到文件本身，
      因为 cone 模式取不了「目录里的某一个文件」，得靠 `git show` 单独取。
    """
    paths: set[str] = set()
    for _k, _r, _t, resolved in refs:
        if repo_root is not None:
            try:
                rel = resolved.relative_to(repo_root)
            except ValueError:
                continue
            paths.add(str(rel).replace("\\", "/"))
    return sorted(paths)


def _kind(repo_root: Path, rel: str) -> str:
    """问 git：`rel` 在 HEAD 里是 `blob`（单文件）还是 `tree`（目录）。

    ★★ 为什么非问不可 ★★
    曾经这里（以及 `gui/pdf_builder_multi.py` 里的同一处判断）用的是
    「最后一段带不带 `.`」这个启发式。它栽在 `Modules/expat/COPYING` 上 ——
    这文件没有扩展名，于是被当成**目录**，建议出：

        git sparse-checkout set Doc Misc/NEWS.d ... Modules/expat/COPYING
        fatal: 'Modules/expat/COPYING' is not a directory;
               to treat it as a directory anyway, rerun with --skip-checks

    后果不是「建议不准确」，而是**整条自动补件链路当场失效**：GUI 的
    `_ensure_doc_ref_files` 拿着这条命令重试两次、都失败，最后只留下一句
    「补目录失败（多为 GitHub 代理断流）」—— 把病因指到了一个完全无关的方向，
    而真实的缺口（3.15 新增的 `Doc/license.rst` 要 include 它）始终没被补上，
    步骤 6 于是永远卡在同一处。凡是「靠文件名形状猜类型」的判断，都会遇到
    没有扩展名的 `COPYING` / `LICENSE` / `Makefile` / `NEWS` / `README`，
    所以这里改成向 git 要事实。

    ★ 不触网：`--filter=blob:none` 只过滤 blob，tree 对象全在本地，
      所以 `ls-tree`（不带 `-l`，不读 blob 内容）纯本地完成。
    ★ 返回 `''` = 说不清（`.git` 不在 / 没装 git / 路径不在 HEAD 里），
      调用方退回启发式。
    """
    if not (repo_root / ".git").exists():
        return ""
    try:
        p = subprocess.run(["git", "-C", str(repo_root), "ls-tree", "HEAD", "--", rel],
                           capture_output=True, creationflags=CREATE_NO_WINDOW)
    except OSError:
        return ""
    if p.returncode != 0:
        return ""
    lines = p.stdout.decode("utf-8", "replace").strip().splitlines()
    if not lines:
        return ""
    parts = lines[0].split()                      # <mode> <type> <hash>\t<path>
    return parts[1] if len(parts) >= 2 and parts[1] in ("blob", "tree") else ""


def classify(paths: list[str], repo_root: Path) -> tuple[list[str], list[str]]:
    """把待补路径分成 (目录, 单文件)，供「怎么补」选用不同命令。

    * **目录**（稀疏检出里整个没有）→ `git sparse-checkout add <目录>`
    * **单文件** → `git show HEAD:<文件>` 按需拉那一个 blob
      —— cone 模式的最小单位是目录，为一个文件把整个大目录（如 `Lib/test/`）
      拖下来不划算。

    `_kind()` 说不清时才退回「最后一段有没有点」——宁可给个可能不准的建议，
    也不要什么都不给（而且返回 `'?'` 会出现在 ASCII 标记里，调用方看得见）。
    """
    dirs: list[str] = []
    files: list[str] = []
    for p in paths:
        k = _kind(repo_root, p)
        if k == "tree":
            dirs.append(p)
        elif k == "blob":
            files.append(p)
        else:
            (files if "." in p.rsplit("/", 1)[-1] else dirs).append(p)
    return dirs, files


def _pstr(p: Path) -> str:
    """路径转成**正斜杠**写法 —— 提示里的命令常被直接粘进 git-bash。"""
    return str(p).replace("\\", "/")


def cdr_main() -> int:
    ap = argparse.ArgumentParser(
        description="检查 Doc/ 里指向 Doc/ 之外的引用是否都取到了")
    ap.add_argument("doc", type=Path, help="CPython 的 Doc 目录")
    ap.add_argument("--list", action="store_true",
                    help="只列出引用并给标记，不做详细判定")
    ap.add_argument("--quiet", action="store_true", help="只在有问题时输出")
    args = ap.parse_args()

    doc: Path = args.doc
    if not (doc / "conf.py").is_file():
        print(f"!! 这不像 CPython 的 Doc 目录：{doc}/conf.py 不存在", file=sys.stderr)
        return 2

    repo_root = doc.resolve().parent                  # cpython/Doc → cpython
    all_refs, outside = scan(doc)
    missing = [(k, r, t, p) for k, r, t, p in outside if not p.exists()]

    if not args.quiet:
        print(f"Doc 越界引用自检：以 ../ 开头的 {len(all_refs)} 条，"
              f"其中真正走出 Doc/ 的 {len(outside)} 条"
              f"（其余都在 Doc/ 内部，取了 Doc 就一定有）")
        if outside:
            print("  走出 Doc/ 的目标（稀疏检出必须覆盖）：")
            for p in need_paths(outside, repo_root):
                print(f"      {p}")

    if args.list:
        for _k, _r, _t, p in missing:
            print("MISSINGFILE " + _rel(p, repo_root))
        for rel in need_paths(missing, repo_root):
            print(f"MISSINGKIND {rel} {_kind(repo_root, rel) or '?'}")
        print(f"REFMISSING {len(missing)}")
        return 1 if missing else 0

    if missing:
        print(f"  [错误] 其中 {len(missing)} 条的目标文件不在磁盘上 ——\n"
              f"      literalinclude / include 缺了，Sphinx **不会报错**，"
              f"PDF 里那一节整段空白；\n"
              f"      image / figure 缺了，会把原始反斜杠路径写进 .tex、"
              f"整册编不出来。")
        for kind, rst, tgt, p in missing:
            print(f"      [{kind}] {rst}  →  {tgt}")
            print(f"             期望位置：{p}")
        dirs, files = classify(need_paths(missing, repo_root), repo_root)
        cpy = _pstr(repo_root)
        print("  处理（幂等，只补差集，不重头克隆）：")
        if dirs:
            print(f"      git -C {cpy} sparse-checkout add " + " ".join(dirs))
        for f in files:
            print(f"      git -C {cpy} show HEAD:{f} > {cpy}/{f}")
        if files:
            print("          （单文件走 `git show` 按需拉 blob —— cone 模式的"
                  "最小单位是目录，为一个大目录里的个把文件把整目录拖下来不划算；"
                  "上面这条命令可直接粘贴执行）")
    elif not args.quiet:
        print("  所有目标的文件都在 ✔")

    for _k, _r, _t, p in missing:
        print("MISSINGFILE " + _rel(p, repo_root))
    print(f"REFMISSING {len(missing)}")
    return 1 if missing else 0


def _rel(p: Path, root: Path) -> str:
    try:
        return str(p.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")

# ---------------------------------------------------------------------------
# 内置工具：alias-po.py（原样内联，逻辑一行未改）
#   入口：alpo_main
# ---------------------------------------------------------------------------
# """给「上游改了目录、zh-CN 翻译还留在旧目录」的 .rst 找回它的译文。
#
# 为什么需要它
# ------------
# 步骤 3 是「按目录层级」把 `zh-cn/**/*.po` 铺进 `Doc/locales/zh_CN/LC_MESSAGES/`，
# Sphinx 再按 **源文件相对路径** 去 `LC_MESSAGES/<同样的相对路径>.po` 找译文。
#
# 对应关系一旦断掉，Sphinx **不报错、不警告**（连 `translation progress` 都是 100%），
# 那一页就与原文一字不差地保持英文 —— 整册读起来像没翻译过。
#
# 实测：CPython 3.14.7 把
#
#     Doc/library/stdtypes.rst      →  Doc/builtins/stdtypes.rst
#     Doc/library/constants.rst     →  Doc/builtins/constants.rst
#     Doc/library/functions.rst     →  Doc/builtins/functions.rst
#     Doc/library/exceptions.rst    →  Doc/builtins/exceptions.rst
#     Doc/library/threadsafety.rst  →  Doc/builtins/threadsafety.rst
#
# 整章搬进了 `Doc/builtins/`，而 python-docs-zh-cn 的 `3.14` 分支里译文仍在
# `zh-cn/library/*.po`（`.po` 里的 `#:` 位置注释也还写着 `../../library/stdtypes.rst`）。
# 于是《11Python 内置参考手册》**整册 196 页全是英文**，构建日志一片绿。
#
# 这不是本项目的 bug（官网 docs.python.org/zh-cn/3.14/library/stdtypes.html 正文同样是
# 英文），但可以把译文「接」到新路径上，让产物比官网更完整。
#
# 怎么确定「这个 .po 就是那个 .rst 的译文」
# ------------------------------------------
# 不能只比文件名 —— `.po` 的 msgid **就是英文原文**，所以拿 msgid 去 `.rst` 原文里找，
# 命中率就是最直接的证据：
#
# * 配对正确：绝大多数长 msgid 都能在 .rst 里原样找到（实测 0.6~0.95）
# * 配错（如同名不同文）：几乎为 0
#
# 本脚本因此把「文件名相同」当作**候选**，把「msgid 重合度 ≥ 阈值」当作**判据**。
# 实测正确配对最低 0.60、错误配对数 0.00 —— 阈值 0.35 已有足够安全边距。
#
# 用法::
#
#     python tools/alias-po.py <zh-cn 目录> --doc <Doc 目录> --locale <LC_MESSAGES 目录>
#     python tools/alias-po.py <zh-cn 目录> --doc <Doc 目录> --locale <...> --dry-run
#
# 三类来源
# --------
# 1. **官方译文放错了目录**（主要场景）：靠 msgid 重合度自动配对，见上。
# 2. **官方根本没翻这一页**：`--extra <目录>` 指向项目自带的「补充译文」目录
#    （`sphinx-pdf/i18n-extra/`），里面的 `.po` 按**相同相对路径**铺进 locale。
#    实测这类页有 `builtins/index.rst`（章的标题与引言）和
#    `builtins/time-complexity.rst` —— 全量扫 535 个 `.po` 的最佳配对都是 0.00。
#    补充译文是**本项目**译的，不是官方译文，文件头会写明。
# 3. **原文只改了大小写，msgid 就失配了**：见 `fix_msgid_drift()`。3.15 实测：
#    `Doc/builtins/functions.rst` 的章标题从 `Built-in Functions` 改成
#    `Built-in functions`，译文条目仍写着旧 msgid → 不算命中 → 那一章的书签
#    静默变回英文（3.14 是「内置函数」）。**同样零报错、零 warning**。
#    自动把「大小写折叠后唯一对应、且译文含中文」的那条接过去。
#
# 输出（★ ASCII 标记，供 GUI / bash 判定；中文行只给人看）::
#
#     ALIAS <Doc 内相对路径> <- <zh-cn 内相对路径>  (msgid 命中 120/129 = 0.93)
#     EXTRA <Doc 内相对路径> <- <补充译文目录内相对路径>
#     DRIFT <po 内相对路径>  "<旧 msgid>" → "<新 msgid>"  （自动修补的失效译文）
#     ALIASED <n>   本次新铺的**别名**条目数（0 = 没有漏译，正常）
#     EXTRAED <n>   本次新铺的**补充译文**条目数（0 = 不缺，正常）
#     DRIFTED <n>   本次修补的**msgid 漂移**条目数（0 = 没有失效译文，正常）
#
# 退出码：0 = 正常；2 = 参数或环境错误。
#
# 注意：本脚本**幂等**，只补「目标路径没有 .po」的缺口，绝不覆盖已有译文；
# 只读磁盘、不碰网络、不碰 git。
# """


import argparse
import re
import shutil
import sys
from pathlib import Path

#: gettext 认得的源文件后缀（Sphinx 的 gettext builder 也处理 .inc / .txt）。
SOURCE_SUFFIXES: tuple[str, ...] = (".rst", ".inc", ".txt")

#: 这些文件名撞车太多、含义完全取决于所在目录，**不做别名**。
#: ★ 2026-09-27 实测确认这是对的：曾以为 `Doc/builtins/index.rst` 的译文是
#:   `zh-cn/library/builtins.po`（文件名 = 目录名），但拿 msgid 一比对是 **0/9 = 0.00**
#:   —— `library/builtins.po` 其实是**旧版** `Doc/library/builtins.rst`
#:   （`:mod:`!builtins` --- Built-in objects`，3.14 已被拆掉）的译文。
#:   实测把 535 个 .po 全扫一遍，`builtins/index.rst` 的最佳候选也是 0.00：
#:   **上游根本没翻这一页**。这类页面只能靠 `--extra` 的补充译文。
NO_ALIAS_STEMS: frozenset[str] = frozenset({"index"})

#: 参与判据的 msgid 最短长度。太短的（"True"、":ref:`x`"）在别处也常见，没有证明力。
MIN_MSGID_LEN = 20

#: 有效样本下限与命中率下限。见模块 docstring 的实测数据。
MIN_SAMPLES = 5
MIN_RATIO = 0.35

#: po 里的转义序列 → 归一化时要还原成一个空白。
_ESCAPES = {"\\n": " ", "\\t": " ", "\\\\": "\\", '\\"': '"', "\\'": "'"}


def parse_msgids(text: str) -> list[str]:
    """从 .po 文本里抽出全部 msgid（跳过 msgstr 与废弃条目 `#~`）。

    只认 `msgid` 与紧跟其后的续行 `"..."`；`msgctxt` 的正文一并计入
    （Sphinx 的 msgctxt 是章节路径，拼上更利于比对，不加也无妨）。
    """
    ids: list[str] = []
    cur: list[str] | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if line.startswith("#~"):
            continue
        if cur is not None and line.startswith('"'):
            cur.append(_unquote(line))
            continue
        m = re.match(r'^(msgid|msgctxt)\s+"(.*)"\s*$', line)
        if m:
            if m.group(1) == "msgid":
                if cur:
                    ids.append("".join(cur))
                cur = [_unquote(line.split(None, 1)[1])]
            else:                                   # msgctxt 并入当前条目
                if cur is None:
                    cur = []
                cur.append(_unquote(line.split(None, 1)[1]) + " ")
            continue
        if line.startswith(("msgstr", '"', "#", "msgid_plural")):
            continue
        if line.strip() == "":
            if cur:
                ids.append("".join(cur))
                cur = None
    if cur:
        ids.append("".join(cur))
    return [i for i in ids if i]


def _unquote(s: str) -> str:
    s = s.strip()
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        s = s[1:-1]
    for a, b in _ESCAPES.items():
        s = s.replace(a, b)
    return s


def norm(text: str) -> str:
    """把换行、缩进、转义全压成单个空格 —— 让「折行了没」不再影响比对。"""
    for a, b in _ESCAPES.items():
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip()


def overlap(rst_text: str, po_text: str) -> tuple[int, int]:
    """返回 (命中的长 msgid 数, 参与比对的长 msgid 数)。"""
    hay = norm(rst_text)
    samples = [n for n in (norm(i) for i in parse_msgids(po_text)) if len(n) >= MIN_MSGID_LEN]
    hits = sum(1 for n in samples if n in hay)
    return hits, len(samples)


def collect_rel(root: Path, suffixes: tuple[str, ...]) -> dict[str, Path]:
    """目录里全部匹配后缀的文件，键是 posix 相对路径（小写键只用于比对）。"""
    out: dict[str, Path] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in suffixes and not _hidden(p, root):
            out[p.relative_to(root).as_posix()] = p
    return out


def _hidden(p: Path, root: Path) -> bool:
    return any(part.startswith(".") for part in p.relative_to(root).parts)


# ── 第五节失败：原文只改了大小写，译文的 msgid 就失配了 ─────────────────────
#: RST 的标题下划线允许这些字符（CPython 实际只用 = - ~ ^ " '）。
_UNDERLINE_CHARS = set("=-~^\"'#*+")
#: 判「这条 msgstr 真的是中文译文」—— 防止把修复做成「换个英文 msgstr」。
#: ★ 名字加 `alpo_` 前缀：本文件顶部也有一个 `CJK_RE`（判「这一册被翻译了没有」），
#:   内联后同名会让后者把前者覆盖掉 —— 那种「看着没事、判据悄悄换了」的坑
#:   正是本次内联最容易踩的，所以每个工具段里的全局名都带自己的前缀。
alpo_CJK_RE = re.compile(r"[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]")


def section_titles(text: str) -> list[str]:
    """抽出 .rst 里全部章节标题（= 下一行是「全同一种下划线字符、且不短于标题」）。

    ★ 长度判据用 RST 自己的规则（下划线不得短于标题），能挡掉大量误判：
      表格边框、代码块里的 `----`、`====` 都会因为「上一行不是同长的标题」被排除。
    """
    out: list[str] = []
    lines = text.splitlines()
    for i in range(len(lines) - 1):
        title, under = lines[i].rstrip(), lines[i + 1].rstrip()
        if not title.strip() or not under.strip():
            continue
        if under[0] not in _UNDERLINE_CHARS or len(set(under)) != 1:
            continue
        if len(under) < len(title):          # RST：下划线短于标题会被 Sphinx 警告
            continue
        out.append(title.strip())
    return out


def po_map(raw: str) -> dict[str, str]:
    """{msgid: msgstr}（均已解码）。只收非废弃条目，续行也算。"""
    out: dict[str, str] = {}
    cur_id: str | None = None
    cur_str: list[str] = []
    in_str = False
    for line in raw.splitlines():
        line = line.rstrip("\r")
        if line.startswith("#~"):
            continue
        m = re.match(r'^msgid\s+"(.*)"\s*$', line)
        if m:
            if cur_id is not None:
                out.setdefault(cur_id, "".join(cur_str))
            cur_id, cur_str, in_str = _unquote(m.group(1)), [], False
            continue
        m = re.match(r'^msgstr\s+"(.*)"\s*$', line)
        if m:
            cur_str, in_str = [_unquote(m.group(1))], True
            continue
        if cur_id is not None and in_str and line.startswith('"'):
            cur_str.append(_unquote(line))
            continue
        if not line.strip():
            if cur_id is not None:
                out.setdefault(cur_id, "".join(cur_str))
            cur_id, cur_str, in_str = None, [], False
    if cur_id is not None:
        out.setdefault(cur_id, "".join(cur_str))
    return out


def _po_quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fix_msgid_drift(locale: Path, doc: Path,
                    dry_run: bool = False) -> list[tuple[str, str, str, str]]:
    """修第五类哑失败：**原文改了大小写，译文的 msgid 就失配了**。

    ★★ 为什么需要（3.15 实测）★★
    CPython 把 `Doc/builtins/functions.rst` 的章标题从 `Built-in Functions`
    改成了 `Built-in functions`（只差一个字母的大小写）。zh-cn 的译文条目仍是
    `msgid "Built-in Functions" / msgstr "内置函数"` —— **msgid 一字之差就不算命中**，
    Sphinx 于是静默回退英文：那一章在 PDF 书签里就叫 `Built-in functions`，
    而所有日志全绿、`translation progress` 也不会掉。3.14 是 `内置函数`，
    3.15 变成英文，就是这么来的。

    判据（**只认最保守的一种漂移**）：
      1. 目标 `.rst` 里的**章节标题** T 不是该 `.po` 的任何 msgid；
      2. `.po` 里存在**唯一**一条 msgid M 满足 `M.casefold() == T.casefold()`；
      3. M 的 msgstr 非空**且含中文**（否则「修复」等于换个英文，没有意义）。
    满足就把 `msgid T / msgstr <M 的译文>` **追加**到 `.po` 末尾（幂等：已在就跳过）。
    ⚠️ 反过来（T 命中、M 不命中）不管 —— 那只是上游删了旧标题，`.po` 里的死条目
      不影响排版。
    ⚠️ 有意**不做**模糊匹配：措辞真变了就该重译，猜出来的译文比英文更糟。
      实测全 549 个 `.po` 里这种「只差大小写」的章标题**只有 1 条**（见 skill 坑 43）。

    返回 [(po 相对路径, 旧 msgid, 新 msgid, msgstr)]。
    """
    fixed: list[tuple[str, str, str, str]] = []
    for po in sorted(locale.rglob("*.po")):
        rel = po.relative_to(locale).as_posix()
        rst = doc / Path(rel).with_suffix(".rst")
        if not rst.is_file():
            continue
        try:
            raw = po.read_text(encoding="utf-8", errors="replace")
            body = rst.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # 末尾必须是完整的 msgstr（以引号收尾）—— 半截文件直接不碰，免得越修越坏
        tail = next((ln.strip() for ln in reversed(raw.splitlines()) if ln.strip()), "")
        if not tail.endswith('"'):
            continue
        entries = po_map(raw)
        ids = set(entries)
        if not ids:
            continue
        # 大小写折叠 → msgid；一旦有两个候选就视为说不清，放弃（宁可不修也不猜）
        fold: dict[str, str | None] = {}
        for k in ids:
            f = k.casefold()
            fold[f] = k if f not in fold else None
        add: list[tuple[str, str, str]] = []
        for title in section_titles(body):
            if title in ids or len(title) < 3 or "\n" in title:
                continue
            old = fold.get(title.casefold())
            if not old:
                continue
            msgstr = entries.get(old, "")
            if not msgstr or not alpo_CJK_RE.search(msgstr):
                continue
            add.append((old, title, msgstr))
        if not add:
            continue
        if not dry_run:
            with po.open("a", encoding="utf-8") as fh:
                for old, new, msgstr in add:
                    fh.write(
                        f"\n# ★ 自动修补：原文只改了大小写，msgid 失配 → 标题静默回退英文\n"
                        f"#   旧 msgid：{old}\n"
                        f"msgid {_po_quote(new)}\n"
                        f"msgstr {_po_quote(msgstr)}\n")
        for old, new, msgstr in add:
            fixed.append((rel, old, new, msgstr))
    return fixed


def alpo_main() -> int:
    ap = argparse.ArgumentParser(
        description="把「目录被上游搬走」的 .po 接到新路径上，救回整册漏译")
    ap.add_argument("zh", type=Path, help="zh-cn 翻译源目录（.po 树）")
    ap.add_argument("--doc", type=Path, required=True, help="CPython 的 Doc 目录")
    ap.add_argument("--locale", type=Path, required=True,
                    help="Doc/locales/<lang>/LC_MESSAGES 目录")
    ap.add_argument("--extra", type=Path, default=None,
                    help="项目自带的「补充译文」目录（如 sphinx-pdf/i18n-extra）："
                         "官方没翻的页（builtins/index.rst 等）按相同相对路径补进去。"
                         "只补缺口，绝不覆盖 locale 里已有的译文")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不拷贝")
    ap.add_argument("--quiet", action="store_true", help="只在有别名时输出")
    args = ap.parse_args()

    zh: Path = args.zh
    doc: Path = args.doc
    locale: Path = args.locale
    if not zh.is_dir():
        print(f"!! 翻译源目录不存在：{zh}", file=sys.stderr)
        return 2
    if not (doc / "conf.py").is_file():
        print(f"!! 这不像 CPython 的 Doc 目录：{doc}/conf.py 不存在", file=sys.stderr)
        return 2
    locale.mkdir(parents=True, exist_ok=True)

    sources = collect_rel(doc, SOURCE_SUFFIXES)
    installed = {p.relative_to(locale).as_posix() for p in locale.rglob("*.po")}
    pool = collect_rel(zh, (".po",))

    # 按文件名（stem）建反查表 —— 候选只可能来自同名文件。
    by_stem: dict[str, list[str]] = {}
    for rel in pool:
        by_stem.setdefault(Path(rel).stem.lower(), []).append(rel)

    aliased: list[tuple[str, str, str]] = []
    considered = 0
    for rel, src in sorted(sources.items()):
        # ★ 必须 .as_posix()：Windows 上 str(WindowsPath) 是反斜杠，
        #   而 installed 的键是 posix —— 不统一就会把「已装好」误判成「缺口」，
        #   于是把同一个文件自己 ALIAS 给自己。
        po_rel = Path(rel).with_suffix(".po").as_posix()
        if po_rel in installed:
            continue
        stem = Path(rel).stem.lower()
        if stem in NO_ALIAS_STEMS:
            continue
        cands = by_stem.get(stem)
        if not cands:
            continue
        considered += 1
        try:
            body = src.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        best: tuple[float, int, int, str] | None = None
        for c in cands:
            try:
                po_text = (zh / c).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            hits, total = overlap(body, po_text)
            if total < MIN_SAMPLES:
                continue
            ratio = hits / total
            if best is None or ratio > best[0]:
                best = (ratio, hits, total, c)
        if best and best[0] >= MIN_RATIO:
            aliased.append((po_rel, best[3], f"{best[1]}/{best[2]} = {best[0]:.2f}"))

    if aliased and not args.quiet:
        print(f"发现 {len(aliased)} 个「上游搬了目录」的译文（候选 {considered} 个，"
              f"重合度达标才收）：")
    for po_rel, src_rel, stat in aliased:
        tgt = locale / po_rel
        if not args.dry_run:
            tgt.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(zh / src_rel, tgt)
        print(f"  ALIAS {po_rel}  <-  {src_rel}   (msgid 命中 {stat})")
    if aliased:
        verb = "待铺" if args.dry_run else "已铺"
        print(f"  说明：这些页在源仓库里就是英文，{verb}后 PDF 反而比官网更完整")

    # ── 补充译文：官方没翻的页，由本项目补（按相同相对路径铺） ──────────────
    extra_n = 0
    if args.extra is not None:
        if not args.extra.is_dir():
            print(f"!! --extra 目录不存在：{args.extra}", file=sys.stderr)
        else:
            # 重新扫一遍：上面刚铺过别名，别把同一个位置算成缺口
            have = {p.relative_to(locale).as_posix() for p in locale.rglob("*.po")}
            todo = []
            for po in sorted(args.extra.rglob("*.po")):
                rel = po.relative_to(args.extra).as_posix()
                if rel in have:
                    continue
                todo.append((rel, po))
            if todo and not args.quiet:
                print(f"发现 {len(todo)} 个「官方没有译文、由本项目补充」的页"
                      f"（来自 {args.extra}）：")
            for rel, po in todo:
                tgt = locale / rel
                if not args.dry_run:
                    tgt.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(po, tgt)
                extra_n += 1
                print(f"  EXTRA {rel}  <-  {po.relative_to(args.extra).as_posix()}")
            if todo:
                verb = "待铺" if args.dry_run else "已铺"
                print(f"  说明：这些页的译文本项目自己译的（非官方），{verb}后 PDF 比官网完整")

    # ── 第三类：原文只改了大小写 → 译文 msgid 失配 → 标题静默回退英文 ────────
    # ★ 放在最后跑：此时 locale 已经装齐（含上面刚铺的别名与补充译文），
    #   扫的就是最终生效的那份 .po。
    drift = fix_msgid_drift(locale, doc, dry_run=args.dry_run)
    if drift and not args.quiet:
        print(f"发现 {len(drift)} 条「原文改了大小写、译文 msgid 失配」的条目"
              f"（不修就会静默显示英文）：")
    for rel, old, new, msgstr in drift:
        print(f"  DRIFT {rel}  {old!r} → {new!r}  msgstr={msgstr!r}")
    if drift:
        verb = "待补" if args.dry_run else "已补"
        print(f"  说明：{verb}的是**同一标题**的历史译文（大小写折叠后唯一对应），"
              f"不改动其它条目；源文件重跑步骤 3 会再次自动补上，幂等。")

    print(f"ALIASED {len(aliased)}")
    print(f"EXTRAED {extra_n}")
    print(f"DRIFTED {len(drift)}")
    return 0

# ---------------------------------------------------------------------------
# 内置工具：localize-titles.py（原样内联，逻辑一行未改）
#   入口：loct_main
# ---------------------------------------------------------------------------
# """把 Sphinx 产出的 .tex 封面标题（\\title{...}）换成中文。
#
# 为什么需要这一步
# ----------------
# Sphinx 手册的封面标题来自 `conf.py` 的 `latex_documents`，而 **`latex_documents`
# 不经过 .po 翻译**（Sphinx 对它的多语言支持只覆盖 `latex_documents` 的
# `target`/`title` 的一部分实现，CPython 的 conf.py 里就是硬编码英文）。所以
# 中文文档构建出来后：
#
#     04 封面 = "The Python Language Reference"
#     05 封面 = "The Python Library Reference"
#     11 封面 = "Python Built-ins Reference"
#
# 而同一册的**文件名**和**书签**都是中文，两套不一致。
# HOWTO 那批的标题来自 reST 正文标题（`latex_documents` 里给的是空串 `''`），
# 所以只要译文存在就是中文；只有 `howto-perf_profiling` 上游没译，也是英文。
#
# 做法
# ----
# 按 `.tex` 文件名查表，重写里面的 `\\title{...}`。
# - `\\title` 同时被 sphinxmanual.cls 用于**页眉**，所以改一处，封面和每页页眉
#   一起变中文；
# - 幂等：已经是目标中文就不再改；
# - `whatsnew` 的标题里带版本号，从同一文件里的 `\\release{3.14.7}` 推出 `3.14`，
#   这样以后换版本不用改代码。
#
# 用法
# ----
#     python tools/localize-titles.py <latex 目录>            # 应用
#     python tools/localize-titles.py <latex 目录> --dry-run   # 只看要改什么
#     python tools/localize-titles.py <latex 目录> --list      # 只列出待改册子名
# """

import argparse
import re
import sys
from pathlib import Path

# 中文标题取自两种权威来源，优先级：参考样张的顶层书签/文件名 > 上游 zh-CN 译文
#   01/02/03/04/05/06/07/08/10 —— 与参考样张《Python文档3.14.0 1002》的顶层书签
#                                 及本项目文件名逐字一致
#   11 builtins —— 上游 python-docs-zh-cn 3.14 **无 builtins 目录**（见
#                 .workbuddy/memory/2026-09-21.md），故按 "…Reference → …参考手册"
#                 的既有惯例自拟（同《Python 语言参考手册》《Python C API 参考手册》）
#   0924 perf_profiling —— 上游无译文，沿用参考样张文件名的中文
TITLES: dict[str, str] = {
    "whatsnew": "Python {v} 有什么新变化",          # {v} 由 \release 推出，如 3.14
    "tutorial": "Python 教程",
    "using": "Python安装和使用",                     # 参考样张此处"Python"后无空格，照抄
    "reference": "Python 语言参考手册",
    "library": "Python 标准库",
    "extending": "扩展和嵌入 Python 解释器",
    "c-api": "Python C API 参考手册",                # 上游 reST 标题作 "Python/C API…"，
    #                                                  但 "/" 进不了文件名，参考样张的书签
    #                                                  与文件名都是无斜杠版，故统一取无斜杠
    "installing": "安装 Python 模块",
    # ★ 只有 3.10 有这一册（3.11 起上游并进 installing 并删掉了目录）。
    #   2026-11-03 实测：3.10 的验收报告「封面标题已中文化 26/27」，缺的就是它
    #   —— 不在这张表里就只能保留上游的英文 "Distributing Python Modules"。
    "distributing": "分发 Python 模块",
    "faq": "Python 常见问题",
    "builtins": "Python 内置参考手册",
    "howto-perf_profiling": "Python 对 Linux perf 性能分析器的支持",
    # ★ 2026-10-17 新增：3.15 的新 howto，上游 zh-CN **还没译**（reST 标题仍是
    #   "Migrating to Stable ABI for free threading (abi3t)"），于是封面是英文、
    #   而文件名与书签已经是中文 —— 两套不一致。标题取自本程序 name_map 的
    #   HOWTO 表（唯一真源），保证「封面 == 文件名 == 书签」。
    "howto-abi3t-migration": "迁移到自由线程的稳定 ABI（abi3t）",
}

TITLE_RE = re.compile(r"\\title\{", re.S)
RELEASE_RE = re.compile(r"\\release\{([^}]*)\}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def match_brace(text: str, start: int) -> int:
    """从 text[start] == '{' 开始，返回配对 '}' 的下标。"""
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c == "\\":          # 跳过被转义的下一个字符（\{ \} 等）
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("花括号不配对")


def current_title(text: str) -> str | None:
    m = TITLE_RE.search(text)
    if not m:
        return None
    open_at = m.end() - 1
    return text[open_at + 1 : match_brace(text, open_at)]


def target_title(tex_name: str, text: str) -> str | None:
    tpl = TITLES.get(tex_name)
    if tpl is None:
        return None
    if "{v}" in tpl:
        m = RELEASE_RE.search(text)
        if not m:
            return None
        ver = ".".join(m.group(1).split(".")[:2])   # 3.14.7 -> 3.14
        return tpl.format(v=ver)
    return tpl


def process(path: Path, dry_run: bool) -> str:
    """返回 'changed' | 'same' | 'skip'。"""
    tex_name = path.stem
    text = read(path)
    want = target_title(tex_name, text)
    if want is None:
        return "skip"
    have = current_title(text)
    if have is None:
        print(f"  [警告] {path.name} 里找不到 \\title{{...}}，跳过")
        return "skip"
    if have == want:
        return "same"
    print(f"  {path.name}\n      {have!r}\n   -> {want!r}")
    if dry_run:
        return "changed"
    m = TITLE_RE.search(text)
    open_at = m.end() - 1
    close_at = match_brace(text, open_at)
    new = text[: open_at + 1] + want + text[close_at:]
    path.write_text(new, encoding="utf-8")
    return "changed"


def loct_main() -> int:
    ap = argparse.ArgumentParser(description="把 Sphinx .tex 的封面标题换成中文")
    ap.add_argument("latex_dir", help="含 *.tex 的 latex 构建目录")
    ap.add_argument("--dry-run", action="store_true", help="只显示将要做的改动")
    ap.add_argument("--list", action="store_true",
                    help="只输出待改册子名（每行一个，供脚本消费）")
    args = ap.parse_args()

    d = Path(args.latex_dir)
    if not d.is_dir():
        print(f"目录不存在：{d}", file=sys.stderr)
        return 2

    todo: list[str] = []
    for tex_name in TITLES:
        p = d / f"{tex_name}.tex"
        if not p.is_file():
            continue
        if args.list:
            text = read(p)
            want = target_title(tex_name, text)
            if want is not None and current_title(text) != want:
                todo.append(tex_name)
            continue
        todo.append(tex_name)

    if args.list:
        for n in todo:
            print(n)
        return 0

    if not todo:
        print("没有任何 .tex 带英文封面标题")
        return 0

    if args.dry_run:
        print(f"── 预演（{d}）")
    else:
        print(f"── 改封面标题（{d}）")

    stats = {"changed": 0, "same": 0, "skip": 0}
    for tex_name in todo:
        stats[process(d / f"{tex_name}.tex", args.dry_run)] += 1

    print(f"待改 {len(todo)} 册 → 改动 {stats['changed']}，已是中文 {stats['same']}，"
          f"跳过 {stats['skip']}")
    if not args.dry_run and stats["changed"]:
        print("⚠️ 改完只能重跑 xelatex，不要重跑 makeindex/make，否则 .ind 里的索引又会坏")
    return 0


# ==== [TOOL-SRC:fix-index:BEGIN] ==============================================
# ↑ 机器标记：`_emit_makeindex_fix()` 靠它把下面这一整段原样切出来，
#   生成**自包含**的 makeindex-fix.py 给 latexmk 用（切片必须是合法的
#   独立脚本：只许用标准库 + 本段内定义的名字）。
# ---------------------------------------------------------------------------
# 内置工具：fix-index.py（原样内联，逻辑一行未改）
#   入口：fidx_main
# ---------------------------------------------------------------------------
# """修补 makeindex 生成的 .ind（中文索引分组标题 + 页码超链接 + 长条目断行）。
#
# makeindex 有四个问题，全都在 .ind 这一层能修掉：
#
# 1) 分组标题按「字节」截断
#    makeindex 遇到 UTF-8 多字节的中文条目，当分组标题时只写第一个字节：
#
#        \\bigletter \\xe7          <- 只写了「特」(E7 89 B9) 的首字节
#
#    这个孤立的 0xE7 不是合法 UTF-8，XeTeX 会报
#        Invalid UTF-8 byte or sequence ... replaced by U+FFFD
#    字体里没有 U+FFFD 字形 → 页面上显示 � 方框。
#    → 把这类「解不出 UTF-8」的分组标题连同它前面的 \\indexspace 一起删掉。
#
# 2) 「非字母」/「数字」两个分组标题是空的
#    Sphinx 的 python.ist 写的是
#
#        symhead_positive "{\\sphinxsymbolsname}"
#        numhead_positive "{\\sphinxnumbersname}"
#
#    而 sphinxlatexindbibtoc.sty 里这两个宏的初始值就是**空**（注释说 "redefined
#    in preamble"）。参考样张（官方中文 PDF）索引第一组就是加粗的「非字母」，
#    数字组是「数字」。→ 直接把这两个宏名替换成字面文字。
#
# 3) 索引页码点不动
#    hyperref 的 hyperindex=true 本来会自动把每个 \\indexentry 写成
#    `\\indexentry{条目|hyperpage}{页码}`，makeindex 收到 |hyperpage 后就会输出
#    `\\hyperpage{33}`，\\hyperpage 再把它变成指向该页的链接。
#    但 Sphinx 的 sphinxlatexindbibtoc.sty 里 `\\RequirePackage{makeidx}` 又把
#    \\@wrindex 覆盖成 makeidx 自己的版本（不带属性），于是 .ind 里的页码是纯文本：
#    参考样张每个索引页有 81~90 个 /Link 注解，我们只有 2~3 个。
#    → 给每条页码包一层 \\hyperpage{...}：
#         , 33            ->  , \\hyperpage{33}
#         , 33, 44        ->  , \\hyperpage{33}, \\hyperpage{44}
#         , 40--42        ->  , \\hyperpage{40--42}      （hyperref 自己会拆区间）
#         \\spxpagem{135}  ->  \\spxpagem{\\hyperpage{135}}
#
#    只处理每行**行尾的页码段**：\\item/\\subitem/\\subsubitem 之后、以「, 数字」或
#    「, 数字--数字」或「\\spxpagem{数字}」构成的那一串；条目正文里的数字（比如
#    「Python 3.14」「base64」）绝不碰。
#
# 4) 长条目压过界，压到隔壁栏（叠字）
#    索引是双栏排的（makeidx 的 \\printindex 走 \\twocolumn）。双栏模式下**溢出的行
#    没有页边距可去，直接压到右栏文字上**，于是出现「address_string() （http.server.
#    BaseHTTPRequestHandler」和右栏「AF_QIPCRTR()」叠在一起的花屏。
#
#    溢出的是条目里的**等宽模块路径**：
#
#        \\spxentry{open\\_resource() （importlib.resources.abc.ResourceReader 方法）}
#
#    \\spxentry 就是 \\sphinxstyleindexentry = \\texttt{#1}（sphinxlatexstyletext.sty），
#    而 LaTeX 的 \\ttfamily 关掉了连字符断词（hyphenchar=-1），于是
#    importlib.resources.abc.ResourceReader 这 35 个字符是一个**不可断的词**：
#    10pt FreeMono 每字符 6pt → 210pt，而索引栏宽只有约 250pt，前面还有
#    「open_resource() （」→ 必然 Overfull（实测 75pt 太宽）。
#
#    → 在条目正文里给 `.` `_` `/` `-` 后面补一个 \\allowbreak{{}}（=\\penalty\\z@，合法断行点，
#      不加连字符）。断在点上正是 Python 文档的惯例：
#        importlib.resources.abc. / ResourceReader
#    ⚠️ 写的是 `\\allowbreak{{}}` 而**不是** `\\allowbreak`：后者是控制词，TeX 会把紧跟的
#       字母并进名字（`Absolute\\allowbreakLink` → 未定义的 `\\allowbreakLink`），
#       索引条目整条丢字且**不报错中断**——PDF 照样生成，只有翻日志才发现。
#    注意 .ind 里的下划线是转义的 `\\_`，要在**整个控制序列之后**补断点；
#    `\\_\\_foo\\_\\_` 这种连续下划线只在最后一串后面补，免得断成 `_` / `_foo`。
#
#    只处理条目正文（\\item/\\subitem/\\subsubitem 之后、行尾页码段之前），
#    页码段一律不碰。同一行正文里的 `.`（比如「Python 3.14」「base64」）补了也无害：
#    \\allowbreak 只是「允许」断行，不强制。
#
# 用法
# ----
# A. 就地修一个目录／文件（事后补救、验收用）：
#
#        python fix-index.py <目录或 .ind> [--dry-run] [--list]
#
# B. 给 latexmk 当 $makeindex 用（推荐：一次编译就修好，不用事后重排）：
#
#        python fix-index.py -s python.ist -o foo.ind foo.idx     # 参数同 makeindex
#
#    接进 latexmk 的做法：把本脚本**拷到 latex 目录、改名 ASCII 的
#    `makeindex-fix.py`**（`-e` 的字符串按 UTF-8 解析，路径带中文会炸），再
#
#        latexmk -pdf -r latexmkrc \
#          -e '$makeindex = q{python makeindex-fix.py %O -s python.ist -o %D %S};' foo.tex
#
# 排查开关： --no-hyperpage（不包页码链接）、--no-break（不补断点）。
# """

import argparse
import re
import sys
from pathlib import Path

# 分组标题：python.ist 里 heading_prefix 是 "  \bigletter "
HEAD_RE = re.compile(r'^  \\bigletter (.*)$')

# item / subitem / subsubitem 行
ITEM_RE = re.compile(r'^(\s*\\(?:subsubitem|subitem|item)\s)(.*)$')

# 页码段里合法的「一段」
#   ⚠️ 必须同时认「已包过 \hyperpage 的形态」：fix_text 每行先包链接、再补断点，
#      但工具也支持反复就地跑，第二次进来页码已经是 \hyperpage{33} 了。
_NUM_RANGE = r'\d+(?:\s*--\s*\d+)?'
PLAIN_PAGE_RE = re.compile('^' + _NUM_RANGE + '$')

#: 「一段页码」的合法形态（单独定义是为了让「整行都是页码」能复用同一套判据）
#:   ⚠️ 必须同时认「已包过 \hyperpage 的形态」：fix_text 每行先包链接、再补断点，
#:      但工具也支持反复就地跑，第二次进来页码已经是 \hyperpage{33} 了。
_PAGE_ITEM = (r'(?:' + _NUM_RANGE +                     # 33 / 40--42
              r'|\\hyperpage\{' + _NUM_RANGE + r'\}' +  # \hyperpage{33}
              r'|\\spxpagem\{\d+\}' +                   # \spxpagem{135}
              r'|\\spxpagem\{\\hyperpage\{\d+\}\})')    # \spxpagem{\hyperpage{135}}
PAGE_TOKEN_RE = re.compile('^' + _PAGE_ITEM + '$')

#: 「整行都是页码段」的行 —— makeindex 折出来的续行就长这样。
#:      \t\t\spxpagem{2210}
#:      \t\t1291
#:      \t\t\spxpagem{2210}, \spxpagem{2211}
PAGE_ONLY_LINE_RE = re.compile(
    '^' + _PAGE_ITEM + r'(?:\s*,\s*' + _PAGE_ITEM + r')*$')

SPX_PAGEM_RE = re.compile(r'^\\spxpagem\{(\d+)\}$')

HYPERPAGE_RE = re.compile(r'\\hyperpage\{')

DEFAULT_SYMBOLS_NAME = '非字母'
DEFAULT_NUMBERS_NAME = '数字'

# 断行点：\allowbreak 就是 \penalty\z@（latex.ltx），合法且不插入连字符。
#   ⚠️ 末尾的 {} **不能省**！\allowbreak 是「控制词」，TeX 会贪婪地把后面的字母
#      并进名字：`Absolute\allowbreakLink\allowbreakError` 会被读成
#      两条**未定义**的控制序列 `\allowbreakLink` / `\allowbreakError`，
#      整册索引条目直接丢失（日志满屏 `Undefined control sequence`，PDF 照样生成，
#      极其隐蔽）。{} 作为空组既终止控制词，又不产生任何水平盒子/间距。
BREAK_MARK = '\\allowbreak{}'

# 兜底自检：绝不允许出现「\allowbreak + 字母」这种被吞掉的写法
BREAK_ABSORBED_RE = re.compile(r'\\allowbreak[A-Za-z]')

# 控制序列：\foo 或 \x（\x 形式有 \_ \{ \} \| 等）
CS_RE = re.compile(r'\\[A-Za-z]+|\\[^A-Za-z]')

# 哪些字符后面值得给一个断点
BREAK_AFTER = '._/-'


def is_utf8(b: bytes) -> bool:
    try:
        b.decode('utf-8')
        return True
    except UnicodeDecodeError:
        return False


def _is_continuation(ln: str) -> bool:
    """makeindex 因 line_max=100 把长条目折行后的「续行」。

    形如（续行以两个制表符缩进）：

        \\item \\spxentry{SetAllocTrackerMaximumAmplification() （... 方法）},
        \\t\\t1291
        \\t\\t\\spxpagem{2210}                      ← python.ist 把页码包成 \\spxpagem

    续行必须并回上一行：否则页码段落在续行上，split_pages() 认不出来，
    长条目的断点也就补不上（页面上继续压栏）。

    ★★ 2026-10-06 修的坑：老判据写的是「不以反斜杠开头才算续行」，
       目的是排除 `\\item` / `\\bigletter` 这些块级命令 —— 但它把
       `\\t\\t\\spxpagem{2210}` 也一起排除了（它确实以反斜杠开头）。
       后果：**478 个页码留在续行上，永远包不上 \\hyperpage**，
       页面上就是一片点不动的黑色页码（实测 3.15 全 39 册恰好 478 条）。
       现在改成按「**整行是不是纯页码**」再认一次 —— 块级命令永远不可能是纯页码。
    """
    if not ln[:1].isspace():
        return False
    body = ln.strip()
    if not body:
        return False
    if body.startswith('\\'):
        return bool(PAGE_ONLY_LINE_RE.match(body))
    return True


def merge_continuations(lines: list[str]) -> list[str]:
    """把 makeindex 折出来的续行并回上一条逻辑行。"""
    out: list[str] = []
    for ln in lines:
        if out and _is_continuation(ln):
            out[-1] = out[-1].rstrip() + ' ' + ln.strip()
        else:
            out.append(ln)
    return out


# ---------------------------------------------------------------------------
# 页码段：切开「条目」与「行尾页码」
# ---------------------------------------------------------------------------
def _top_level_commas(s: str) -> list[int]:
    """返回所有「花括号深度为 0」的逗号位置。

    反斜杠转义的字符（\\{ \\} 等）不算括号，否则条目名里的字面花括号会数错深度。
    """
    pos: list[int] = []
    depth = 0
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == '\\':
            i += 2                      # 连同被转义的字符一起跳过
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
        elif ch == ',' and depth == 0:
            pos.append(i)
        i += 1
    return pos


def split_pages(line: str) -> tuple[str, list[str]] | None:
    """把 item 行切成 (条目部分, 页码段列表)。

    没有页码段（例如只有 \\item \\spxentry{foo} 的行）→ 返回 None。
    """
    m = ITEM_RE.match(line)
    if not m:
        return None
    commas = _top_level_commas(line)
    if not commas:
        return None
    # 从最后一个逗号往前找，连续满足「页码」形态的那几段
    segs: list[str] = []
    start: int | None = None
    prev = len(line)
    for c in reversed(commas):
        seg = line[c + 1:prev].strip()
        if not PAGE_TOKEN_RE.match(seg):
            break
        segs.append(seg)
        start = c
        prev = c
    if start is None:
        return None
    segs.reverse()
    return line[:start], segs


def wrap_one(token: str) -> str:
    """给单段页码加 \\hyperpage（已经包过的原样返回）。"""
    if HYPERPAGE_RE.search(token):
        return token
    m = SPX_PAGEM_RE.match(token)
    if m:
        return f'\\spxpagem{{\\hyperpage{{{m.group(1)}}}}}'
    if PLAIN_PAGE_RE.match(token):
        return f'\\hyperpage{{{token.replace(" ", "")}}}'
    return token


def wrap_pages(line: str) -> tuple[str, int]:
    """给一行里的行尾页码全部包上 \\hyperpage。返回 (新行, 实际包装个数)。

    幂等：已经包过的页码段原样保留，也不计入个数（否则 --check 永远判「没修好」）。
    """
    got = split_pages(line)
    if got is None:
        return line, 0
    head, segs = got
    new_segs: list[str] = []
    n = 0
    for s in segs:
        w = wrap_one(s)
        if w != s:
            n += 1
        new_segs.append(w)
    if n == 0:
        return line, 0
    return head + ', ' + ', '.join(new_segs), n


# ---------------------------------------------------------------------------
# 断行点：让长模块路径能在 . _ / - 处换行，避免溢出压到隔壁栏
# ---------------------------------------------------------------------------
def add_breakpoints(head: str) -> tuple[str, int]:
    """   在条目正文里 . _ / - 之后（以及驼峰词内部）插入 \\allowbreak{{}}。

    返回 (新文本, 插入个数)。幂等：先把上次插的记号去掉再重插。

    为什么还要断驼峰：栏宽约 255pt，10pt FreeMono 每字符 6pt ⇒ 最多 42 字符。
    xml.parsers.expat.xmlparser 后面挂着
        SetBillionLaughsAttackProtectionMaximumAmplification()   ← 52 字符 = 312pt
    光在点号处断行仍然溢出，所以再按驼峰边界（fooBar / HTTPPassword）给断点。
    """
    s = re.sub(r'\\allowbreak(\{\})?', '', head)   # 归一化（顺带修掉旧版的 `\allowbreak词` 残骸）
    out: list[str] = []
    added = 0
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == '\\':                      # 控制序列：整段搬走，别在名字里插东西
            m = CS_RE.match(s, i)
            assert m is not None
            cs = m.group(0)
            out.append(cs)
            i = m.end()
            if cs == '\\_':
                # 连续的 \_ 只在一串末尾给断点：\_\_foo 不该断成 _ / _foo
                if not s.startswith('\\_', i) and _worth_break(s, i):
                    out.append(BREAK_MARK)
                    added += 1
            elif cs == '\\sphinxhyphen' and s.startswith('{}', i):
                # \sphinxhyphen{} 展开是 `-\kern\z@`。**这个零 kern 不给断点** ——
                # 最小文档实测：`python--m-sqlite3-[-h]-[-v]-[filename]-[sql]`
                # 整串 45 字符仍然 Overfull 35.6pt（见 .chk/brk）。
                # 于是 `\sphinxhyphen{}` 串起来的长串（命令行选项、PEP 标题）
                # 一个断点都没有 → 自己补上。
                out.append('{}')
                i += 2
                out.append(BREAK_MARK)
                added += 1
            continue
        # 驼峰边界：前一个字符是字母/数字，本身是大写字母时，可以在它前面断
        if _camel_boundary(s, i):
            out.append(BREAK_MARK)
            added += 1
        out.append(ch)
        i += 1
        if ch in BREAK_AFTER and i < n and s[i] not in ' \t,':
            out.append(BREAK_MARK)
            added += 1
    return ''.join(out), added


def _camel_boundary(s: str, i: int) -> bool:
    """s[i] 处是不是驼峰词边界（可以在它**前面**断行）。

    只认两种写法，别把缩写拆坏：
        fooBar        → foo|Bar      （大写字母、左邻为小写）
        HTTPPassword  → HTTP|Password（处于大写串末尾、右邻为小写）
    反例：IMAP4 的 P（左邻大写、右邻是数字）——不是边界，别断成 IMA|P4。
    """
    if i <= 0 or not s[i].isupper():
        return False
    prev = s[i - 1]
    nxt = s[i + 1] if i + 1 < len(s) else ''
    if prev.islower():
        return True
    if prev.isupper() or prev.isdigit():
        return nxt.islower()
    return False


def _worth_break(s: str, i: int) -> bool:
    """断点后面的下一个字符是空白/逗号/结束就没有必要再插。"""
    return i < len(s) and s[i] not in ' \t,'


def break_row(line: str) -> tuple[str, int]:
    """给一条 item 行的「条目正文」补断点（页码段不动）。"""
    got = split_pages(line)
    if got is None:
        return line, 0
    head, segs = got
    new_head, n = add_breakpoints(head)
    new_line = new_head + ', ' + ', '.join(segs)
    if new_line == line:
        return line, 0          # 已经修过：原样返回，也不计数
    return new_line, n


# ---------------------------------------------------------------------------
# 主修补
# ---------------------------------------------------------------------------
class Stats:
    def __init__(self) -> None:
        self.dropped = 0          # 删掉的坏分组标题
        self.symbols = 0          # 换掉 {\sphinxsymbolsname} 的个数
        self.numbers = 0          # 换掉 {\sphinxnumbersname} 的个数
        self.refs = 0             # 包上 \hyperpage 的页码段个数
        self.breaks = 0           # 插入的 \allowbreak 断点个数
        self.invalid_after = 0    # 修完还剩的非法行
        self.modified = False     # 有没有真的改动文本（--check 的判据）

    @property
    def changed(self) -> bool:
        return self.modified

    def __str__(self) -> str:
        return (f'删坏标题 {self.dropped}  非字母标题 {self.symbols}  '
                f'数字标题 {self.numbers}  页码链接 {self.refs}  '
                f'断点 {self.breaks}')


def fidx_fix_text(text: str, *, symbols: str = DEFAULT_SYMBOLS_NAME,
             numbers: str = DEFAULT_NUMBERS_NAME,
             hyperpage: bool = True,
             breakpoints: bool = True) -> tuple[str, Stats]:
    """修补 .ind 文本（已解码为 str）。"""
    st = Stats()
    out: list[str] = []
    raw_lines = text.split('\n')
    src = merge_continuations(raw_lines)
    st.modified = len(src) != len(raw_lines)      # 合并过续行 → 文件就变了
    for line in src:
        raw = line.encode('utf-8', 'surrogateescape')

        m = HEAD_RE.match(line)
        if m:
            arg = m.group(1)
            raw_arg = arg.encode('utf-8', 'surrogateescape')
            if not is_utf8(raw_arg):
                st.dropped += 1
                st.modified = True
                # 连前面的空行 + \indexspace 一起回溯删掉，别留空洞
                while out and out[-1].strip() == '':
                    out.pop()
                if out and out[-1].strip() == '\\indexspace':
                    out.pop()
                while out and out[-1].strip() == '':
                    out.pop()
                continue
            if arg == '{\\sphinxsymbolsname}':
                line = f'  \\bigletter {{{symbols}}}'
                st.symbols += 1
                st.modified = True
            elif arg == '{\\sphinxnumbersname}':
                line = f'  \\bigletter {{{numbers}}}'
                st.numbers += 1
                st.modified = True
            out.append(line)
            continue

        if ITEM_RE.match(line):
            orig = line
            if hyperpage:
                line, n = wrap_pages(line)
                st.refs += n
            if breakpoints:
                line, nb = break_row(line)
                st.breaks += nb
            if line != orig:
                st.modified = True
        out.append(line)

    # 不该残留非法字节（坏标题都删了）
    st.invalid_after = sum(1 for ln in out if not is_utf8(ln.encode('utf-8', 'surrogateescape')))
    new = '\n'.join(out)
    # 兜底：断点必须是 `\allowbreak{}`。少了 {} 就会变 `\allowbreakError`，
    # TeX 报未定义控制序列、索引条目整条丢字 —— 宁可在这里直接失败。
    m = BREAK_ABSORBED_RE.search(new)
    if m:
        raise RuntimeError(
            f'断点写法被 TeX 吞掉：{new[max(0, m.start() - 40):m.end() + 40]!r} '
            f'—— \\allowbreak 后面必须紧跟 {{}}（见 BREAK_MARK 的注释）')
    return new, st


def fix_file(path: Path, *, dry_run: bool = False, **kw) -> Stats:
    raw = path.read_bytes()
    text = raw.decode('utf-8', 'surrogateescape')
    new, st = fidx_fix_text(text, **kw)
    if not dry_run and new != text:
        path.write_bytes(new.encode('utf-8', 'surrogateescape'))
    return st


def count_invalid(path: Path) -> int:
    return sum(1 for ln in path.read_bytes().split(b'\n') if not is_utf8(ln))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _collect_inds(paths: list[str]) -> list[Path]:
    inds: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            inds.extend(sorted(p.glob('*.ind')))
        elif p.suffix == '.ind':
            inds.append(p)
    return inds


def fidx_main() -> int:
    ap = argparse.ArgumentParser(
        description='修 .ind：坏分组标题 / 非字母·数字标题 / 页码超链接 / 长条目断行点')
    # 兼容 makeindex 的参数（给 latexmk 当 $makeindex 用）
    ap.add_argument('-s', '--style', default=None,
                    help='makeindex 样式文件（给了就顺手当 makeindex 跑一遍 .idx）')
    ap.add_argument('-o', '--out', default=None,
                    help='makeindex 的输出 .ind（配合 -s 使用）')
    ap.add_argument('-t', '--transcript', default=None, help='makeindex 转录文件（忽略）')
    ap.add_argument('paths', nargs='+', help='目录（处理其中全部 *.ind）或单个 .ind 文件')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--check', action='store_true',
                    help='只检查：需要修补的 .ind 会列出来，退出码 1（不写盘）')
    ap.add_argument('--list', action='store_true',
                    help='只打印「被改动的 .ind 文件名」，每行一个')
    ap.add_argument('--no-hyperpage', action='store_true',
                    help='不包 \\hyperpage（只修标题，用于排查）')
    ap.add_argument('--no-break', action='store_true',
                    help='不给长条目补 \\allowbreak 断点（用于排查叠字）')
    ap.add_argument('--symbols-name', default=DEFAULT_SYMBOLS_NAME)
    ap.add_argument('--numbers-name', default=DEFAULT_NUMBERS_NAME)
    ap.add_argument('--quiet', action='store_true')
    # latexmk 会在 $makeindex 里塞 %O，可能有我们不认识的选项 —— 忽略即可
    args, unknown = ap.parse_known_args()
    if unknown and not args.quiet:
        print(f'（忽略未知参数：{" ".join(unknown)}）', file=sys.stderr)

    kw = dict(symbols=args.symbols_name, numbers=args.numbers_name,
              hyperpage=not args.no_hyperpage,
              breakpoints=not args.no_break)

    # --- 模式 B：先替 makeindex 跑一遍 -------------------------------------
    if args.style and args.out:
        import shutil
        import subprocess

        mi = shutil.which('makeindex')
        if not mi:
            print('!! PATH 里找不到 makeindex', file=sys.stderr)
            return 1
        idx = Path(args.paths[0])
        cmd = [mi, '-s', args.style, '-o', args.out]
        if args.transcript:
            cmd += ['-t', args.transcript]
        cmd.append(str(idx))
        # ★ 这一步由 latexmk 的 $makeindex 调用，**每册都会跑**；漏掉
        #   CREATE_NO_WINDOW 就成了「构建过程中黑框乱闪」（实测踩过）。
        rc = subprocess.run(cmd, creationflags=CREATE_NO_WINDOW).returncode
        if rc != 0:
            print(f'!! makeindex 失败，退出码 {rc}', file=sys.stderr)
            return rc
        out = Path(args.out)
        # .idx 是空的（有些 howto 册子没有索引项）时 makeindex 不写文件，
        # latexmk 那边会自己造一个空 .ind —— 这里不能当成错误。
        if not out.is_file() or out.stat().st_size == 0:
            if not args.quiet:
                print(f'  {out.name}: （无索引项，跳过修补）')
            return 0
        st = fix_file(out, dry_run=args.dry_run, **kw)
        if not args.quiet:
            print(f'  {out.name}: {st}')
        return 0

    # --- 模式 A：就地修目录／文件 -----------------------------------------
    inds = _collect_inds(args.paths)
    if not inds:
        print('!! 没有找到 .ind 文件', file=sys.stderr)
        return 1

    # --list 的语义是「只打印会被改动的文件名」，绝不能真写盘：
    #   否则一次 --list 就把 .ind 就地改了，调用方随后再跑一次「真修」成了空操作，
    #   而且和 --dry-run 的语义冲突。
    dry = args.dry_run or args.check or args.list
    rows = []
    affected: list[str] = []
    for p in inds:
        st = fix_file(p, dry_run=dry, **kw)
        if st.changed:
            affected.append(p.name)
        rows.append((p.name, st, count_invalid(p)))

    if args.list:
        for name in affected:
            print(name)
        return 0

    if args.check:
        if affected:
            print(f'!! 有 {len(affected)} 个 .ind 还没修好：{" ".join(affected)}',
                  file=sys.stderr)
            return 1
        print(f'OK：{len(inds)} 个 .ind 都齐了（分组标题 + 页码超链接）')
        return 0

    width = max((len(r[0]) for r in rows), default=10) + 2
    print(f'{"文件":<{width}}{"删坏标题":>8}{"非字母":>7}{"数字":>6}'
          f'{"页码链接":>9}{"断点":>8}{"残留非法":>9}')
    print('-' * (width + 47))
    for name, st, bad in rows:
        flag = '' if bad == 0 else '  << 仍有非法字节!'
        print(f'{name:<{width}}{st.dropped:>8}{st.symbols:>7}{st.numbers:>6}'
              f'{st.refs:>9}{st.breaks:>8}{bad:>9}{flag}')
    tot = Stats()
    for _n, st, _b in rows:
        tot.dropped += st.dropped
        tot.symbols += st.symbols
        tot.numbers += st.numbers
        tot.refs += st.refs
        tot.breaks += st.breaks
        tot.modified = tot.modified or st.modified
    print('-' * (width + 47))
    print(f'共 {len(inds)} 个 .ind，{len(affected)} 个被改动：{tot}')
    if args.dry_run:
        print('（dry-run，未写盘）')
    return 0
# ==== [TOOL-SRC:fix-index:END] ================================================

# ---------------------------------------------------------------------------
# 内置工具：rename-pdf.py（原样内联，逻辑一行未改）
#   入口：rnpdf_main
# ---------------------------------------------------------------------------
# """按 `name_map.py` 把 Sphinx 产出的英文 PDF 名改成中文名（步骤 8 的后半）。
#
# 为什么要重写（原来是 `rename-pdf.sh`）
#     shell 版有三个**静默**毛病，换版本时才暴露：
#       1. `[ -f "$1.pdf" ] || return 0` —— 源文件不在就默默跳过。低版本本来就没有的册子
#          跳过是对的，但**上游新增 howto 时也默默跳过**，于是目录里会留下
#          `howto-xxx.pdf` 这种英文名文件，没人知道。
#       2. 映射表硬写「09Python 指南NN」长名，与本项目其余 27 篇的「09NN」简写不一致。
#       3. 映射表和 `merge-pdf.py`、GUI 各一份，必须手工同步（已实测漏同步两次）。
#     现在三个毛病都堵住：映射只在 `name_map.py`，改完名会**逐项核对**并把
#     缺册 / 未收录 / 本版本无此册全部分类报出来。
#
# 输出（★ ASCII 标记，供 GUI / bash 判定；中文行只给人看）
#     RENAMED <n>      本次改名成功
#     KEPT <n>         已经是目标名（幂等重跑，不算问题）
#     MISSING <n>      本版本**应当有却缺** → 只数这个才是真缺册
#     UNPRODUCED <n>   本版本**本就没有**（版本门控），不是问题
#     UNKNOWN <n>      未收录产物：`howto-*.pdf` 里 `name_map.py` 没登记的那些
#     EXTRA <n>        目录里其它 PDF（合并册、用户自己放的文件），只提示
#     FAILED <n>       改名时报 OSError 的个数
#
# 退出码
#     0 = 全好；1 = 有 MISSING / UNKNOWN / FAILED（可继续，但要处理）；2 = 参数或环境错误。
#
# ★ 幂等与「不误删」
#     重复跑一遍是安全的：
#       * 源文件不在、目标名已在 → 记为 KEPT；
#       * 源文件在、目标名也已在，且两者**逐字节相同**（sha256）→ 删掉那个重复副本；
#       * 源文件在、目标名已在但**内容不同** → 旧件改名成 `*.pdf.old` 留着，绝不直接删。
#
# ★ 会主动发现的错
#     1. `--version` 传错：目录里若已有 `01Python X.Y 有什么新变化.pdf`，用它反查版本，
#        与 `--version` 不一致就报警（否则满屏假「缺册」）。
#     2. 上游新增 howto 而我们没登记 → `UNKNOWN`，并提示本版本可用的**空号**。
#     3. `MIN_VERSION` 登记错（低版本里居然有该册）→ 该文件会正常改名，不报错。
#
# 用法::
#
#     python tools/rename-pdf.py "<PDF 目录>" --version 3.15
#     python tools/rename-pdf.py "<PDF 目录>" --version 3.15 --check   # 只看不动
#     python tools/rename-pdf.py "<PDF 目录>" --version 3.15 --list    # 只列不改
# """


import argparse
import hashlib
import sys
from pathlib import Path



def _same(a: Path, b: Path) -> bool:
    """两个文件是否**逐字节相同**（分块 sha256）。

    ★ 不能只比大小：同名旧件恰好大小相同却内容不同的概率虽低，但一旦发生就是
      「默默删掉刚编出来的新册子」，代价极大。这里宁可多花一次 IO。
    """
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        h1, h2 = hashlib.sha256(), hashlib.sha256()
        for p, h in ((a, h1), (b, h2)):
            with p.open('rb') as f:
                for chunk in iter(lambda: f.read(1 << 20), b''):
                    h.update(chunk)
        return h1.digest() == h2.digest()
    except OSError:
        return False


#: 从目录里的册子反查真实版本号（实现在 name_map 里，与合并工具共用一份）


def _brief(names: list[str], limit: int = 8) -> str:
    """长清单只显示前几个 —— 37 个名字铺一屏会把真正的结论埋掉。"""
    return brief(names, limit)


def _classify(pdf_dir: Path, version: str) -> dict[str, list]:
    """把目录里的 PDF 分成：待改名 / 已是目标名 / 缺 / 本版本无 / 未收录 / 其它。

    ★ 判定顺序很重要 —— **先看目标名在不在，再看源名**。
      只按源名判断的话，第二次跑（文件早已是中文名）会把 39 册全报成「缺」，
      因为 `whatsnew.pdf` 这类英文名文件本来就不该再存在了。
    """
    plan = rename_plan(version)                    # {slug: 目标名}（全集）
    targets = set(plan.values())
    res: dict[str, list] = {
        'todo': [], 'kept': [], 'missing': [], 'unproduced': [],
        'unknown': [], 'other': [],
    }
    for slug, target in plan.items():
        src = pdf_dir / f'{slug}.pdf'
        tgt = pdf_dir / f'{target}.pdf'
        if tgt.is_file():
            # 目标名已在：若源名也在，就是重复副本，交给改名循环去比对/清理
            (res['todo'] if src.is_file() else res['kept']).append((slug, target))
        elif src.is_file():
            res['todo'].append((slug, target))
        elif has_in_version(slug, version):
            res['missing'].append((slug, target))
        else:
            res['unproduced'].append((slug, target))

    known = set(plan) | targets
    prefixed = tuple(s for s in plan if not s.startswith('howto-')) + ('howto-',)
    for pdf in sorted(pdf_dir.glob('*.pdf')):
        if pdf.stem in known:
            continue
        if pdf.stem.startswith(prefixed):
            res['unknown'].append(pdf.name)
        else:
            res['other'].append(pdf.name)
    return res


def rnpdf_main() -> int:
    ap = argparse.ArgumentParser(
        description='按 name_map.py 把分册 PDF 改成中文名（步骤 8 后半）')
    ap.add_argument('pdf_dir', help='分册 PDF 所在目录')
    ap.add_argument('version_pos', nargs='?', default=None,
                    help='（兼容老 shell 写法的第二个位置参数）版本号，如 3.15')
    ap.add_argument('--version', '-v', default=None,
                    help='Python 版本，决定文件名里的版本片段与版本门控，如 3.13/3.14/3.15')
    ap.add_argument('--check', '--dry-run', '-n', dest='check', action='store_true',
                    help='只检查、不改名')
    ap.add_argument('--list', dest='list_only', action='store_true',
                    help='只列出分类结果与版本相关信息，不做任何检查判定')
    args = ap.parse_args()

    ver = (args.version or args.version_pos or '3.14').strip()
    pdf_dir = Path(args.pdf_dir).expanduser().resolve()
    if not pdf_dir.is_dir():
        print(f'!! 目录不存在：{pdf_dir}', file=sys.stderr)
        return 2

    res = _classify(pdf_dir, ver)
    renamed = deduped = replaced = failed = 0

    if not args.check and not args.list_only:
        for slug, target in res['todo']:
            src = pdf_dir / f'{slug}.pdf'
            tgt = pdf_dir / f'{target}.pdf'
            try:
                if tgt.exists():
                    if _same(src, tgt):
                        # 幂等重跑：上次已改好，这个只是重复副本 → 删副本
                        src.unlink()
                        deduped += 1
                        continue
                    # 同名但内容不同（上一轮遗留的旧版）→ 移开再放新的，不直接删
                    tgt.replace(tgt.with_suffix('.pdf.old'))
                    replaced += 1
                src.rename(tgt)
                renamed += 1
            except OSError as e:
                failed += 1
                print(f'[错误] 改名失败 {src.name} → {tgt.name}：{e}')
        # 改完重算：残留的 `howto-*.pdf` 才是真问题
        res = _classify(pdf_dir, ver)

    # ── 人看的部分 ────────────────────────────────────────────────────────
    print(f'重命名（{pdf_dir}，版本 {ver}）')
    found = guess_version(pdf_dir)
    if found and ver_tuple(found) != ver_tuple(ver):
        print(f'  [警告] 目录里的册子看起来是 **{found}** 的'
              f'（`01Python {found} 有什么新变化.pdf`），但这次按 **{ver}** 处理。'
              f'若 `--version` 传错，下面的「缺册」全是假警报。')
    if renamed or deduped or replaced:
        print(f'  已改名 {renamed} 册'
              + (f'；清掉 {deduped} 个逐字节相同的重复副本' if deduped else '')
              + (f'；{replaced} 个同名旧件移到 *.pdf.old' if replaced else ''))
    if res['kept']:
        print(f'  已是目标名 {len(res["kept"])} 册（幂等，无需处理）')
    if res['unproduced']:
        names = '、'.join(f for _s, f in res['unproduced'])
        print(f'  本版本本就没有 {len(res["unproduced"])} 册（版本门控，正常）：{names}')
        for slug, _f in res['unproduced']:
            print(f'      · {slug} —— 上游 {ver} 分支没有这篇（最低版本 '
                  f'{".".join(map(str, min_version_of(slug)))}+）')
    if res['missing']:
        names = [f for _s, f in res['missing']]
        print(f'  [警告] 本版本应当有、但没编出来 {len(names)} 册：{_brief(names)}')
        print('         多为该册在步骤 7 编译失败 —— 去 latex-build.log 搜它的名字。')
    if res['unknown']:
        print(f'  [警告] 未收录产物 {len(res["unknown"])} 个（`name_map.py` 里没登记，'
              f'所以保持英文名、也进不了合并册）：')
        for n in res['unknown'][:8]:
            print(f'      · {n}')
        if len(res['unknown']) > 8:
            print(f'      …（共 {len(res["unknown"])} 个）')
        spare = spare_numbers(ver)
        print(f'        处理：在 tools/name_map.py 的 HOWTO 表里补一行，'
              f'格式 (\'<slug>\', \'09NN中文名\', \'书签标题\', \'分组\')；'
              f'本版本空号：{" ".join(spare) if spare else "（无，需往后取 0930+）"}')
    if res['other']:
        print(f'  目录里另有 {len(res["other"])} 个非分册 PDF（合并册等，不管）：'
              + '、'.join(res['other'][:4])
              + ('…' if len(res['other']) > 4 else ''))
    if not (pdf_dir / '09Python 指南.pdf').exists():
        print(f'  提示：`09Python 指南.pdf` 这类总册在 {ver} 分支编不出来 —— '
              'conf.py 只逐个收 howto-*.rst，没有 howto/index 总册条目。')

    # ── 给程序看的 ASCII 标记 ─────────────────────────────────────────────
    print(f'RENAMED {renamed}')
    print(f'KEPT {len(res["kept"])}')
    print(f'MISSING {len(res["missing"])}')
    print(f'UNPRODUCED {len(res["unproduced"])}')
    print(f'UNKNOWN {len(res["unknown"])}')
    print(f'EXTRA {len(res["other"])}')
    print(f'FAILED {failed}')

    bad = len(res['missing']) + len(res['unknown']) + failed
    return 1 if bad else 0

# ---------------------------------------------------------------------------
# 内置工具：merge-pdf.py（原样内联，逻辑一行未改）
#   入口：mgpdf_main
# ---------------------------------------------------------------------------
# """把分册 PDF 合并成一本带完整书签的总册（3.13→37 册 / 3.14→38 册 / 3.15→39 册）。
#
# ★ 册名 / 编号 / 分组 / 版本门控的**唯一真源是 `name_map.py`** —— 本文件不再自带
#   任何表（2026-09-26 之前自带一份，与 `rename-pdf.sh`、GUI 的 `RENAME_MAP` 三份并存，
#   靠手工同步，实测漏同步过两次）。改分册名只改 `name_map.py`。
#
# 书签结构（★ 一级书签照用户给的参考图，即 EPUB 目录的一级）::
#
#     Python的新变化                 ← 01 whatsnew  （该册自己的书签原样挂在下面）
#     Python 教程                   ← 02 tutorial
#     Python安装和使用               ← 03 using
#     Python 语言参考手册             ← 04 reference
#     Python 标准库                  ← 05 library
#     扩展和嵌入 Python 解释器          ← 06 extending
#     Python/C API 参考手册          ← 07 c-api
#     安装 Python 模块               ← 08 installing
#     Python 指南                    ← howto 的分组节点（自己没有页）
#         通用                                  ← 官网 howto 索引页第 1 组（13 册）
#             asyncio 的概念概述                  ← 该册标题，它自己的书签挂在下面
#             ...
#         高级开发                               ← 第 2 组（0929 是 3.15 才有的）
#         调试和性能分析                          ← 第 3 组（0925 是 3.14 才有的）
#         将 optparse 代码迁移至 argparse          ← 官网索引页没列的 3 册，直接挂在指南下
#         Argument Clinic 的用法
#         如何将 Python 2 代码移植到 Python 3
#     Python 常见问题                 ← 10 faq
#     Python 内置参考手册              ← 11 builtins（按用户要求放最后）
#
# 要点：
# * **每一册自己的书签原样保留、整棵嵌进去**（页码按合并后的偏移量重算），
#   点开任意一册就是它原来那棵完整的树，层次不变。
# * 分组节点（Python 指南 / 通用 / 高级开发 / 调试和性能分析）自己没有页，
#   统一指向它第一个有页的后代 —— 点它也能跳过去，不会点不动。
# * 少数册子（如 0926将 optparse 代码迁移至 argparse）本身一个书签都没有，
#   那就只挂一个标题节点，不算错。
# * **书内跳转链接会被重映射**（`/Dest` 从「名字」改成指向合并册具体页的显式数组）：
#   hyperref 的锚点在各册之间是重名的，直接靠 pypdf 的名字表会让后面各册的同名锚点
#   全指到第 1 册去（实测 489 条错位）。详见 `_remap_book_links()` 上方注释。
#
# 用法::
#
#     python merge-pdf.py <输出目录> --version 3.15   # ★ --version 一定要传（默认 3.14）
#     python merge-pdf.py <输出目录> --list           # 只看目录树/缺册，**不需要 pypdf**
#     python merge-pdf.py <输出目录> -o 指定名字.pdf
#
# `--list` 末尾的 ASCII 标记（调用方只认它，别匹配中文）::
#
#     MISSING n       ★ 本版本**应当有却缺** —— 只有它代表真出事（合并门禁看它）
#     UNPRODUCED n    本版本**本就没有**（版本门控）—— 不是缺册
#     UNKNOWN n       未收录产物：`howto-*.pdf` 里 `name_map.py` 没登记的
#                     → 会保持英文名、且**不会进合并册**（结果静默少一章）
#
# 依赖 pypdf —— 但**只在真合并时**（延迟导入）；`--list` 只需标准库。
# """


import argparse
import datetime as _dt
import sys
from pathlib import Path


# ★ pypdf 延迟导入（2026-09-26 改）
#   以前是模块级 `from pypdf import ...`，于是**连 `--list` 都需要 pypdf** ——
#   而 `--list` 正是用来「先看看缺哪册」的那一步：没装 pypdf 时连缺册清单都看不到，
#   只能对着 `!! 需要 pypdf` 猜。现在只有真正合并时才要求它。
PdfReader = PdfWriter = None
ArrayObject = DictionaryObject = IndirectObject = NameObject = NullObject = None


def _need_pypdf() -> None:
    """真正要合并时再把 pypdf 拉进来；已加载则直接返回。"""
    global PdfReader, PdfWriter, ArrayObject, DictionaryObject
    global IndirectObject, NameObject, NullObject
    if PdfWriter is not None:
        return
    # ★ 先走 `_import_pypdf()`：它会（1）先试内置那份，（2）不行再从构建 venv 的
    #   site-packages 里导（2026-10-30 加，见那个函数的说明），（3）都没有才报错
    #   并带上真实的 ImportError 原因。千万别在这里直接 `from pypdf import …` ——
    #   那样就绕过了备用路径，又变成「明明装了却报缺 pypdf」。
    _import_pypdf("合并")
    try:
        from pypdf import PdfReader as _R, PdfWriter as _W
        from pypdf.generic import (ArrayObject as _A, DictionaryObject as _D,
                                   IndirectObject as _I, NameObject as _N,
                                   NullObject as _Null)
    except ImportError:                                # pragma: no cover
        print('!! 需要 pypdf：pip install pypdf（只有合并这一步需要；'
              '`--list` 不需要）', file=sys.stderr)
        raise SystemExit(2)
    PdfReader, PdfWriter = _R, _W
    ArrayObject, DictionaryObject = _A, _D
    IndirectObject, NameObject, NullObject = _I, _N, _Null

# pypdf 在 append 时会顺手「配对」每页的链接注解，好在最后修正命名目标；它的配对
# 对不上时会刷一堆 `Annotation sizes differ: 11 vs. 0` 的告警。我们的链接修正
# 完全不依赖它（见 _remap_book_links），所以把这一条静音，免得日志里看着像出错。
# 其他 pypdf 告警照常输出。
import logging                                         # noqa: E402


class _DropAnnPairWarn(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return 'Annotation sizes differ' not in record.getMessage()


logging.getLogger('pypdf.generic._link').addFilter(_DropAnnPairWarn())


# ---------------------------------------------------------------------------
# 合并结构表 —— ★ 全部来自 tools/name_map.py（唯一命名真源）
# ---------------------------------------------------------------------------
# 2026-09-26 之前这里自带一份表（`_MAIN` / `_HOWTO_GROUPS` / `_HOWTO_EXTRA` /
# `_TAIL` / `MIN_VERSION`），与 `rename-pdf.sh`、GUI 的 `RENAME_MAP` 三份并存，
# 必须手工同步 —— 实测漏同步过两次，都是换版本时才炸：
#   * asyncio 那册改名后这里没跟     → `--list` 报 `MISSING 1`；
#   * 3.13 目录报 `MISSING 1`（`0925远程调试附加协议`），因为版本门控只登记了 0929，
#     漏了 3.14 才新增的那一册。
# 现在统一从 name_map 取。**改分册名 / 编号 / 分组 / 版本门控，只改 name_map.py 一处。**


_ver_tuple = ver_tuple                     # 兼容旧调用点




def _scan_dir(indir: Path, version: str) -> tuple[list[str], list[str], list[str]]:
    """扫目录，返回 (本版本本就没有的册名, 未收录产物, 其它 PDF)。

    * **本版本本就没有**：版本门控掉的（如 3.13 没有 `0925远程调试附加协议`）——
      不是缺册，只是提示。以前这里也算「缺」，于是 3.13 的合并被误拒。
    * **未收录产物**：目录里出现了 `howto-xxx.pdf` 这类「源名」风格的文件，
      但 `name_map.py` 没登记它（典型场景：上游 3.15+ 又加了一篇 howto）——
      它会**保持英文名、也进不了合并册**，必须报出来。
    * **其它**：合并册本身、用户自己放的 PDF，只提示。
    """
    plan = rename_plan(version)
    known = set(plan.values())
    prefixed = tuple(s for s in plan if not s.startswith('howto-')) + ('howto-',)
    unprod = [f for _s, f in unproduced(version)]
    unknown, other = [], []
    for pdf in sorted(indir.glob('*.pdf')):
        if pdf.stem in known:
            continue
        (unknown if pdf.stem.startswith(prefixed) else other).append(pdf.name)
    return unprod, unknown, other


def _report_unknown(unknown: list[str], version: str) -> None:
    if not unknown:
        return
    spare = spare_numbers(version)
    print(f'!! 目录里有 {len(unknown)} 个「未收录产物」（name_map.py 里没登记，'
          f'会保持英文名、且进不了合并册）：')
    for n in unknown[:8]:
        print(f'     · {n}')
    if len(unknown) > 8:
        print(f'     …（共 {len(unknown)} 个）')
    print(f'   处理：在 tools/name_map.py 的 HOWTO 表补一行 '
          f'(slug, \'09NN中文名\', \'书签标题\', \'分组\')；'
          f'本版本空号 {" ".join(spare) if spare else "（无，往后取 0930+）"}')


def parse_spec(spec: list[tuple[str, str, int]]) -> list[list]:
    """拍平表 → 嵌套树 [标题, 文件名 or None, [子节点]]。"""
    root: list = []
    stack: list[tuple[int, list]] = [(-1, root)]     # (层级, 该层的子列表)

    for name, title, level in spec:
        while stack[-1][0] >= level:                 # 回到 level 的父层
            stack.pop()
        node: list = [title, name or None, []]
        stack[-1][1].append(node)
        stack.append((level, node[2]))
    return root


def _fmt_tree(nodes: list, depth: int = 0, out: list[str] | None = None) -> list[str]:
    out = out if out is not None else []
    for title, fname, kids in nodes:
        out.append(f'{"    " * depth}{title}' + ('' if fname else '   （分组，指向第一个子项）'))
        _fmt_tree(kids, depth + 1, out)
    return out


def _first_page(kids: list, offs: dict[str, int]) -> int | None:
    """分组节点的落点：第一个有页的后代。"""
    for _t, f, k in kids:
        if f:
            return offs[f]
        p = _first_page(k, offs)
        if p is not None:
            return p
    return None


# ---------------------------------------------------------------------------
# 书内跳转链接的重映射（★ 这一步不能省）
# ---------------------------------------------------------------------------
# xelatex/hyperref 给每册的锚点起的名字是 **各册重名** 的（`section.1`、
# `subsection.2.1`、`page.10`、`index:xxx`…），而 pypdf 的
# `NamedReferenceLink.patch_reference()` 只在「目标册里还没登记这个名字」时才写：
#
#     if str(self._reference) not in target_pdf.named_destinations:
#         target_pdf.add_named_destination(...)
#
# 于是 **第 2 册以后的同名锚点全都指到第 1 册的页上**（实测 489 条错位：
# 正则表达式指南第 1 页的 `section.1` 被解析到合并册第 5 页）。
#
# 修法：不依赖 pypdf 的名字表，直接把每条链接的 `/Dest`（或 `/A /D`）从
# 「名字」改写成**指向合并册具体页的显式数组** `[页引用 /XYZ null null null]`。
# 页号按「本册第 i 页 → 合并册第 offset+i 页」算，天然不会串册。

def _dest_array(writer: PdfWriter, page_index: int) -> ArrayObject:
    return ArrayObject([writer.pages[page_index].indirect_reference,
                        NameObject('/XYZ'), NullObject(), NullObject(), NullObject()])


def _remap_book_links(writer: PdfWriter, reader: PdfReader, base: int,
                      stats: dict[str, int]) -> None:
    """把某一册的命名/显式目标链接改写成合并册里的绝对页目标。"""
    # 锚点名 → 本册页索引
    name2idx: dict[str, int] = {}
    try:
        for k, d in reader.named_destinations.items():
            try:
                name2idx[str(k)] = reader.get_destination_page_number(d)
            except Exception:                       # noqa: BLE001
                pass
    except Exception:                               # noqa: BLE001
        pass
    # 页对象 idnum → 本册页索引（给「本来就是显式数组」的链接用）
    obj2idx: dict[int, int] = {p.indirect_reference.idnum: i
                               for i, p in enumerate(reader.pages)}
    n_pages = len(reader.pages)

    for i in range(n_pages):
        try:
            page = writer.pages[base + i]
            dict_obj = page.indirect_reference.get_object()
        except Exception:                           # noqa: BLE001
            continue
        annots = dict_obj.get('/Annots')
        if annots is None:
            continue
        arr = annots.get_object()
        if not isinstance(arr, ArrayObject):
            continue
        for a in arr:
            d = a.get_object()
            if not isinstance(d, DictionaryObject) or d.get('/Subtype') != '/Link':
                continue
            holders = [(d, NameObject('/Dest'))]
            act = d.get('/A')
            if act is not None:
                act = act.get_object()
                if isinstance(act, DictionaryObject):
                    holders.append((act, NameObject('/D')))
            for holder, key in holders:
                ref = holder.get(key)
                if ref is None:
                    continue
                ref = ref.get_object()
                tgt = None
                if isinstance(ref, str):                    # 命名目标
                    tgt = name2idx.get(str(ref))
                elif (isinstance(ref, ArrayObject) and len(ref)
                      and isinstance(ref[0], IndirectObject)):
                    tgt = obj2idx.get(ref[0].idnum)         # 已经是显式数组
                if tgt is None or base + tgt >= len(writer.pages):
                    stats['miss'] += 1
                    continue
                holder[key] = _dest_array(writer, base + tgt)
                stats['fixed'] += 1


# ---------------------------------------------------------------------------
# 合并
# ---------------------------------------------------------------------------
def _copy_outline(writer: PdfWriter, reader: PdfReader, nodes: list,
                  parent, offset: int, stats: list[int]) -> None:
    """把 reader 的书签树整棵复制到 writer，页码 +offset。

    pypdf 的 outline 是「节点后紧跟一个子列表」的形式，所以这里手写游标遍历。
    """
    i, n = 0, len(nodes)
    while i < n:
        item = nodes[i]
        if isinstance(item, list):          # 上一个节点的子表（已在下面处理过）
            i += 1
            continue
        child = None
        try:
            page = reader.get_destination_page_number(item) + offset
            child = writer.add_outline_item(item.title, page,
                                            parent=parent, is_open=False)
            stats[0] += 1
        except Exception as e:              # noqa: BLE001
            # 极少数书签目标已坏：跳过它，别让整册失败
            stats[1] += 1
            if stats[1] <= 5:
                print(f'      ! 跳过坏书签 {item.title!r}：{e}', file=sys.stderr)
        i += 1
        if i < n and isinstance(nodes[i], list):
            if child is not None:
                _copy_outline(writer, reader, nodes[i], child, offset, stats)
            i += 1


def merge(indir: Path, out: Path, *, quiet: bool = False,
          no_outline: bool = False, version: str = '3.14') -> dict:
    spec = build_spec(version)
    tree = parse_spec(spec)

    missing = [f'{n}.pdf' for n, _t, _lv in spec if n and not (indir / f'{n}.pdf').is_file()]
    if missing:
        raise SystemExit('!! 以下分册不在 %s 里，先跑完步骤 8（收集+重命名）：\n   %s'
                         % (indir, '\n   '.join(missing)))
    # 缺册过了再报告「未收录产物」：它不会让合并失败，但会**静默少一章**，
    # 所以要在这里就说清楚（这次不挡路，但别让人事后才发现）。
    _unprod, _unknown, _other = _scan_dir(indir, version)
    if _unknown and not quiet:
        _report_unknown(_unknown, version)
    _need_pypdf()
    books = [n for n, _t, _lv in spec if n]
    if not quiet:
        print(f'合并 {len(books)} 册 → {out.name}')

    writer = PdfWriter()
    offsets: dict[str, int] = {}
    readers: dict[str, PdfReader] = {}
    total = 0
    for name, _t, _lv in spec:
        if not name:
            continue
        r = PdfReader(str(indir / f'{name}.pdf'))
        readers[name] = r
        offsets[name] = total
        total += len(r.pages)
        writer.append(r, import_outline=False)     # 书签我们自己挂，不让它铺平
    if not quiet:
        print(f'  页数合计 {total}')

    # ★ 书内跳转链接：必须自己重映射（原因见 _remap_book_links 上方注释）
    link_stats = {'fixed': 0, 'miss': 0}
    for name, _t, _lv in spec:
        if name:
            _remap_book_links(writer, readers[name], offsets[name], link_stats)
    if not quiet:
        print(f'  书内跳转链接：重映射 {link_stats["fixed"]} 条'
              + (f'，无法定位 {link_stats["miss"]} 条' if link_stats['miss'] else ''))

    stats = [0, 0]                                  # [挂上的书签, 跳过的坏书签]
    if not no_outline:
        def build(nodes: list, parent, depth: int) -> None:
            for title, fname, kids in nodes:
                page = offsets[fname] if fname else _first_page(kids, offsets)
                child = writer.add_outline_item(title, page if page is not None else 0,
                                                parent=parent, is_open=(depth < 1))
                stats[0] += 1
                if fname:
                    _copy_outline(writer, readers[fname], readers[fname].outline,
                                  child, offsets[fname], stats)
                else:
                    build(kids, child, depth + 1)

        build(tree, None, 0)

    writer.add_metadata({'/Title': out.stem,
                         '/Producer': 'sphinx-pdf merge-pdf.py (pypdf)'})
    tmp = out.with_suffix('.part.pdf')
    with open(tmp, 'wb') as fh:
        writer.write(fh)
    # ★ 先写 .part.pdf、成功了再换名 —— 别写到一半留下一个坏 PDF。
    #   ⚠️ Windows 上这一步会被「刚写完的 50 MB 文件正被杀软实时扫描」打断，
    #      报 `PermissionError: [WinError 5] 拒绝访问`（实测重跑一次就好，
    #      手工 `mv` 同一个文件反而成功）—— 所以退避重试；
    #      6 次仍被拒就退化成「先删目标再换名」：放弃原子性，
    #      但总比整轮合并白跑一场强。
    import time as _time
    for attempt in range(6):
        try:
            tmp.replace(out)
            break
        except PermissionError:
            if attempt < 5:
                _time.sleep(0.5 * (attempt + 1))
                continue
            if out.exists():
                out.unlink()
            tmp.replace(out)
    return {'pages': total, 'books': len(books),
            'marks': stats[0], 'bad_marks': stats[1],
            'links': link_stats['fixed'], 'links_miss': link_stats['miss'],
            'out': out}


def mgpdf_main() -> int:
    ap = argparse.ArgumentParser(description='把 38 册分册 PDF 合并成一本带完整书签的总册')
    ap.add_argument('indir', help='分册 PDF 所在目录（步骤 8 的输出目录）')
    ap.add_argument('-o', '--out', default=None,
                    help='输出文件名（默认 Python <版本> 文档 <日期>.pdf）')
    ap.add_argument('--version', default='3.14',
                    help='版本号：决定默认输出文件名，也决定册名里的版本'
                         '（01Python <版本> 有什么新变化）')
    ap.add_argument('--full-version', dest='full_version', default='',
                    help='完整版本号（如 3.13.16），只用于默认输出文件名；'
                         '留空 = 同 --version')
    ap.add_argument('--list', action='store_true', help='只打印计划的目录树，不合并')
    ap.add_argument('--no-outline', action='store_true', help='只合并页面、不挂书签（排查用）')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    indir = Path(args.indir)
    if not indir.is_dir():
        print(f'!! 目录不存在：{indir}', file=sys.stderr)
        return 1

    if args.list:
        spec = build_spec(args.version)
        print('\n'.join(_fmt_tree(parse_spec(spec))))
        have = len([1 for n, _t, _lv in spec if n])
        miss = [f'{n}.pdf' for n, _t, _lv in spec
                if n and not (indir / f'{n}.pdf').is_file()]
        unprod, unknown, other = _scan_dir(indir, args.version)
        got = guess_version(indir)
        print(f'\n共 {have} 册 + {len(spec) - have} 个分组节点；'
              f'{indir} 里缺 {len(miss)} 册'
              + (f'：{brief(miss)}' if miss else ''))
        if got and ver_tuple(got) != ver_tuple(args.version):
            print(f'!! 目录里的册子看起来是 **{got}** 的'
                  f'（`01Python {got} 有什么新变化.pdf`），但这次按 **{args.version}** 处理。'
                  f'若 `--version` 传错，下面的「缺册」全是假警报。')
        if unprod:
            print(f'   本版本本就没有 {len(unprod)} 册（版本门控，不算缺册）：'
                  + '、'.join(unprod))
        _report_unknown(unknown, args.version)
        if other:
            print(f'   另有 {len(other)} 个非分册 PDF（合并册等，不管）：'
                  + '、'.join(other[:4]) + ('…' if len(other) > 4 else ''))
        # ★ 给调用方（GUI 步骤 9 / build-sphinx-pdf.sh）的 ASCII 标记：
        #   靠中文"缺 0 册"去匹配，在 GBK/locale 不匹配的环境中会静默失配。
        #   MISSING 只数「本版本应当有却缺」，版本门控掉的不算 —— 3.13 的合并
        #   就是这样被误拒过一次（0925 是 3.14 才新增的）。
        print(f'MISSING {len(miss)}')
        print(f'UNPRODUCED {len(unprod)}')
        print(f'UNKNOWN {len(unknown)}')
        return 0

    name = (args.out
            or f'Python {args.full_version or args.version} 文档 '
               f'{_dt.date.today():%Y%m%d}.pdf')
    if not name.lower().endswith('.pdf'):
        name += '.pdf'
    out = Path(name)
    if not out.is_absolute():
        out = indir / out

    try:
        st = merge(indir, out, quiet=args.quiet, no_outline=args.no_outline,
                   version=args.version)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 1
    if not args.quiet:
        size = out.stat().st_size / 1024 / 1024
        print(f'OK  {out.name}  {st["pages"]} 页  {size:.1f} MB  '
              f'书签 {st["marks"]} 个  书内跳转链接 {st["links"]} 条'
              + (f'（无法定位 {st["links_miss"]} 条）' if st['links_miss'] else '')
              + (f'  跳过坏书签 {st["bad_marks"]} 个' if st['bad_marks'] else ''))
    return 0

# ---------------------------------------------------------------------------
# 内置工具：report.py（原样内联，逻辑一行未改）
#   入口：rpt_main
# ---------------------------------------------------------------------------
# """生成分册 PDF 验收报告（Markdown）。
#
# 用法:
#     python tools/report.py <pdf 目录> [<latex 日志目录>]
# 例:
#     python tools/report.py pdf C:/pypdfbuild/zh/cpython/Doc/build/latex
#
# 每册检查：页数 / 体积 / 书签数 / 链接注释数（含其中带内部跳转的）/
# 日志里的 `Invalid UTF-8` 条数 / 封面首行标题（核对步骤 6b 的中文化是否生效）。
# """

import argparse
import contextlib
import glob
import io
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

def rpt_PdfReader(*args, **kwargs):                # noqa: N802
    """懒加载 pypdf：主程序本身不强制依赖它（只有报表/查空白页才需要）。

    ★ 原来是模块级 `from pypdf import PdfReader` —— 内联进主程序后会让
      「没装 pypdf 就跑不了 --cli」这种事复活（本文件刻意只在 GUI 段才要求 PyQt6）。
    """
    _Real = _import_pypdf("本工具").PdfReader
    return _Real(*args, **kwargs)

CJK = re.compile(r"[\u4e00-\u9fff]")


def rpt_walk(items) -> int:
    n = 0
    for it in items:
        if isinstance(it, list):
            n += rpt_walk(it)
        else:
            n += 1
    return n


def annots(page) -> list:
    """取页面的 /Annots 数组。

    ⚠️ `page.get('/Annots')` 返回的是 **IndirectObject**（间接引用），对它直接
       `len()` 会抛错或被吞成 0 —— 必须先 `.get_object()` 解引用。
       不这么写，链接数会永远显示 0。
    """
    a = page.get("/Annots")
    if a is None:
        return []
    if hasattr(a, "get_object"):
        a = a.get_object()
    try:
        return list(a)
    except TypeError:
        return []


def link_stats(reader) -> tuple[int, int]:
    """返回 (全书链接注释数, 其中带内部跳转的数)。"""
    total = inner = 0
    for p in reader.pages:
        for an in annots(p):
            try:
                an = an.get_object()
            except Exception:
                continue
            total += 1
            if an.get("/Dest") is not None:
                inner += 1
            else:
                a = an.get("/A")
                if a is not None:
                    a = a.get_object()
                    if a.get("/S") == "/GoTo":
                        inner += 1
    return total, inner


def cover_line(pdf: str) -> str:
    """取封面（第 1 页）第一行非空文字。"""
    try:
        out = subprocess.run(["pdftotext", "-f", "1", "-l", "1", pdf, "-"],
                             capture_output=True, timeout=60,
                             creationflags=CREATE_NO_WINDOW).stdout
    except Exception:
        return "?"
    for line in out.decode("utf-8", "replace").splitlines():
        if line.strip():
            return line.strip()
    return "(空白)"


def _sphinx_ver(log_dir: str) -> str:
    """从构建日志里抠出 Sphinx 版本（找不到就返回空串）。

    ★ 要**往上找**：调用方传进来的 log_dir 是 `<root>/cpython/Doc/build/latex`
      （每册的 `library.log` 之类在这里），而 `latex-build.log` 是写在 `<root>` 的。
    ★ 正则要**语言无关**：因为 `-D language=zh_CN`，这一行是中文的
      「正在运行 Sphinx v8.2.3」，写死 `Running Sphinx v` 一个字都匹配不上。
      （`Sphinx v` 这个片段两种语言都有；`RemovedInSphinx90Warning` 那种没有 v，
        所以用 `Sphinx\\s+v` 不会误伤。）
    """
    if not log_dir:
        return ""
    d = Path(log_dir)
    for _ in range(6):
        for cand in ("latex-build.log", "pdf-build.log"):
            try:
                m = re.search(r"Sphinx\s+v([0-9][\w.\-+]*)",
                              (d / cand).read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if m:
                return m.group(1)
        if d.parent == d:
            break
        d = d.parent
    return ""


def rpt_main() -> int:
    """打印报告，并把它**写成文件**。

    ★ 为什么以前没有这个文件：本脚本一直只往 stdout `print`，而步骤 8 却对外报
      「验收报告：<输出目录>/验收报告.md」—— 报告内容其实全进了 `report.log`，
      输出目录里根本没有 `验收报告.md`（2026-09-26 实测发现）。现在自己落盘。
    """
    ap = argparse.ArgumentParser(description="生成分册 PDF 验收报告（Markdown）")
    ap.add_argument("pdf_dir", nargs="?", default=".", help="PDF 目录（默认当前目录）")
    ap.add_argument("log_dir", nargs="?", default="", help="日志目录（latex 构建目录）")
    ap.add_argument("-o", "--out", default=None,
                    help="输出 .md 路径（默认 <pdf_dir>/验收报告.md；填 - 表示只打印不写盘）")
    ap.add_argument("--version", default=None,
                    help="Python 版本，如 3.15（留空则从册名推断）")
    a = ap.parse_args()

    ver = a.version or _guess_version(a.pdf_dir) or "3.14"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = _emit(a.pdf_dir, a.log_dir, ver)
    text = buf.getvalue()
    # 非 f-string 的大段正文里不能写 `{ver}`（正文本身含 `\\title{...}` 这种字面花括号），
    # 所以那两处版本号用占位符 @@VER@@ 标记，这里统一替换。
    text = text.replace("@@VER@@", ver)
    sys.stdout.write(text)

    if a.out == "-":
        return rc
    out = Path(a.out) if a.out else Path(a.pdf_dir) / "验收报告.md"
    try:
        out.write_text(text, encoding="utf-8")
    except OSError as e:                                          # pragma: no cover
        print(f"[报告写不进去] {out}：{e}")
        return 1
    print(f"[报告已写入] {out}")
    return rc


_STEP_LINE_RE = re.compile(r"^----- 步骤\s+(\S+)\s+(.+?)：(完成|失败)（([0-9hms]+)）(.*)$")
_DUR_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")


def _dur_secs(txt: str) -> float:
    """把 `1h05m` / `3m21s` / `45s` 解成秒；认不出返回 -1。"""
    m = _DUR_RE.match((txt or "").strip())
    if not m or not any(m.groups()):
        return -1.0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def _step_timings(pdf_dir: str) -> tuple[list[tuple[str, str, str, bool]], list[str], str, str]:
    """从构建根里的 `gui-build.log` 抽出「每一步的耗时」。

    返回 (步骤列表[(名字, 用时, 说明, 是否成功)], 细分说明, 开始时间, 总用时)。
    ★ 只读日志，不碰任何产物；日志不在（比如步骤 10 选了「全清理」）就返回空，
      报告里宁可写一句实话，也不编造耗时。
    ★ 同一步骤跑了两次（重试）时保留**最后一次**，顺序按首次出现。
    """
    cands = [os.path.join(pdf_dir, "gui-build.log"),
             os.path.join(os.path.dirname(os.path.abspath(pdf_dir)), "gui-build.log")]
    log = next((p for p in cands if os.path.exists(p)), "")
    if not log:
        return [], [], "", ""
    steps: dict[str, tuple[str, str, bool]] = {}
    notes: list[str] = []
    started = total = ""
    try:
        with open(log, encoding="utf-8", errors="replace") as fp:
            for line in fp:
                line = line.rstrip("\n")
                if line.startswith("# 构建开始"):
                    started = line.split("构建开始", 1)[1].strip()
                    continue
                if line.startswith("# 构建结束"):
                    m = re.search(r"用时\s+(\S+)", line)
                    total = m.group(1) if m else ""
                    continue
                if "读入 " in line and "篇/分" in line:      # 步骤 6 的细分（读入/写出）
                    notes.append(line.strip())
                    continue
                m = _STEP_LINE_RE.match(line)
                if m:
                    label, title, state, dur, tail = m.groups()
                    steps[f"步骤 {label} {title}".strip()] = (dur, tail.strip(), state == "完成")
    except OSError:
        return [], [], "", ""
    return ([(k, v[0], v[1], v[2]) for k, v in steps.items()], notes, started, total)


def _print_step_timings(pdf_dir: str) -> None:
    """输出「每步耗时」小节（验收报告的收尾段）。"""
    steps, notes, started, total = _step_timings(pdf_dir)
    print("\n## 每步耗时\n")
    if not steps:
        print("（找不到本轮 `gui-build.log` —— 可能步骤 10 选了「全清理」、"
              "或报告是单独跑的。想看耗时就把「步骤 10 清理范围」改成「不清理」。）")
        return
    head = []
    if started:
        head.append(f"开始 {started}")
    if total:
        head.append(f"总用时 **{total}**")
    if head:
        print("　".join(head) + "\n")
    print("| 步骤 | 用时 | 结果 |")
    print("|-|-:|-|")
    acc = 0.0
    for name, dur, tail, ok in steps:
        secs = _dur_secs(dur)
        if secs > 0:
            acc += secs
        mark = "✔" if ok else "**✘ 失败**"
        note = sanitize_cell(tail)[:60]
        print(f"| {name} | {dur} | {mark}{'　' + note if note else ''} |")
    print(f"| **合计（各步相加）** | **{human_dur(acc)}** | |")
    for n in notes:
        print(f"\n> 步骤 6 细分：`{n}`")


def sanitize_cell(txt: str) -> str:
    """表格单元格里的 `|` 会把列打断，统一转义。"""
    return (txt or "").replace("|", r"\|").strip()


def _guess_version(pdf_dir: str) -> str:
    """从 `01Python X.Y 有什么新变化.pdf` 这种册名里推断版本。"""
    for f in sorted(glob.glob(os.path.join(pdf_dir, "0*有什么新变化*.pdf"))):
        m = re.search(r"Python\s+(\d+\.\d+)", os.path.basename(f))
        if m:
            return m.group(1)
    return ""


def _emit(pdf_dir: str, log_dir: str, ver: str) -> int:

    rows = []
    for f in sorted(glob.glob(os.path.join(pdf_dir, "*.pdf"))):
        name = os.path.basename(f)
        size = os.path.getsize(f) / 1048576
        pages = bookmarks = links = inner = -1
        try:
            r = rpt_PdfReader(f)
            pages = len(r.pages)
            try:
                bookmarks = rpt_walk(r.outline)
            except Exception:
                bookmarks = 0
            try:
                links, inner = link_stats(r)
            except Exception:
                links = inner = 0
            bad: int | str = "—"
            if log_dir:
                log = os.path.join(log_dir, name.replace(".pdf", ".log"))
                if os.path.exists(log):
                    txt = open(log, "rb").read().decode("utf-8", "replace")
                    bad = len(re.findall(r"Invalid UTF-8", txt))
            rows.append((name, pages, size, bookmarks, links, inner, bad, cover_line(f)))
        except Exception:
            rows.append((name, -1, size, -1, -1, -1, "—", "?"))

    total_pages = sum(r[1] for r in rows if r[1] > 0)
    total_size = sum(r[2] for r in rows)
    with_bm = sum(1 for r in rows if r[3] > 0)
    bad_total = sum(r[6] for r in rows if isinstance(r[6], int))
    zh_cover = sum(1 for r in rows if CJK.search(r[7]))
    en_cover = [r[0] for r in rows if not CJK.search(r[7])]

    print(f"""# 分册 PDF 验收报告

- 生成时间：{datetime.now():%Y-%m-%d %H:%M}
- 版本：Python 文档 **{ver}**（中文，python-docs-zh-cn {ver}）
- 构建：Sphinx {_sphinx_ver(log_dir) or '?'} + `latex_engine='xelatex'` + `-D language=zh_CN` + TeX Live 2025
- 册数：**{len(rows)}**　总页数：**{total_pages}**　总体积：**{total_size:.1f} MB**
- 有书签的册子：**{with_bm}/{len(rows)}**
- 索引里的非法 UTF-8 字节（`Invalid UTF-8` 日志条数）合计：**{bad_total}**
- 封面标题已中文化：**{zh_cover}/{len(rows)}**
  {'（全部中文）' if not en_cover else '（仍是英文：' + '、'.join(en_cover) + '）'}

## 逐册明细

| 册子 | 页数 | 体积 (MB) | 书签 | 链接 (内部跳转) | 索引非法字节 | 封面首行 |
|-|-:|-:|-:|-:|-:|-:|""")
    for name, pages, size, bm, links, inner, bad, cover in rows:
        note = '' if bm > 0 or pages <= 0 else '（无小节）'
        print(f"| {name} | {pages if pages > 0 else '**失败**'} | {size:.2f} | "
              f"{bm}{note} | {links} ({inner}) | {bad} | {cover[:34]} |")

    print("""
## 核对项

| 项目 | 参考样张 | 本次产物 |
|-|-|-|
| 纸型 | A4（595.28 × 841.89 pt） | A4 |
| 封面标题 | **英文**（`The Python Language Reference`、`Python Tutorial` …，因为 `latex_documents` 不走 `.po`） | **中文**（本轮按要求中文化，**有意与样张不同**） |
| 封面地址块 | PSF + `docs@python.org` | 同款 |
| 页脚版本 | 发行版本 3.14.x | 发行版本 @@VER@@ |
| 中文字体 | FandolSong / FandolHei / FandolKai / FandolFang | 同族 |
| 西文字体 | FreeSerif / FreeSans / FreeMono | 同族 |
| 正文前目录 | 带点线 + 页码，3 级 | 同款 |
| PDF 书签 | 有 | 有（1~2 页跳转占位页除外） |
| 内部超链接 | 有 | 有 |
| 索引末尾 | 无 `�` | **无 `�`** |
""")
    _print_step_timings(pdf_dir)
    return 0

# ---------------------------------------------------------------------------
# 内置工具：check-pdf-gaps.py（原样内联，逻辑一行未改）
#   入口：cpg_main
# ---------------------------------------------------------------------------
# """扫一本成品 PDF，找出「几乎空白」的页，并报出它落在哪个章节。
#
# 背景：Sphinx 找不到 `literalinclude` / `include` 的目标时**不报错**，
# 把整段内容跳过 —— 于是正文整章消失，PDF 里只留下标题页和一片空白，
# 而构建日志全绿。这类「静默少内容」只能从成品里反过来查。
#
# 判据：页面 `/Contents` 内容流的字节数。
#   · 正常正文页  ≈ 15000 ~ 25000 字节
#   · 章节标题页  ≈ 2000 ~ 4000（有标题 + 页眉页脚）
#   · 空白页      < 1000（只有页眉页脚）
# 中文 PDF 用字体子集 + 自定义编码，`extract_text()` 基本取不到文字，
# 所以**不能**靠搜文本来判断。
#
# ⚠️ **怎么读结果**：本工具会连**正常**的空白页一起列出来 ——
# `book` 文档类默认 `openright`，每章结束会补一个空白页让下一章从右页（奇数页）开始，
# 所以「某章末尾有一页空白」是排版需要、不是缺内容。
# 真正要警惕的是「**整章只有标题页 + 空白页、没有正文页**」那种，例如
# 《Python 语言参考手册》的「完整的语法规范」本该 20 多页，却只剩 149/150 两页
# （`Grammar/python.gram` 没进稀疏检出，`literalinclude` 被整段跳过）。
# 判断办法：看空白页**后面**紧跟着的是不是下一个章节 —— 若是、而本章只有一两页，
# 那就是缺内容。
#
# 用法::
#
#     python tools/check-pdf-gaps.py <pdf> [阈值字节]      # 默认阈值 1000
# """

import sys
from pathlib import Path

def cpg_PdfReader(*args, **kwargs):                # noqa: N802
    """懒加载 pypdf：主程序本身不强制依赖它（只有报表/查空白页才需要）。

    ★ 原来是模块级 `from pypdf import PdfReader` —— 内联进主程序后会让
      「没装 pypdf 就跑不了 --cli」这种事复活（本文件刻意只在 GUI 段才要求 PyQt6）。
    """
    _Real = _import_pypdf("本工具").PdfReader
    return _Real(*args, **kwargs)


def flat(items, d=0, out=None):
    out = [] if out is None else out
    for it in items:
        if isinstance(it, list):
            flat(it, d + 1, out)
        else:
            out.append((d, str(it.title), it))
    return out


def pbytes(r, i: int) -> int:
    try:
        c = r.pages[i].get_contents()
        if c is None:
            return 0
        return len(c.get_data())
    except Exception:
        return -1


def cpg_main() -> None:
    pdf = Path(sys.argv[1])
    thr = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    r = cpg_PdfReader(str(pdf))
    n = len(r.pages)

    # 书签 → 页号，用来给空白页归属章节
    marks: list[tuple[int, str]] = []
    try:
        for d, t, node in flat(r.outline):
            try:
                p = r.get_destination_page_number(node)
            except Exception:
                p = None
            if p is not None:
                marks.append((p, t))
    except Exception:
        pass
    marks.sort()

    def owner(i: int) -> str:
        name = "（封面/前言）"
        for p, t in marks:
            if p <= i:
                name = t
            else:
                break
        return name

    bad = [(i, pbytes(r, i)) for i in range(n)]
    bad = [(i, b) for i, b in bad if 0 <= b < thr]
    print(f"=== {pdf.name} ===")
    print(f"  总 {n} 页，内容流 < {thr} 字节的有 {len(bad)} 页")
    for i, b in bad[:40]:
        print(f"      第 {i + 1:>4} 页  {b:>6} 字节   所属章节：{owner(i)}")
    if len(bad) > 40:
        print(f"      …（共 {len(bad)} 页）")

# ---------------------------------------------------------------------------
# 内置工具：fix-md-escapes.py（原样内联，逻辑一行未改）
#   入口：fmd_main
# ---------------------------------------------------------------------------
# """把被「两轮 escape」叠坏的反斜杠还原回去（仅限 sphinx-pdf 下的 .md 文档）。
#
# 背景
# ----
# `sphinx-pdf/构建Python文档PDF-完整步骤.md` 与 `sphinx-pdf/pdf/验收报告.md`
# 在早期生成时被 escape 了两轮，于是正文里出现大量**多余的反斜杠**，
# markdown 渲染出来是一堆 `\\` / `\\\\`，里面的 shell 命令**照抄就跑不通**。
#
# 实测（用 Python 数出每段反斜杠串的真实长度）：
#     3 个 + 标点   ← 原文 0 个（标点被转义：`*` → `\\*` → `\\\\\\*`）
#     4 个 + 任何字符 ← 原文 1 个（反斜杠本身被转义：`\\` → `\\\\` → `\\\\\\\\`）
#     8 个 + 任何字符 ← 原文 2 个
#
# 只动 **≥3 个** 的串 —— 1~2 个的那种是**合法**的 markdown 转义（`\\.` `\\|` …）
# 或**真正的代码**（正则 `\\s` `\\d`、LaTeX `\\usepackage`），碰了反而编坏。
#
# 用法::
#
#     python sphinx-pdf/tools/fix-md-escapes.py <sphinx-pdf 目录> --dry-run
#     python sphinx-pdf/tools/fix-md-escapes.py <sphinx-pdf 目录>
# """


import argparse
import re
import shutil
import sys
from pathlib import Path

#: 反斜杠串 → 还原后的反斜杠个数（只列 ≥3 的）
_RUN_MAP = {3: 0, 4: 1, 8: 2}


def fmd_fix_text(s: str) -> str:
    def rep(m: re.Match) -> str:
        n = len(m.group(1))
        back = _RUN_MAP.get(n)
        if back is None:            # 长度没算准就原样留着，绝不猜
            return m.group(0)
        return "\\" * back + m.group(2)

    return re.sub(r"(\\{3,})(.)", rep, s, flags=re.S)


def fmd_main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="sphinx-pdf 目录")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    root = Path(a.root)
    if not root.is_dir():
        print(f"ERROR 不是目录：{root}", file=sys.stderr)
        return 2

    bak = root / "_bak_escape"
    todo = 0
    for f in sorted(list(root.rglob("*.md"))):
        if "_bak_escape" in f.parts:
            continue
        s = f.read_text(encoding="utf-8")
        new = fmd_fix_text(s)
        if new == s:
            print(f"SKIP  {f.relative_to(root)}")
            continue
        runs = len(re.findall(r"\\{3,}", s))
        todo += 1
        if a.dry_run:
            print(f"WOULD {f.relative_to(root)}  修正 {runs} 处")
            continue
        bak.mkdir(exist_ok=True)
        shutil.copy2(f, bak / f.name)
        f.write_text(new, encoding="utf-8")
        left = len(re.findall(r"\\{3,}", new))
        print(f"FIXED {f.relative_to(root)}  修正 {runs} 处，残留 {left}")

    print(f"CHANGED {todo}")
    return 0

# ---------------------------------------------------------------------------
# 内置工具：verify-pdf.py（原是平铺脚本，改成 vpdf_main(argv)）
# ---------------------------------------------------------------------------
import glob
import os
import sys

def vpdf_PdfReader(*args, **kwargs):                # noqa: N802
    """懒加载 pypdf：主程序本身不强制依赖它（只有报表/查空白页才需要）。

    ★ 原来是模块级 `from pypdf import PdfReader` —— 内联进主程序后会让
      「没装 pypdf 就跑不了 --cli」这种事复活（本文件刻意只在 GUI 段才要求 PyQt6）。
    """
    _Real = _import_pypdf("本工具").PdfReader
    return _Real(*args, **kwargs)


def vpdf_walk(items, depth=0):
    n = 0
    for it in items:
        if isinstance(it, list):
            n += vpdf_walk(it, depth + 1)
        else:
            n += 1
    return n



def vpdf_main() -> int:
    d = sys.argv[1] if len(sys.argv) > 1 else '.'
    rows = []
    for f in sorted(glob.glob(os.path.join(d, '*.pdf'))):
        name = os.path.basename(f)
        try:
            r = vpdf_PdfReader(f)
            pages = len(r.pages)
            try:
                outline = vpdf_walk(r.outline)
            except Exception:
                outline = -1
            try:
                # ★ 用上面的 annots()，不要退回 `len(p.get('/Annots') or [])`：
                #   pypdf 6.x 下 `/Annots` 是 **IndirectObject**，直接 len() 抛
                #   TypeError → 被这里吞掉 → 每一册都显示 -1（实测 3.13.16 全部如此）。
                #   ★ 这次是**有意**跨段共用 annots()：本项目要的就是「/Annots 怎么读
                #     只有一处实现」；而内联早期那次 vpdf 用错 `walk`/`PdfReader`
                #     是**无心**的跨段串味 —— 两者性质不同，别混为一谈。
                links = sum(len(annots(p)) for p in list(r.pages)[:40])
            except Exception:
                links = -1
            rows.append((name, pages, outline, links))
        except Exception as e:
            rows.append((name, -1, -1, -1))

    print(f"{'文件':<38}{'页数':>7}{'书签':>7}{'前40页链接':>11}")
    print('-' * 64)
    for n, p, o, l in rows:
        flag = '' if (p > 0 and o > 0) else '   <-- 待查'
        print(f"{n:<38}{p:>7}{o:>7}{l:>11}{flag}")
    print('-' * 64)
    print(f"总计 {len(rows)} 个 PDF；有书签的 {sum(1 for _,p,o,_ in rows if o > 0)} 个")

    return 0



def _tool_run(fn, argv, cwd: Path | None = None) -> tuple[int, str]:
    """在**本进程内**跑一个内置工具，返回 (退出码, 它打到 stdout/stderr 的文本)。

    ★ 工具本身仍是「命令行形状」（读 `sys.argv`、`print` 到 stdout），这里只把
      这两样临时替换掉。好处：内联前后行为完全一致，工具代码一行都不用改。
    ★ 必须整套换掉 stdout/stderr：GUI（pythonw）里 `sys.stdout` 可能是 None，
      而工具会 print。
    ★ 退出码的三种来源都要接住：正常 return / `SystemExit` / `sys.exit()`。
    ★ 其它异常也接住（打印 traceback、返回 1）：工具是「命令行形状」，
      单独跑时异常就是「打 traceback + 退出码 1」；不接的话会冒泡成**整个程序崩**，
      还会在 GUI 里弹一个跟工具无关的「启动错误」框（pythonw 下 stdout 是 None）。
      需要一个没装的依赖（如 pypdf）时尤其明显 —— 应该只报一句，不该炸。
    """
    import contextlib
    import io
    import traceback

    buf = io.StringIO()
    old_argv, old_cwd = sys.argv, None
    # sys.argv[0] 决定 argparse 的 prog（`--help` / 参数报错里的「程序名」）。
    # 内联前它是 `tools/xxx.py`；内联后若不还原，就会变成没头没尾的
    # `<内置工具>`。两种调用方式都照顾到：
    #   · 转发器 / 主程序 `--tool X …` → `<这是谁> --tool X`
    #   · 直接在进程内调用            → `<这是谁>`
    prog = Path(sys.argv[0]).name if (sys.argv and sys.argv[0]) else "<内置工具>"
    if len(sys.argv) > 2 and sys.argv[1] == "--tool":
        prog = f"{prog} --tool {sys.argv[2]}"
    sys.argv = [prog, *[str(a) for a in argv]]
    try:
        if cwd is not None:
            old_cwd = os.getcwd()
            os.chdir(str(cwd))
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = fn()
        return (0 if rc is None else int(rc)), buf.getvalue()
    except SystemExit as e:                      # sys.exit() / argparse 报错
        code = e.code
        if code is None:
            code = 0
        elif isinstance(code, str):
            buf.write(code + chr(10))
            code = 1
        return int(code), buf.getvalue()
    except Exception:                            # 工具自己炸了 —— 别连累整个程序
        buf.write(traceback.format_exc())
        return 1, buf.getvalue()
    finally:
        sys.argv = old_argv
        if old_cwd is not None:
            os.chdir(old_cwd)



def expected_slugs(version: str) -> list[str]:
    """本版本**应当有**的上游产物名（已过滤版本区间）—— 与 `expected()` 同源。"""
    return [s for s, _f in all_entries() if has_in_version(s, version)]


def volume_stats(version: str) -> dict[str, int]:
    """`{'main': n, 'howto': n, 'tail': n, 'total': n}` —— 界面/报告都用它数册。"""
    got = set(expected_slugs(version))
    main = sum(1 for s, _n, _t in MAIN if s in got)
    tail = sum(1 for s, _n, _t in TAIL if s in got)
    howto = sum(1 for s, _n, _t in HOWTO if s in got)
    return {'main': main, 'howto': howto, 'tail': tail, 'total': main + howto + tail}


def nm_cli() -> int:
    """`name_map.py` 原来的 `__main__` 块（改成函数，逻辑一字未动）。

    ★ 仍然是**唯一**的映射表自检入口：`--check` 那一路被步骤 8 / 步骤 9 各调一次。
    ★ 参数照旧从 `sys.argv[1:]` 读 —— 与其它内置工具一致，由 `_tool_run()` 接管。
    """
    argv = sys.argv[1:]
    if "--check" in argv:
        bad = selfcheck()
        if bad:
            print("!! name_map 自检发现 %d 个问题：" % len(bad))
            for b in bad:
                print("   · " + b)
            return 1
        print(f"OK  name_map 自检通过（"
              f"{len(all_entries())} 个条目，编号 {' '.join(used_numbers())}）")
        print(f"    配置来源：{VOLUMES_NOTE}")
        return 0

    # ★ 把当前生效的表导成 JSON —— 界面「导出」与手工建 volumes.json 都走这里，
    #   免得手抄 39 行出笔误。
    if "--dump" in argv:
        out = None
        for i, a in enumerate(argv):
            if a in ("--dump", "-o") and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                out = argv[i + 1]
        text = json.dumps(dump_volumes(), ensure_ascii=False, indent=2) + "\n"
        if out:
            Path(out).write_text(text, encoding="utf-8")
            print(f"已写出 {out}（{len(all_entries())} 条）")
        else:
            print(text, end="")
        return 0

    if "--versions" in argv:
        for v in KNOWN_VERSIONS:
            st = volume_stats(v)
            print(f"  {v:5s} 共 {st['total']:2d} 册"
                  f"（前置 {st['main']} + 指南 {st['howto']} + 尾部 {st['tail']}）")
        return 0

    v = next((a for a in argv if not a.startswith("-")), "3.14")
    st = volume_stats(v)
    print(f"版本 {v}")
    print(f"  应有册子 {len(expected(v))} 个"
          f"（前置 {st['main']} + 指南 {st['howto']} + 尾部 {st['tail']}）")
    print(f"  本版本没有 {len(unproduced(v))} 个："
          + ("、".join(f for _s, f in unproduced(v)) or "（无）"))
    print(f"  已用编号 {' '.join(used_numbers(v))}")
    print(f"  空号     {' '.join(spare_numbers(v)) or '（无）'}")
    return 0


# ---------------------------------------------------------------------------
# 内置工具：volumes（各版本册数 / 对着官方 conf.py 复核）
#   入口：vols_cli
# ---------------------------------------------------------------------------
# """册数从哪来 —— 别猜，直接问上游。
#
# CPython 每册 PDF 都由 `Doc/conf.py` 的 `latex_documents` 决定，howto 那一批是
# 目录里 `Doc/howto/*.rst` 的个数（conf.py 里用 `os.listdir('howto')` 现数）。
# 所以「某版本有几册」= 静态条目数 + howto 的 .rst 数（去掉 index.rst）。
#
# 实测（2026-11-03，`--verify` 全绿）：
#     3.10 → 10 + 17 = 27     3.13 → 10 + 27 = 37
#     3.11 →  9 + 20 = 29     3.14 → 10 + 28 = 38
#     3.12 →  9 + 23 = 32     3.15 → 10 + 29 = 39
#
# 用法：
#     --tool volumes                      各版本应有册数（离线）
#     --tool volumes --verify             联网核对（缺/多都会列出来）
#     --tool volumes --verify --versions 3.10,3.12
# """

def _http_text(url: str, timeout: int = 30, tries: int = 3) -> str:
    """GET 一个文本资源，失败重试。

    ★ 重试不是洁癖：连续打 raw.githubusercontent.com 时实测会出现
      `Remote end closed connection without response`（连接被中途掐掉），
      同一秒重发就好了。七次请求里撞过四次，不加就会误报「配置和官方不一致」。
    """
    import urllib.request
    last: Exception | None = None
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "python-doc-pdf-zh-volumes/1.0",
                "Accept": "application/vnd.github+json",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:                      # noqa: BLE001
            last = e
            if n + 1 < tries:
                time.sleep(1.5 * (n + 1))
    raise RuntimeError(f"{last}")


def _latex_slug_block(conf: str) -> str:
    """截出 `latex_documents = [ ... ]` 那一段（3.12 起 ruff 会把它排成多行）。"""
    m = re.search(r"^latex_documents\s*=\s*\[", conf, re.M)
    if not m:
        return ""
    i = conf.index("[", m.start())
    depth, j = 0, i
    while j < len(conf):
        if conf[j] == "[":
            depth += 1
        elif conf[j] == "]":
            depth -= 1
            if depth == 0:
                return conf[i:j + 1]
        j += 1
    return conf[i:]


def _howto_from_index(text: str) -> list[str]:
    """从 `Doc/howto/index.rst` 的 toctree 里抠 slug（API 限流时的退路）。

    toctree 条目就是「缩进 + 纯 slug」的行；`:doc:` 交叉引用不算。
    ★ 只是**近似**：conf.py 用 `os.listdir('howto')` 数目录里所有 `.rst`，
      index.rst 可能少列几篇（例如 `clinic.rst`）。所以这条退路只用来提示，
      不参与「算不算差异」的判定。
    """
    out: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^\s{2,}([a-z0-9][a-z0-9_\-]*)\s*$", line)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return sorted(out)


def official_volumes(branch: str) -> dict:
    """官方某分支的册子清单 → `{'main': [...], 'howto': [...], 'approx': bool}`。

    ★ 静态册看 `Doc/conf.py` 的 `latex_documents`（raw 接口，不限流）；
      指南看 `Doc/howto/*.rst` 的文件数。后者官方用的是 GitHub contents API，
      **匿名额只有 60 次/小时**（CI runner 共享 IP，很容易打满），
      403 时退回 `index.rst` 的 toctree 做近似核对，并置 `approx=True` ——
      这样限流不会再被误报成「配置和官方不一致」。
    """
    conf = _http_text(f"https://raw.githubusercontent.com/python/cpython/{branch}/Doc/conf.py")
    block = _latex_slug_block(conf)
    if not block:
        raise ValueError("conf.py 里找不到 latex_documents")
    main: list[str] = []
    for m in re.finditer(r"['\"]([A-Za-z0-9_\-]+)/index['\"]", block):
        if m.group(1) not in main:
            main.append(m.group(1))
    if re.search(r"['\"]whatsnew/['\"]\s*\+", block):
        main.append("whatsnew")

    approx = False
    try:
        listing = json.loads(_http_text(
            f"https://api.github.com/repos/python/cpython/contents/Doc/howto?ref={branch}"))
        if isinstance(listing, dict):     # 出错时是 {"message": ...}
            raise ValueError(str(listing.get("message")))
        howto = sorted(x["name"][:-4] for x in listing
                       if x.get("name", "").endswith(".rst") and x["name"] != "index.rst")
    except Exception as e:                # noqa: BLE001 —— 限流/网络抖动都走退路
        print(f"        · GitHub API 不可用（{e}）→ 改用 Doc/howto/index.rst 近似核对")
        idx = _http_text(
            f"https://raw.githubusercontent.com/python/cpython/{branch}/Doc/howto/index.rst")
        howto = _howto_from_index(idx)
        if not howto:
            raise ValueError("API 限流，且 index.rst 里也解析不出 toctree 条目") from e
        approx = True
    return {"main": main, "howto": ["howto-" + h for h in howto], "approx": approx}


def vols_cli() -> int:
    argv = sys.argv[1:]
    vers = list(KNOWN_VERSIONS)
    for i, a in enumerate(argv):
        if a == "--versions" and i + 1 < len(argv):
            vers = [x.strip() for x in argv[i + 1].split(",") if x.strip()]
    print(f"配置来源：{VOLUMES_NOTE}")
    if "--verify" not in argv:
        for v in vers:
            st = volume_stats(v)
            print(f"  {v:5s} 共 {st['total']:2d} 册"
                  f"（前置 {st['main']} + 指南 {st['howto']} + 尾部 {st['tail']}）")
        print("\n（加 --verify 联网对着 github.com/python/cpython 复核）")
        return 0

    bad = 0
    for v in vers:
        branch = BRANCH_ALIAS.get(v, v)
        try:
            off = official_volumes(branch)
        except Exception as e:                      # noqa: BLE001 —— 网络/限流都算
            print(f"  {v:5s} !! 取不到官方数据（分支 {branch}）：{e}")
            bad = 2
            continue
        want = off["main"] + off["howto"]
        have = expected_slugs(v)
        miss = [s for s in want if s not in have]        # 官方有、本地没登记
        extra = [s for s in have if s not in want]       # 本地登记了、官方没有
        approx = bool(off.get("approx"))
        # ★ 近似核对（API 限流时）只打印一行摘要、不列差异、不算失败：
        #   index.rst 的 toctree 与 `os.listdir` 的口径本来就不一样（会少列几篇），
        #   拿它当判据只会刷出几十行假差异。
        mark = "OK" if (not (miss or extra) or approx) else "!!"
        print(f"  {v:5s} {mark} 官方 {len(want):2d} 册 / 本地 {len(have):2d} 册"
              + (f"（分支 {branch}）" if branch != v else "")
              + ("（近似，不作判据）" if approx else ""))
        if approx:
            print("        · GitHub API 额度用完了（匿名 60 次/小时）；"
                  "精确核对请等额度恢复，或到 CI 上跑（runner 有自己的额度）")
        else:
            if miss:
                bad = 1
                print(f"        官方有但本地没登记 {len(miss)} 个：{'、'.join(miss)}")
                print(f"        → 在 volumes.json 里补这些条目（name 里的 {{V}} 会换成版本号）")
            if extra:
                bad = 1
                print(f"        本地登记了但官方没有 {len(extra)} 个：{'、'.join(extra)}")
                print(f"        → 给它们加 min/max 版本区间，或删掉")
    print("\n" + ("全部与官方一致。" if bad == 0 else "有差异，见上。"))
    return 0 if bad == 0 else (1 if bad == 1 else 2)


# ---------------------------------------------------------------------------
# 内置工具：titles（官方文档站标题 → 完整版本号口径）
#   入口：titles_cli
# ---------------------------------------------------------------------------
# """完整版本号从哪来 —— 看官方文档站的标题，而不是「这台机器上的解释器」。
#
# 每个版本首页的 h1 就是「Python <完整版本> 文档」：
#     https://docs.python.org/zh-cn/3.10/  →  Python 3.10.22 文档
#     https://docs.python.org/zh-cn/3.15/  →  Python 3.15.2 文档
# 抓下来存进 `sphinx-pdf/version-titles.json`，`resolve_full_version()` 优先用它。
# ★ 为什么必须这样：CI 的 `setup-python` 只保证「3.13 某个补丁版」，不一定等于文档站
#   的 3.13.18。命名跟着解释器走，就会「内容是新分支、文件名是老补丁版」；
#   而用户对照的就是文档站标题那个号。
#
# 用法：
#     --tool titles                     抓六个版本，打印并与缓存比对（不写文件）
#     --tool titles --write             同上，并把结果写进 version-titles.json
#     --tool titles --versions 3.10,3.15
# """

DOCS_ZH_BASE = "https://docs.python.org/zh-cn/{v}/"


def fetch_official_title(v: str) -> tuple[str, str]:
    """抓官方该版本首页 → `('Python 3.10.22 文档', '3.10.22')`。

    两套模板都要认：3.13 及更早是 `<h1>Python 3.10.22 文档</h1>`；
    3.14 起换了主题，`<h1>` 里可能带额外的 `<span>`（先剥标签再匹配）。
    `<title>` 作为兜底：3.10~3.13 写作 `3.10.22 Documentation`（没有 Python 前缀）。
    """
    from html import unescape
    page = _http_text(DOCS_ZH_BASE.format(v=v))
    cands: list[str] = []
    for pat in (r"<h1[^>]*>(.*?)</h1>", r"<title[^>]*>(.*?)</title>"):
        m = re.search(pat, page, re.S)
        if m:
            cands.append(unescape(re.sub(r"<[^>]+>", " ", m.group(1))))
    for text in cands:
        text = " ".join(text.split())
        for pat in (r"Python\s+(\d+\.\d+\.\d+)\s*文档",
                    r"Python\s+(\d+\.\d+\.\d+)\s+documentation",
                    r"\b(\d+\.\d+\.\d+)\b"):
            m = re.search(pat, text, re.I)
            if m:
                return text, m.group(1)
    raise ValueError("标题里找不到完整版本号")


def titles_cli() -> int:
    argv = sys.argv[1:]
    vers = list(KNOWN_VERSIONS)
    for i, a in enumerate(argv):
        if a == "--versions" and i + 1 < len(argv):
            vers = [x.strip() for x in argv[i + 1].split(",") if x.strip()]
    write = "--write" in argv
    cached = official_titles(refresh=True)
    existing = next((p for p in version_titles_candidates() if p.is_file()), None)
    target = default_volumes_json_path().with_name(VERSION_TITLES_FILENAME)
    print(f"缓存文件：{existing or target}"
          + ("" if existing else "（还没有，--write 会写到这里）"))
    print(f"{'版本':6s} {'官方标题':26s} {'官方完整版':11s} 缓存/结果")
    bad = 0
    titles: dict[str, dict[str, str]] = {}
    for v in vers:
        try:
            text, full = fetch_official_title(v)
        except Exception as e:                      # noqa: BLE001 —— 网络抖动都算
            print(f"{v:6s} !! 取不到：{e}")
            bad = 2
            continue
        old = (cached.get(v) or {}).get('full') or ''
        if not full.startswith(v + "."):
            mark = f"!! 版本对不上（应为 {v}.x）"
            bad = 1
        elif old == full:
            mark = "= 缓存一致"
        elif not old:
            mark = "+ 缓存里没有"
        else:
            mark = f"! 缓存是 {old} → 需更新"
            bad = max(bad, 1) if not write else bad
        titles[v] = {'full': full, 'title': text}
        print(f"{v:6s} {text:26s} {full:11s} {mark}")

    if write and titles:
        p = default_volumes_json_path().with_name(VERSION_TITLES_FILENAME)
        # ★ 合并写回，不是覆盖：网络抖动时某个版本可能取不到（bad=2），
        #   若直接拿本次结果整体覆盖，那个版本就会从缓存里**消失** ——
        #   而缓存没有它时 resolve_full_version 会退回解释器，命名口径就飘了。
        merged = dict(cached)
        merged.update(titles)
        payload = {
            "schema": 1,
            "_说明": "完整版本号口径：取自官方中文文档站各版本首页 h1（如 `Python 3.10.22 文档`）。"
                     "文件名/文件夹名/Release 标题都以这里的 full 为准；由 `--tool titles --write` 生成。",
            "_来源": "https://docs.python.org/zh-cn/<版本>/",
            "titles": dict(sorted(merged.items(), key=lambda kv: _ver_key(kv[0]))),
        }
        tmp = p.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
        tmp.replace(p)
        print(f"\n已写入 {p}（本次刷新 {len(titles)} 条，缓存共 {len(merged)} 条）")
        # ★ 这里**不能**把 bad 清零：bad=2 表示「有版本没取到」，调用方必须知道
        #   这份缓存不是全刷新的；而「缓存是旧值 → 需更新」(1) 已经写进文件，才算解决。
    elif bad == 0:
        print("\n全部与缓存一致。")
    else:
        print("\n有差异：加 `--write` 更新 version-titles.json。")
    return 0 if bad == 0 else bad



#: `--tool <名字>` 的名单：名字 → (说明, 入口函数)
BUILTIN_TOOLS: dict[str, tuple[str, object]] = {
    "name-map": ("分册命名真源自检/查询（原 tools/name_map.py）", nm_cli),
    "volumes": ("各版本册数 / 对着官方 conf.py 复核", vols_cli),
    "titles": ("官方文档站标题 → 完整版本号口径（version-titles.json）", titles_cli),
    "check-doc-refs": ("Doc/ 越界引用自检（原 tools/check-doc-refs.py）", cdr_main),
    "alias-po": ("接回被搬走目录的译文（原 tools/alias-po.py）", alpo_main),
    "localize-titles": ("封面标题中文化（原 tools/localize-titles.py）", loct_main),
    "fix-index": ("修 makeindex 的 .ind（原 tools/fix-index.py）", fidx_main),
    "rename-pdf": ("分册改中文名（原 tools/rename-pdf.py）", rnpdf_main),
    "merge-pdf": ("合并成一册（原 tools/merge-pdf.py）", mgpdf_main),
    "report": ("生成验收报告（原 tools/report.py）", rpt_main),
    "check-pdf-gaps": ("查空白页（原 tools/check-pdf-gaps.py）", cpg_main),
    "fix-md-escapes": ("还原被叠坏的反斜杠（原 tools/fix-md-escapes.py）", fmd_main),
    "verify-pdf": ("批量看页数/书签（原 verify-pdf.py）", vpdf_main),
    "extra-dump": ("把内置的补充译文导出到目录", None),
    "extra-fetch": ("联网拉一次补充译文到目录", None),
    "emit-makeindex-fix": ("释放 latexmk 用的 makeindex-fix.py 转发器", None),
    "emit-shims": ("在指定目录重新生成 tools/ 下的转发器", None),
}


#: 工具名 → 转发器的文件名（`--tool emit-shims` 用；verify-pdf.py 在上一级目录）
SHIM_FILES: dict[str, str] = {
    "name-map": "name_map.py",
    "check-doc-refs": "check-doc-refs.py",
    "alias-po": "alias-po.py",
    "localize-titles": "localize-titles.py",
    "fix-index": "fix-index.py",
    "rename-pdf": "rename-pdf.py",
    "merge-pdf": "merge-pdf.py",
    "report": "report.py",
    "check-pdf-gaps": "check-pdf-gaps.py",
    "fix-md-escapes": "fix-md-escapes.py",
}

#: 转发器的正文模板。`{rel}` = 从转发器所在目录到主程序的相对路径。
SHIM_TEMPLATE = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""转发器 —— 真正的实现在 `gui/pdf_builder_multi.py` 里（2026-10-04 起内联）。

为什么还留着这个文件：
  * `build-sphinx-pdf.sh` 与手工排查照旧可以 `python tools/{fname} …`；
  * 但**不会有第二份实现** —— 下面只是把参数原样交给主程序的 `--tool {name}`，
    所以「脚本改了、主程序没跟上」这种静默分叉在这里不可能发生。

★ 本文件可以用 `python gui/pdf_builder_multi.py --tool emit-shims tools` 重新生成。
"""
import runpy
import sys
from pathlib import Path

_MAIN = (Path(__file__).resolve().parent / '{rel}').resolve()
sys.argv = [str(_MAIN), '--tool', '{name}', *sys.argv[1:]]
runpy.run_path(str(_MAIN), run_name='__main__')   # 退出码随 SystemExit 传出
'''

#: 打包成 exe 之后的转发器模板 —— 没有 .py 可 `runpy` 了，改成拉起 exe 自己。
#: `{exe}` = exe 的绝对路径（用 repr 塞进来，路径含中文也安全）。
SHIM_TEMPLATE_FROZEN = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""转发器 —— 真正的实现在 PDF构建器-多版本.exe 里（打包版）。

★ 与源码版转发器的区别：exe 里**没有**可 `runpy` 的 .py 文件，
  所以这里直接把参数交给 exe 的 `--tool {name}`。
★ 由 `PDF构建器-多版本.exe --tool emit-shims tools` 生成。
"""
import subprocess
import sys

_EXE = {exe}
# ★ 必须**显式**把 stdout/stderr 传下去：exe 是 GUI 子系统（无控制台），
#   靠继承拿不到有效句柄，子进程里 sys.stdout 会是 None ——
#   结果输出被兜进 exe 旁边的 tool-output.log，调用方（latexmk 日志）啥也看不到。
#   实测：不传 = 0 行输出；传了 = 正常回传。（sys.stdout 为 None 时传 None = 继承，也对。）
raise SystemExit(
    subprocess.call([_EXE, '--tool', '{name}', *sys.argv[1:]],
                    stdout=sys.stdout, stderr=sys.stderr))
'''


def emit_tool_shims(dest_dir: Path) -> int:
    """在 dest_dir 里为 10 个内置工具各生成一个几行的转发器。

    ★ 为什么保留这些文件：`build-sphinx-pdf.sh` 与手工排查都按文件名调它们。
      内容是**生成的**（不是手写的第二份实现），所以不存在分叉。
    ★ 两种产物：源码运行 → `runpy` 主程序 .py；打成 exe → 拉起 exe 自己。
      （后者是必须的：exe 里没有那个 .py，`runpy.run_path` 会 FileNotFoundError。）
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    frozen = bool(getattr(sys, "frozen", False))
    main_py = Path(__file__).resolve()
    exe = str(Path(sys.executable).resolve())
    n = 0
    for name, fname in SHIM_FILES.items():
        rel = os.path.relpath(main_py, dest_dir).replace(os.sep, "/")
        tpl = SHIM_TEMPLATE_FROZEN if frozen else SHIM_TEMPLATE
        (dest_dir / fname).write_text(
            tpl.format(fname=fname, name=name, rel=rel, exe=repr(exe)),
            encoding="utf-8", newline="")
        print(f"  {fname:24s} → --tool {name}")
        n += 1
    print(f"生成 {n} 个转发器到 {dest_dir}")
    return n


def run_builtin_tool(name: str, argv: list[str]) -> int:
    """`--tool <名字> [参数…]` 的实现：在进程内跑一个内置工具。

    ★ 这是 tools/ 下那些转发器唯一的落地方式 —— 它们只做
      `runpy` 本文件 + `--tool <名字>`，所以**永远不可能**与主程序分叉。
    """
    if name == "extra-dump":
        # 「导出」不是「判定」：导出几个文件都不代表失败，退出码必须 0。
        # （历史上这里直接 `return dump_i18n_extra(...)`，于是导出 2 个文件 →
        #   进程退出码 2 → 调用方会误判成工具报错。）
        dump_i18n_extra(Path(argv[0]) if argv else Path("i18n-extra"))
        return 0
    if name == "extra-fetch":
        dest = Path(argv[0]) if argv else Path("i18n-extra")
        url = argv[1] if len(argv) > 1 else ""
        prepare_i18n_extra(dest, url, echo=True)
        return 0
    if name == "emit-makeindex-fix":
        # bash 脚本的步骤 7 用它把转发器放到 latex 目录（GUI 走 _emit_makeindex_fix）。
        dest = Path(argv[0]) if argv else Path("makeindex-fix.py")
        _emit_makeindex_fix(dest)
        print(f"  已写出 {dest}")
        return 0
    if name == "emit-shims":
        emit_tool_shims(Path(argv[0]) if argv else Path("tools"))
        return 0
    ent = BUILTIN_TOOLS.get(name)
    if ent is None or ent[1] is None:
        print("!! 不认识的内置工具：" + name, file=sys.stderr)
        print("   可用：" + "、".join(sorted(BUILTIN_TOOLS)), file=sys.stderr)
        return 2
    rc, text = _tool_run(ent[1], argv)
    sys.stdout.write(text)
    return rc


def _tool_source(tool: str) -> str | None:
    """把内联工具段**原样**切出来（给 `_emit_makeindex_fix` 生成自包含脚本用）。

    ★ 唯一实现原则不变：切片来自本文件（frozen 时来自打包进 exe 的本文件**源码
      副本**，见 spec 的 datas），`--tool fix-index` 与释放出的 makeindex-fix.py
      跑的是**同一段代码**，磁盘上不出现第二份实现。
    ★ 切片必须能当独立脚本运行：该段只许 import 标准库、只许引用段内定义的名字。
      （fix-index 段只在外部用了 `CREATE_NO_WINDOW`，由释放方在文件头补上。）
    """
    p: Path | None
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        p = next((q for q in sorted(meipass.glob("pdf_builder_*.py")) if q.is_file()),
                 None) if meipass.is_dir() else None
    else:
        p = Path(__file__).resolve()
    if p is None:
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return None
    b, e = f"[TOOL-SRC:{tool}:BEGIN]", f"[TOOL-SRC:{tool}:END]"
    i, j = text.find(b), text.find(e)
    if i < 0 or j <= i:
        return None
    i = text.find("\n", i) + 1                     # 跳过 BEGIN 标记行（剩下的 ==== 不是注释）
    j = text.rfind("\n", 0, j) + 1                 # 到 END 标记行的行首为止
    return text[i:j].rstrip("\n")


def _emit_makeindex_fix(dest: Path) -> None:
    """在 latex 目录释放 makeindex-fix.py —— 给 latexmk 的 `$makeindex` 用。

    ★ 为什么必须是**文件**：latexmk 的 `-e "$makeindex = q{python makeindex-fix.py …}"`
      只能调外部命令，没法内联一段 Python。
    ★ 文件名必须是 ASCII：`-e` 的字符串 latexmk 按 UTF-8 解析，路径里带中文
      （…/Python 文档/…）会直接 `Malformed UTF-8 character (fatal)`。
      文件**内容**里可以出现中文路径 —— Python 读源码默认 UTF-8。

    ★★ 2026-10-28 起：释放**自包含脚本**，不再转发到主 exe ★★
      旧方案（exe 转发器）有两个致命伤，都在当天实测踩到：
      ① onefile exe 每次调用都要重新解压 37 MB —— 一轮 3 版本 × 37 册要解压
         上百次，又慢又吵；
      ② 致命的：makeindex-fix 由 latexmk 调起，继承到主 exe 引导层塞进环境的
         PyInstaller 内部变量（_PYI_ARCHIVE_FILE / _PYI_APPLICATION_HOME_DIR /
         _PYI_PARENT_PROCESS_LEVEL …），孙 exe 的引导层走「挂接父进程归档」启动
         路径，在该路径上嵌入解释器初始化失败 → `Fatal Python error: Failed to
         import encodings module` + 弹 **模态** 错误框
         「Failed to start embedded python interpreter!」—— 框没人点，latexmk
         就永远等在那，**整个构建卡死**（三个版本同时挂，日志 45 分钟不动的实锤）。
      fix-index 本来就是**纯标准库**实现（argparse/re/pathlib/shutil/subprocess），
      直接让 PATH 里的 python 跑切片出的源码即可：不依赖主 exe、不挑 Python 版本、
      也没有任何 PyInstaller 参与启动。逻辑仍然只有主程序里那一份（见
      `_tool_source()`），`--tool fix-index` 与本脚本同源。
    """
    src = _tool_source("fix-index")
    if src is not None:
        dest.write_text(
            "# -*- coding: utf-8 -*-\n"
            "# 本文件由 PDF 构建器自动生成（步骤 7），**不要手改**。\n"
            "# 自包含脚本：fix-index 的实现从主程序源码的 [TOOL-SRC:fix-index] 段\n"
            "# 原样切出（逻辑只有一份），由 latexmk PATH 里的 python 直接运行。\n"
            "# ★ 刻意**不转发到主 exe**，原因见主程序 `_emit_makeindex_fix()` 的说明\n"
            "#   （exe 每次重解压 37 MB；继承 _PYI_* 后引导层会启动失败并弹模态框卡死构建）。\n"
            "CREATE_NO_WINDOW = 0x08000000          # 主程序里的同名常量，这里补上\n"
            "\n"
            + src +
            '\n\nif __name__ == "__main__":\n'
            "    raise SystemExit(fidx_main())\n",
            encoding="utf-8")
        return

    # ── 兜底：切片失败（标记被误删 / 打包时没带上源码）→ 退回旧转发器 ──
    #   至少构建不挡死；症状退化为「索引页码没修好」（旧方案的静默失败模式）。
    if getattr(sys, "frozen", False):
        exe = str(Path(sys.executable).resolve())
        dest.write_text(
            "# -*- coding: utf-8 -*-\n"
            "# 本文件由 PDF 构建器自动生成（步骤 7），**不要手改**。\n"
            "# 兜底转发器（自包含脚本生成失败时才用，正常不应该出现）。\n"
            "import subprocess\n"
            "import sys\n"
            "\n"
            f"_EXE = {exe!r}\n"
            "\n"
            "# ★ 必须**显式**把 stdout/stderr 传下去：exe 是 GUI 子系统（无控制台），\n"
            "#   靠继承拿不到有效句柄 → 子进程里 sys.stdout 是 None → 输出被兜进\n"
            "#   exe 旁边的 tool-output.log，latexmk 日志里啥也看不到（实测 0 行）。\n"
            "raise SystemExit(\n"
            '    subprocess.call([_EXE, "--tool", "fix-index", *sys.argv[1:]],\n'
            "                    stdout=sys.stdout, stderr=sys.stderr))\n",
            encoding="utf-8")
        return

    main_py = Path(__file__).resolve()
    dest.write_text(
        "# -*- coding: utf-8 -*-\n"
        "# 本文件由 pdf_builder_multi.py 自动生成（步骤 7），**不要手改**。\n"
        "# 兜底转发器（自包含脚本生成失败时才用，正常不应该出现）。\n"
        "import runpy\n"
        "import sys\n"
        "\n"
        f"_MAIN = {str(main_py)!r}\n"
        "\n"
        'sys.argv = [_MAIN, "--tool", "fix-index", *sys.argv[1:]]\n'
        'runpy.run_path(_MAIN, run_name="__main__")   # 退出码随 SystemExit 传出\n',
        encoding="utf-8")


# ---------------------------------------------------------------------------
# 补充译文（原 sphinx-pdf/i18n-extra/ 下的 .po）
# ---------------------------------------------------------------------------
# ★★ 2026-10-31 改：**程序里不再内置正文译文** ★★
#   以前这里塞了两段「上游没译、我们自己补」的正文（builtins/index.po、
#   builtins/time-complexity.po）。现在上游 python-docs-zh-cn 已经把这两页译了
#   （3.15 分支 builtins/*.po 齐全），内置副本只会**越放越旧**，还容易和上游
#   打架（msgid 一对不上就整段失效，且没人看得出来）。
#   现在的口径：
#     · 正文译文 → 一律来自上游 .po：步骤 2 每次 clone / fetch 到最新，
#       步骤 3 铺进 Doc/locales —— 这就是「实时抓取、确保最新」；
#     · 程序内置 → 只有**标题**（`TITLES` 表：封面标题 / 书签标题，上游不提供）；
#     · 仍想给某页打补丁 → 配「补充译文地址」（`i18n_extra_url`：http(s) 清单 /
#       目录前缀 / file:// / 本机目录都认），每次运行实时抓取；也可以先用
#       `--tool extra-dump <目录>` 把这份导出来当发布源。
#   ★ 字典为空是**正常状态**，不是没配好。

I18N_EXTRA: dict[str, str] = {}



def dump_i18n_extra(dest: Path) -> int:
    """把（程序内置的）补充译文写到目录（`--tool extra-dump <目录>`）。

    ★ 2026-10-31 起程序**不再内置正文译文**（正文一律来自上游 python-docs-zh-cn
      的 .po），所以正常情况下这里是 0 个文件 —— 这不是错误，只是没有可导出的补丁。
      想发布一份补丁源：自己建目录放 .po，再把地址填进「补充译文地址」。
    """
    n = 0
    for rel, text in sorted(I18N_EXTRA.items()):
        p = Path(dest) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="")
        print(f"  {rel}  ({len(text)} 字符) → {p}")
        n += 1
    if n == 0:
        print("程序里没有内置正文译文（正文用上游 python-docs-zh-cn 的 .po），"
              "没有可导出的内容")
    else:
        print(f"导出 {n} 个补充译文到 {dest}")
    return n


def _fetch_i18n_extra(url: str) -> dict[str, str]:
    """拉一次最新的补充译文，返回 `{相对路径: 文本}`；拿不到则返回 `{}`。

    ★ 三种源都认（「每次运行单独取一份」全靠这里）：
        * `http(s)://…` 且以 `.json` 结尾 → 清单文件
          `{"builtins/index.po": "<文本>", …}`
        * `http(s)://…` 其它          → 当目录前缀，按内置那份的相对路径逐个 GET
        * `file://…` / **本机目录路径** → 直接从该目录读同名相对路径的文件
          （没有远端服务器、只想「每次运行都从程序外那份单独取」时用它）
    ★ 拿不到的项**不出现在结果里** → 调用方回退内置版，所以断网也能跑。
    ★ http 超时给得短（每个 10 秒）：这一步不该拖慢一次十几分钟的构建。
    """
    import json
    import urllib.parse
    import urllib.request

    def get(u: str) -> bytes | None:
        try:
            with urllib.request.urlopen(u, timeout=10) as r:
                return r.read()
        except Exception as e:                    # noqa: BLE001
            print(f"      [警告] 取 {u} 失败：{e}", file=sys.stderr)
            return None

    raw_url = (url or "").strip()
    if not raw_url:
        return {}

    # ---- 本机目录 / file:// -------------------------------- 先判断，省得把
    #      Windows 路径当 URL 去 urlopen（那样必然失败）。
    local: Path | None = None
    low = raw_url.lower()
    if low.startswith("file://"):
        p = urllib.parse.urlparse(raw_url)
        # netloc 里放盘符（file:///C:/… → path=/C:/…）；统一走 url2pathname
        local = Path(urllib.request.url2pathname(p.path))
    elif "://" not in raw_url:
        local = Path(raw_url)
    if local is not None:
        if local.is_file() and local.suffix.lower() == ".json":
            try:
                obj = json.loads(local.read_text(encoding="utf-8"))
                return {str(k): str(v) for k, v in obj.items()}
            except Exception as e:                # noqa: BLE001
                print(f"      [警告] 清单不是合法 JSON：{e}", file=sys.stderr)
                return {}
        if local.is_dir():
            out: dict[str, str] = {}
            for rel in I18N_EXTRA:
                f = local / rel
                if f.is_file():
                    out[rel] = f.read_text(encoding="utf-8", errors="replace")
            return out
        print(f"      [警告] 本机源不存在：{local}", file=sys.stderr)
        return {}

    # ---- http(s) ------------------------------------------
    if raw_url.lower().endswith(".json"):
        raw = get(raw_url)
        if raw:
            try:
                obj = json.loads(raw.decode("utf-8"))
                return {str(k): str(v) for k, v in obj.items()}
            except Exception as e:                # noqa: BLE001
                print(f"      [警告] 清单不是合法 JSON：{e}", file=sys.stderr)
        return {}

    got: dict[str, str] = {}
    for rel in I18N_EXTRA:
        raw = get(raw_url.rstrip("/") + "/" + rel)
        if raw is not None:
            got[rel] = raw.decode("utf-8", "replace")
    return got


def prepare_i18n_extra(dest: Path, url: str = "", echo: bool = False) -> int:
    """把补充译文铺到 `dest`，返回**实际写出的文件数**。

    ★ 顺序：先取外部源（url 非空时）→ 再逐项写盘，**外部拿到的优先、其余用内置**。
      于是「配了地址」= 每次都跟上最新的；「没配」= 什么都不写（正常状态）。
    ★ 每次都**整份重写**（不是「有就跳过」）：否则上一轮联网拿到的旧文件会在
      本轮断网时被当成新鲜数据 —— 「每次运行单独下载」就名不副实了。
    """
    url = (url or "").strip()
    if not I18N_EXTRA and not url:
        return 0                                  # 没有内置、也没配地址 → 什么都不做
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    got = _fetch_i18n_extra(url) if url else {}

    n = 0
    for rel, emb_text in sorted(I18N_EXTRA.items()):
        text = got.get(rel, emb_text)             # 外部优先，否则内置
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="")
        n += 1
    # 外部源比内置多出来的（内置里没有的路径）也一并写出
    for rel, text in sorted(got.items()):
        if rel in I18N_EXTRA:
            continue
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="")
        n += 1

    if echo:
        print(f"  外部源更新 {len(got)} 项，共写出 {n} 个文件 → {dest}")
    return n

# =============================================================================

# 七、PyQt6 图形界面
# =============================================================================

from html import escape as _esc                                   # noqa: E402

#: PyQt6 缺失时的原因；None = 界面可用。--cli / --check 不依赖它。
QT_ERROR: str | None = None

try:
    from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal       # noqa: E402
    from PyQt6.QtGui import QColor, QFont                          # noqa: E402
    from PyQt6.QtWidgets import (                                  # noqa: E402
        QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
        QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
        QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
        QScrollArea, QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem,
        QToolButton, QVBoxLayout, QWidget,
    )
except ImportError as _e:                                         # pragma: no cover
    # ★ 这里**不能**直接 SystemExit：--cli / --check 是无头路径，只跑 Pipeline，
    #   跟 Qt 一点关系没有（ConsoleReporter 的注释也把 --cli 当冒烟测试用）。
    #   所以缺 PyQt6 时给一整套同名占位名，让下面的界面类仍能被定义出来
    #   （类体里只用到 pyqtSignal；类型注解因为 from __future__ import annotations
    #    是字符串，不会真去求值），只是谁也用不了它们。
    QT_ERROR = str(_e)

    class _MissingQt:
        """PyQt6 缺失时所有 Qt 类的替身；一被实例化就报缺依赖。"""

        def __init__(self, *a, **k):
            raise SystemExit(
                f"缺少图形界面依赖：{QT_ERROR}\n"
                f"请先安装：pip install PyQt6 pypdf\n"
                f"或直接双击 启动PDF构建器.bat（它会自动建 venv 并装好）。")

    Qt = QThread = QTimer = QColor = QFont = _MissingQt
    QApplication = QCheckBox = QComboBox = QDialog = QFileDialog = _MissingQt
    QFrame = QGridLayout = QGroupBox = QHBoxLayout = QHeaderView = _MissingQt
    QLabel = QLineEdit = QMainWindow = QMessageBox = QPlainTextEdit = _MissingQt
    QProgressBar = QPushButton = QScrollArea = QSizePolicy = _MissingQt
    QSplitter = QTableWidget = QTableWidgetItem = QToolButton = _MissingQt
    QVBoxLayout = QWidget = _MissingQt

    def pyqtSignal(*_a, **_k):                                    # noqa: D103
        return None

#: 日志级别 → 颜色（浅色主题：浅底深字）
LEVEL_COLOR = {
    "info": "#24292f",
    "step": "#2f6feb",
    "ok":   "#1a7f37",
    "warn": "#9a6700",
    "err":  "#cf222e",
    "meta": "#6e7781",
    "cmd":  "#8250df",
    "raw":  "#57606a",
}

#: 状态列文字 → 颜色
STATE_COLOR = {
    "待执行": "#6e7781",
    "执行中": "#2f6feb",
    "完成":   "#1a7f37",
    "失败":   "#cf222e",
    "已跳过": "#9a6700",
}

QSS = """
QWidget            { background:#f6f7f9; color:#1f2328;
                     font-family:"Microsoft YaHei UI","Segoe UI",sans-serif; font-size:9.5pt; }
QGroupBox          { background:#ffffff; border:1px solid #d8dce3; border-radius:8px;
                     margin-top:14px; padding:12px 10px 8px 10px; font-weight:600; }
QGroupBox::title   { subcontrol-origin:margin; left:12px; padding:0 6px; color:#2f6feb; }
QLineEdit, QComboBox { background:#ffffff; border:1px solid #cfd6df; border-radius:6px;
                     padding:5px 8px; }
QLineEdit:focus, QComboBox:focus { border:1px solid #2f6feb; }
QLineEdit:disabled, QComboBox:disabled { background:#f1f3f6; color:#8c959f; }
QPushButton        { background:#ffffff; border:1px solid #cfd6df; border-radius:6px;
                     padding:6px 14px; }
QPushButton:hover  { background:#eef3fd; border-color:#2f6feb; }
QPushButton:disabled { color:#8c959f; background:#f1f3f6; border-color:#e2e6ea; }
QPushButton#primary{ background:#2f6feb; color:#ffffff; border:none; font-weight:600;
                     padding:9px 26px; }
QPushButton#primary:hover { background:#1f5fd8; }
QPushButton#primary:disabled { background:#a9c2f4; }
QPushButton#danger { color:#cf222e; border-color:#f0b4b8; }
QPushButton#danger:hover { background:#fff1f2; border-color:#cf222e; }
QTableWidget       { background:#ffffff; border:1px solid #d8dce3; border-radius:6px;
                     gridline-color:#eef0f3; }
QTableWidget::item { padding:2px 6px; }
QHeaderView::section { background:#f1f3f6; border:none; border-bottom:1px solid #d8dce3;
                     padding:6px; font-weight:600; color:#57606a; }
QPlainTextEdit     { background:#ffffff; border:1px solid #d8dce3; border-radius:6px;
                     font-family:Consolas,"Cascadia Mono","Sarasa Mono SC",monospace;
                     font-size:9pt; }
QProgressBar       { border:1px solid #d8dce3; border-radius:6px; background:#ffffff;
                     text-align:center; color:#24292f; min-height:17px; }
QProgressBar::chunk{ background:#2f6feb; border-radius:5px; }
QLabel#h1          { font-size:14pt; font-weight:700; color:#1f2328; }
QLabel#hint        { color:#6e7781; }
QLabel#state       { font-weight:600; }
QFrame#card        { background:#ffffff; border:1px solid #d8dce3; border-radius:8px; }
QToolButton#sect   { text-align:left; font-weight:600; color:#1f2328; padding:5px 6px;
                     border:none; border-top:1px solid #e4e7eb; background:transparent; }
QToolButton#sect:hover { background:#f4f6f9; color:#2f6feb; }
"""


# ---------------------------------------------------------------------------
# 6.1 工作线程：把 Pipeline 跑在后台，通过信号把进度送回界面
# ---------------------------------------------------------------------------

class BuildWorker(QThread):
    """工作线程。

    它同时是 Pipeline 的 reporter —— Pipeline 只认 log/step_begin/step_end/
    sub/check_cancel 这几个方法，换成 Qt 或控制台实现都能跑。
    """

    sig_step_begin = pyqtSignal(int, str)
    sig_step_end = pyqtSignal(int, bool, str, float)
    sig_sub = pyqtSignal(int, int, int, str)
    sig_log = pyqtSignal(str, str)          # (level, text)
    sig_done = pyqtSignal(bool, str)

    def __init__(self, cfg: Config, steps: list[int], parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.steps = steps
        self._cancel = False
        self._pipe: Pipeline | None = None
        self._buf: list[tuple[str, str]] = []
        self._last = 0.0

    # ------------------------------------------------------------ 外部控制
    def stop(self) -> None:
        self._cancel = True
        cands: list[subprocess.Popen] = []
        if self._pipe:
            if self._pipe._proc is not None:
                cands.append(self._pipe._proc)
            # ★ 步骤 7 并发时会同时有好几个 latexmk 在跑，必须全杀 ——
            #   只杀 _proc 会留下孤儿 xelatex 继续占满 CPU。
            cands.extend(list(self._pipe._procs))
        alive = [p for p in cands if p.poll() is None]
        if alive:
            self.log(f"正在结束 {len(alive)} 个命令…" if len(alive) > 1 else "正在结束当前命令…",
                     "warn")
            self._flush()
            for p in alive:
                kill_tree(p.pid)

    # ------------------------------------------------------- Reporter 协议
    def log(self, text: str, level: str = "info") -> None:
        self._buf.append((level, text))
        now = time.monotonic()
        if len(self._buf) >= 30 or level in ("step", "err", "ok", "warn") \
                or (now - self._last) > 0.1:
            self._flush()

    def _flush(self) -> None:
        """把缓冲按级别合并后一次性发信号（latexmk 输出动辄几万行，不合并会卡）。"""
        if not self._buf:
            return
        buf, self._buf = self._buf, []
        lv, chunk = buf[0][0], [buf[0][1]]
        for l, t in buf[1:]:
            if l == lv:
                chunk.append(t)
            else:
                self.sig_log.emit(lv, "\n".join(chunk))
                lv, chunk = l, [t]
        self.sig_log.emit(lv, "\n".join(chunk))
        self._last = time.monotonic()

    def step_begin(self, i: int, title: str) -> None:
        self._flush()
        self.sig_step_begin.emit(i, title)

    def step_end(self, i: int, ok: bool, summary: str, secs: float) -> None:
        self._flush()
        self.sig_step_end.emit(i, ok, summary, secs)

    def sub(self, i: int, done: int, total: int, label: str = "") -> None:
        self.sig_sub.emit(i, done, total, label)

    def check_cancel(self) -> None:
        if self._cancel:
            raise Cancelled()

    # ---------------------------------------------------------------- body
    def run(self) -> None:
        ok, msg = True, ""
        try:
            self._pipe = Pipeline(self.cfg, self)
            ok, msg = self._pipe.main(self.steps)
        except Cancelled:
            ok, msg = False, "已手动停止"
        except Fail as e:
            ok, msg = False, str(e)
        except Exception as e:                                  # noqa: BLE001
            import traceback
            self.log(traceback.format_exc(), "err")
            ok, msg = False, f"{type(e).__name__}: {e}"
        finally:
            self._flush()
            if self._pipe:
                self._pipe._close_logs()
        self.sig_done.emit(ok, msg)


# ---------------------------------------------------------------------------
# 6.2 配置面板：所有"可改的链接和路径"都在这里
# ---------------------------------------------------------------------------

class CollapsibleBox(QWidget):
    """可折叠分组：点标题栏收起/展开。

    左侧原来一屏放了 20 多个字段，太挤。现在按「必改 / 偶尔改 / 基本不用动」
    分成几块，只有常用的两块默认展开。
    """

    def __init__(self, title: str, opened: bool = True, hint: str = "",
                 parent=None) -> None:
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.btn = QToolButton()
        self.btn.setObjectName("sect")
        self.btn.setText(title)
        self.btn.setCheckable(True)
        self.btn.setChecked(opened)
        self.btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn.setArrowType(Qt.ArrowType.DownArrow if opened
                              else Qt.ArrowType.RightArrow)
        self.btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if hint:
            self.btn.setToolTip(hint)
        self.btn.clicked.connect(self._toggle)
        v.addWidget(self.btn)

        self.body = QWidget()
        self.lay = QVBoxLayout(self.body)
        self.lay.setContentsMargins(12, 4, 10, 10)
        self.lay.setSpacing(6)
        self.body.setVisible(opened)
        v.addWidget(self.body)

    def _toggle(self) -> None:
        on = self.btn.isChecked()
        self.body.setVisible(on)
        self.btn.setArrowType(Qt.ArrowType.DownArrow if on
                              else Qt.ArrowType.RightArrow)

    def add(self, w) -> None:
        self.lay.addWidget(w)


class SettingsPanel(QWidget):
    """左侧配置区。每个字段都直接对应 Config 的一个属性。

    只保留 4 块内容，按改动频率排序：
        ① 版本与目录       —— 必改（选 3.13/3.14/3.15 + 目录）
        ② 下载源           —— 默认联网克隆，代理不通时才需要改（折叠）
        ③ 本地环境         —— 自动探测，装了两套 TeX Live 之类才需要改（折叠）
        ④ 运行参数与开关   —— 语言默认中文，一般不用动
    """

    #: (key, 标签, 提示, 类型) —— ① 版本与目录
    FIELDS_MAIN = [
        ("base_dir", "基准目录", "默认路径的基准：构建根目录 = <基准>/Python <完整版本> PDF 文档 <日期>",
         "dir", ""),
        ("date_tag", "日期标签", "写进文件夹名与合并册名，形如 20261017；留空 = 今天。\n"
                                 "续跑同一轮构建时**保持不变**（改了就等于换文件夹，要重新克隆）",
         "text", "留空 = 今天（如 20261017）"),
        ("root", "构建根目录", "源码 + 全部中间产物都放这里；留空 = 按上面的基准目录＋版本＋日期自动生成",
         "dir", ""),
        ("outdir", "PDF 输出目录", "最终中文名 PDF 落地目录；留空 = 与构建根目录相同",
         "dir", ""),
    ]
    #: ② 下载源
    FIELDS_SRC = [
        ("gh", "GitHub 代理前缀",
         "★ 留空 = 自动依次尝试内置镜像（失败自动换下一个，日志里会写用的是哪个）：\n"
         + "\n".join(f"    {i}. {n:<13}{t.format(repo='python/cpython.git')}"
                     for i, (n, t) in enumerate(GH_MIRRORS, 1))
         + "\n填了就先用它，失败仍会自动回退。",
         "text", "留空 = 自动（推荐）"),
        ("cpython_url", "CPython 仓库地址", "留空 = 自动（用上面挑中的镜像拼 /python/cpython.git）",
         "text", "留空 = 自动"),
        ("zh_url", "翻译仓库地址", "留空 = 自动（/python/python-docs-zh-cn.git）",
         "text", "留空 = 自动"),
        ("zh_src", "本地翻译源目录", "★ 留空 = 联网克隆（推荐）。填了就用本地那份，不再联网",
         "dir", "留空 = 联网下载 python-docs-zh-cn"),
        ("version_branch", "分支覆盖", "留空 = 直接用版本号（3.14 → 分支 3.14）",
         "text", "留空 = 用版本号"),
        ("pip_index", "pip 源", "国内建议清华源", "text", ""),
        ("i18n_extra_url", "补充译文地址",
         "★ 程序**不再内置正文译文**：正文一律用上游 python-docs-zh-cn 的 .po"
         "（步骤 2 每次都取最新），内置只有标题表。\n"
         "这一行是「额外打补丁」用的，留空即可：http(s) 地址（.json 结尾当清单文件，"
         "否则当目录前缀逐文件取）、file:// 或本机目录路径都支持。",
         "text", "留空 = 不打补丁（正文用上游最新译文）"),
    ]
    #: ③ 本地环境
    #: ★ 这里**刻意没有** `python` 一行（单版本版有）。多版本版里解释器是
    #:   「每个版本一份」的，权威输入在 ① 的那三行；再放一个全局解释器会：
    #:     ① 表达不了「三个版本各用各的」；
    #:     ② 编辑它**没有任何效果**（collect() 里 `cfg.python` 被 ① 覆盖）；
    #:     ③ 误导 —— 界面显示 3.13.12，而勾了 3.15 时实际用的是 Python315。
    #:   `Config.python` 仍然保留（CLI / 旧配置 / ① 留空时的兜底都用它），
    #:   只是不再单独占一行。
    FIELDS_ENV = [
        ("texlive_bin", "TeX Live bin", "xelatex / latexmk / makeindex 所在目录", "dir", ""),
        ("venv", "构建 venv", "装了 sphinx 的虚拟环境；留空 = 自动探测", "dir", "留空 = 自动探测"),
        ("tools_dir", "工具目录", "固定脚本所在目录（留空 = <gui>/../tools）", "dir", ""),
    ]

    def __init__(self, cfg: Config, parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.edits: dict[str, QLineEdit] = {}
        self.checks: dict[str, QCheckBox] = {}
        self.cmb_lang: QComboBox | None = None
        #: 版本多选：版本号 → 勾选框 / 解释器输入框 / 「→ 3.13.16」提示
        self.chk_ver: dict[str, QCheckBox] = {}
        self.ed_verpy: dict[str, QLineEdit] = {}
        self.lbl_fullver: dict[str, QLabel] = {}
        self.cmb_from: QComboBox | None = None
        self.cmb_clean: QComboBox | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)

        title = QLabel("配置")
        title.setObjectName("h1")
        lay.addWidget(title)
        hint = QLabel("默认即可直接跑：源码与翻译源都从网上下载，语言固定中文。"
                      "改动「版本」会同时决定 CPython 和 python-docs-zh-cn 的分支。")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        # 动作按钮放在最上面，保证不用滚动就能点到
        btns = QHBoxLayout()
        self.btn_save = QPushButton("保存配置")
        self.btn_save.clicked.connect(self.on_save)
        self.btn_reset = QPushButton("恢复默认")
        self.btn_reset.clicked.connect(self.on_reset)
        self.btn_verify = QPushButton("校验路径")
        self.btn_verify.setToolTip("不跑构建，只检查解释器 / TeX Live / venv / 工具脚本")
        self.btn_verify.clicked.connect(self.on_verify)
        for b in (self.btn_save, self.btn_reset, self.btn_verify):
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)

        # ── ① 版本与目录 ──────────────────────────────────────────────────
        g1 = CollapsibleBox("① 版本与目录", opened=True,
                            hint="勾几个跑几个（≥2 个 = 多进程并行）；"
                                 "每个版本各用各的解释器，留空 = 自动探测")
        vtip = QLabel("勾 1 个：和以前一样，就在右边这个面板里跑。"
                      "勾 2 个及以上：各起一个子进程同时跑（六版全勾 = 六路并行），点「开始处理」后"
                      "会弹出多版本并行日志窗口，一个版本一个独立日志框。")
        vtip.setObjectName("hint")
        vtip.setWordWrap(True)
        g1.add(vtip)

        vh = QWidget()
        vg = QGridLayout(vh)
        vg.setContentsMargins(0, 0, 0, 0)
        vg.setHorizontalSpacing(6)
        vg.setVerticalSpacing(3)
        for r, ver in enumerate(KNOWN_VERSIONS):
            cb = QCheckBox(f"Python {ver}")
            cb.setFixedWidth(112)
            cb.toggled.connect(self._sync_defaults)
            ed = QLineEdit()
            ed.setToolTip("这个版本建 venv 用的解释器（三个分支各用各的，互不干扰）")
            ed.textChanged.connect(self._sync_defaults)
            btn = QPushButton("浏览…")
            btn.setFixedWidth(62)
            btn.clicked.connect(
                lambda _, e=ed, v=ver: self._pick_file(
                    e, f"Python {v} 解释器", "Python (python.exe)"))
            lb = QLabel("")
            lb.setObjectName("hint")
            vg.addWidget(cb, r, 0)
            vg.addWidget(ed, r, 1)
            vg.addWidget(btn, r, 2)
            vg.addWidget(lb, r, 3)
            self.chk_ver[ver] = cb
            self.ed_verpy[ver] = ed
            self.lbl_fullver[ver] = lb
        vg.setColumnStretch(1, 1)
        g1.add(vh)

        # ── 分册配置入口 ──────────────────────────────────────────────────
        # 册数随版本变（3.10 27 册 → 3.15 39 册），所以这张表必须是可改的：
        # 点这里能看到每册的编号/文件名/书签/版本区间，并直接编辑 volumes.json。
        vh2 = QWidget()
        vh2l = QHBoxLayout(vh2)
        vh2l.setContentsMargins(0, 2, 0, 0)
        vh2l.setSpacing(6)
        self.btn_volumes = QPushButton("分册配置…")
        self.btn_volumes.setFixedWidth(112)
        self.btn_volumes.setToolTip(
            "各版本的册数不一样（3.10 27 / 3.11 29 / 3.12 32 / 3.13 37 / 3.14 38 / 3.15 39）；"
            "这里可以改分册名、编号、书签标题、版本区间与合并顺序，保存到 sphinx-pdf/volumes.json")
        self.btn_volumes.clicked.connect(self.on_edit_volumes)
        self.lbl_volumes = QLabel("")
        self.lbl_volumes.setObjectName("hint")
        self.lbl_volumes.setWordWrap(True)
        vh2l.addWidget(self.btn_volumes)
        vh2l.addWidget(self.lbl_volumes, 1)
        g1.add(vh2)
        self._refresh_volume_hint()

        for key, label, tip, kind, ph in self.FIELDS_MAIN:
            g1.add(self._row_widget(key, label, tip, kind, ph))
        lay.addWidget(g1)

        # ── ② 下载源 ──────────────────────────────────────────────────────
        g2 = CollapsibleBox("② 下载源（默认联网）", opened=False,
                            hint="默认从 GitHub 实时克隆/更新；代理不通或要离线构建时才需要改")
        self.checks["download_sources"] = self._check(
            "从网站实时下载 / 更新源码与翻译源（推荐）",
            "关掉后必须自己填「本地翻译源目录」，否则步骤 2 会失败")
        self.checks["refresh_sources"] = self._check(
            "已克隆过也 fetch 到最新（步骤 1/2）",
            "每次运行都 git fetch + reset 到远端最新；断网时自动跳过，不影响构建")
        for key, label, tip, kind, ph in self.FIELDS_SRC:
            g2.add(self._row_widget(key, label, tip, kind, ph))
        lay.addWidget(g2)

        # ── ③ 本地环境 ────────────────────────────────────────────────────
        g3 = CollapsibleBox("③ 本地环境（自动探测，通常不用改）", opened=False,
                            hint="装了两套 Python / TeX Live，或 venv 不在默认位置时才需要改")
        for key, label, tip, kind, ph in self.FIELDS_ENV:
            g3.add(self._row_widget(key, label, tip, kind, ph))
        lay.addWidget(g3)

        # ── ④ 运行参数 ────────────────────────────────────────────────────
        g4 = CollapsibleBox("④ 运行参数", opened=True)
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)
        rl.addWidget(self._label("语言", "传给 sphinx -D language=…；默认中文 zh_CN"))
        self.cmb_lang = QComboBox()
        for code, name in (("zh_CN", "中文（默认）"), ("zh_TW", "繁体中文"),
                           ("ja", "日文"), ("en", "英文（正文会退回原文）")):
            self.cmb_lang.addItem(name, code)
        rl.addWidget(self.cmb_lang)
        rl.addSpacing(10)
        rl.addWidget(QLabel("并行度"))
        ed_jobs = QLineEdit()
        ed_jobs.setToolTip("并行度：sphinx -j 与步骤 7 的 latexmk 并发都用它；\n"
                           "留空或 auto = 自动（CPU 核数-1，上限 6）；填 1 = 串行")
        ed_jobs.setMaximumWidth(80)
        self.edits["jobs"] = ed_jobs
        rl.addWidget(ed_jobs)
        rl.addStretch(1)
        g4.add(row)

        row2 = QWidget()
        r2 = QHBoxLayout(row2)
        r2.setContentsMargins(0, 0, 0, 0)
        r2.setSpacing(6)
        r2.addWidget(self._label("起始步骤",
                                 "从哪一步开始跑，前面的步骤标成「已跳过」。\n"
                                 "中途失败后再跑（比如只重跑 6/6b/7/7b/8）用它。"))
        self.cmb_from = QComboBox()
        for row_i, label, ttl, _s in STEPS:
            self.cmb_from.addItem(f"{label} · {ttl}", row_i)
        r2.addWidget(self.cmb_from, 1)
        g4.add(row2)

        row3 = QWidget()
        r3 = QHBoxLayout(row3)
        r3.setContentsMargins(0, 0, 0, 0)
        r3.setSpacing(6)
        r3.addWidget(self._label("只跑这些步",
                                 "只跑指定步骤（填行号，逗号分隔）。填了这项，「起始步骤」被忽略。"))
        ed_only = QLineEdit()
        ed_only.setPlaceholderText("留空 = 从起始步骤一路跑到底；例如 0,1 或 7,8,9")
        ed_only.setToolTip("只跑指定步骤（填行号，逗号分隔）。填了这项，起始步骤就被忽略。")
        self.edits["only_steps"] = ed_only
        r3.addWidget(ed_only, 1)
        g4.add(row3)
        lay.addWidget(g4)

        # ── ⑤ 执行开关 ────────────────────────────────────────────────────
        g5 = CollapsibleBox("⑤ 执行开关", opened=False)
        grid = QWidget()
        v4 = QGridLayout(grid)
        v4.setContentsMargins(0, 0, 0, 0)
        v4.setHorizontalSpacing(12)
        v4.setVerticalSpacing(2)
        opts = [
            ("skip_clone_if_exists", "步骤 1/2：已有克隆就直接用（不重下）"),
            ("skip_pip_if_ready", "步骤 4：依赖已就绪就跳过 pip（省十几分钟）"),
            ("keep_build_dir", "步骤 4：保留已有 build/（增量，不如全量干净）"),
            ("build_html", "步骤 5：构建 HTML（只验证主题，不影响 PDF）"),
            ("localize_titles", "步骤 6b：封面标题中文化（封面＋页眉）"),
            ("fix_index", "步骤 7b：索引自检（分组标题＋页码超链接＋长条目断点）"),
            ("prune_extra_pdf", "步骤 8：丢掉 SVG 转出的插图 PDF，只留册子"),
            ("gen_report", "步骤 8：生成 验收报告.md（需要 pypdf）"),
            ("merge_pdf", "步骤 9：把 38 册合并成一册（完整书签，需 pypdf）"),
            ("verbose_log", "界面显示完整输出（会刷屏，日志文件里始终是全的）"),
            ("open_outdir_when_done", "完成后自动打开输出目录"),
        ]
        for i, (key, label) in enumerate(opts):
            cb = QCheckBox(label)
            self.checks[key] = cb
            v4.addWidget(cb, i % 5, i // 5)          # 5 行 2 列，省纵向空间
        g5.add(grid)

        # 步骤 9 的成品名 —— 留空就用「Python <版本> 文档 <今天>.pdf」
        rowm = QWidget()
        rm = QHBoxLayout(rowm)
        rm.setContentsMargins(0, 0, 0, 0)
        rm.setSpacing(6)
        rm.addWidget(self._label("合并册名", "步骤 9：合并成一册后的文件名（可带 .pdf，也可不带）。"))
        ed_merge = QLineEdit()
        ed_merge.setPlaceholderText("留空 = Python <版本> 文档 <今天>.pdf")
        ed_merge.setToolTip("步骤 9：合并成一册后的文件名。留空就自动按日期命名。")
        self.edits["merge_name"] = ed_merge
        rm.addWidget(ed_merge, 1)
        g5.add(rowm)

        # 步骤 10 的清理范围 —— 三选一，用下拉框（勾选框表达不了「删到什么程度」）
        rowc = QWidget()
        rc = QHBoxLayout(rowc)
        rc.setContentsMargins(0, 0, 0, 0)
        rc.setSpacing(6)
        rc.addWidget(self._label(
            "清理范围",
            "步骤 10：跑完（含步骤 9 合并）之后删掉哪些过程文件。\n"
            "★ 成品 PDF 永远不会被删。\n"
            "· 只删构建中间件：<根>/cpython/Doc/build\n"
            "· 全删：再加 cpython 源码 + venv + zh-cn 翻译源 + 日志\n"
            "  （下次要重新联网克隆、重装依赖，但机器上不留东西）\n"
            "· 日志正被本程序占用时删不掉，关掉程序后可手删。"))
        self.cmb_clean = QComboBox()
        for val, text in CLEAN_MODES:
            self.cmb_clean.addItem(text, val)
        rc.addWidget(self.cmb_clean, 1)
        g5.add(rowc)

        lay.addWidget(g5)
        lay.addStretch(1)

        self.load_from(cfg)

    # ------------------------------------------------------------ 行构造器
    LABEL_W = 104      # 标签固定宽度，避免字段被挤扁

    def _label(self, text: str, tip: str = "") -> QLabel:
        lb = QLabel(text)
        lb.setFixedWidth(self.LABEL_W)
        lb.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if tip:
            lb.setToolTip(tip)
        return lb

    def _check(self, text: str, tip: str = "") -> QCheckBox:
        cb = QCheckBox(text)
        if tip:
            cb.setToolTip(tip)
        return cb

    def _row_widget(self, key: str, label: str, tip: str, kind: str = "dir",
                    placeholder: str = "") -> QWidget:
        """一行 = 定宽标签 + 可伸展输入框 [+ 浏览按钮]."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        ed = QLineEdit()
        ed.setToolTip(tip)
        ed.setMinimumWidth(160)
        if placeholder:
            ed.setPlaceholderText(placeholder)
        if key in ("base_dir", "root", "date_tag"):
            ed.textChanged.connect(self._sync_defaults)
        self.edits[key] = ed
        h.addWidget(self._label(label, tip))
        h.addWidget(ed, 1)
        if kind in ("dir", "file"):
            btn = QPushButton("浏览…")
            btn.setFixedWidth(62)
            if kind == "dir":
                btn.clicked.connect(lambda _, e=ed, l=label: self._pick_dir(e, l))
            else:
                filt = ("Python (python.exe)" if key == "python" else "所有文件 (*)")
                btn.clicked.connect(
                    lambda _, e=ed, l=label, f=filt: self._pick_file(e, l, f))
            h.addWidget(btn)
        return w

    def _pick_dir(self, edit: QLineEdit, title: str) -> None:
        start = edit.text().strip() or str(Path.home())
        p = QFileDialog.getExistingDirectory(self, f"选择{title}", start)
        if p:
            edit.setText(str(Path(p)).replace("\\", "/"))

    def _pick_file(self, edit: QLineEdit, title: str, filt: str) -> None:
        start = edit.text().strip()
        if start and not Path(start).is_file():
            start = str(Path(start).parent)
        p, _ = QFileDialog.getOpenFileName(self, f"选择{title}", start or str(Path.home()), filt)
        if p:
            edit.setText(str(Path(p)).replace("\\", "/"))

    # ------------------------------------------------------------- 读写
    def _refresh_volume_hint(self) -> None:
        """版本区下面那行小字：分册表从哪来 + 每个版本几册。

        ★ 这行字是「册数随版本变」的唯一可见提示。以前勾了 3.13 却按 3.14 的表
          去改名，结果是 `MISSING 1` 而看不出原因；现在一眼能看到 3.13 是 37 册。
        """
        try:
            parts = [f"{v} {volume_stats(v)['total']}" for v in KNOWN_VERSIONS]
            src = Path(VOLUMES_LOADED).name if VOLUMES_LOADED else "内置表"
            self.lbl_volumes.setText("分册表（%s）册数：%s" % (src, " / ".join(parts)))
            self.lbl_volumes.setToolTip(VOLUMES_NOTE)
        except Exception as e:                                   # noqa: BLE001
            self.lbl_volumes.setText(f"分册表读取异常：{e}")

    def on_edit_volumes(self) -> None:
        """打开可视化分册配置（各版本册数不同，都在这个窗口里改）。"""
        dlg = VolumeEditorDialog(self)
        dlg.exec()
        self._refresh_volume_hint()

    def _checked_versions(self) -> list[str]:
        """勾选的版本（按 3.10 → 3.16）。"""
        return [v for v in KNOWN_VERSIONS
                if v in self.chk_ver and self.chk_ver[v].isChecked()]

    def _current_version(self) -> str:
        got = self._checked_versions()
        return got[0] if got else "3.14"

    def _date_txt(self) -> str:
        dt = self.edits.get("date_tag")
        return (dt.text().strip() if dt else "") or today_tag()

    def _full(self, ver: str) -> str:
        """某个版本当前会解析出的完整版本号（跟着它那一行的解释器走）。"""
        py = self.ed_verpy[ver].text().strip() if ver in self.ed_verpy else ""
        return resolve_full_version(ver, py)

    def _auto_dir(self, ver: str) -> Path:
        """某个版本「留空时」会用的构建根目录。"""
        base = self.edits.get("base_dir")
        base_txt = base.text().strip() if base else ""
        return Path(base_txt or _guess_base_dir()) / \
            f"Python {self._full(ver)} PDF 文档 {self._date_txt()}"

    def _sync_defaults(self, *_a) -> None:
        """版本勾选 / 基准目录 / 日期一改，就把「留空时用哪个目录」写进灰字。"""
        got = self._checked_versions()
        for ver in KNOWN_VERSIONS:
            lb = self.lbl_fullver.get(ver)
            if lb is None:
                continue
            lb.setText(f"→ {self._full(ver)}")
            lb.setToolTip(str(self._auto_dir(ver)))
        if len(got) >= 2:
            # ★ 多选时必须各自一个文件夹，否则三个版本会互相覆盖产物 ——
            #   所以这里直接把「构建根目录 / 输出目录」置灰，并在灰字里说清楚。
            for k in ("root", "outdir"):
                ed = self.edits.get(k)
                if ed is not None:
                    ed.setEnabled(False)
                    ed.setPlaceholderText("多选时不用填：每个版本自动用各自的文件夹")
            # ★ 合并册名同理：多选时每个版本各出一本，名字由程序按
            #   「Python <完整版本> 文档 <日期>.pdf」自动生成（手填的会被忽略），
            #   留着可编辑只会让人以为填了能生效。
            em = self.edits.get("merge_name")
            if em is not None:
                em.setEnabled(False)
                em.setPlaceholderText("多选时自动：Python <完整版本> 文档 <日期>.pdf")
            hint = "；".join(f"{v} → {self._auto_dir(v).name}" for v in got)
            for lb in self.lbl_fullver.values():
                lb.setToolTip(hint)
        else:
            dflt = str(self._auto_dir(got[0] if got else "3.14"))
            if "root" in self.edits:
                self.edits["root"].setEnabled(True)
                self.edits["root"].setPlaceholderText(f"留空 = {dflt}")
            if "outdir" in self.edits:
                self.edits["outdir"].setEnabled(True)
                self.edits["outdir"].setPlaceholderText(f"留空 = 构建根目录（{dflt}）")
            em = self.edits.get("merge_name")
            if em is not None:
                em.setEnabled(True)
                ver0 = got[0] if got else "3.14"
                em.setPlaceholderText(
                    f"留空 = Python {self._full(ver0)} 文档 {self._date_txt()}.pdf")

    def load_from(self, cfg: Config) -> None:
        d = asdict(cfg)
        for key, ed in self.edits.items():
            ed.setText(str(d.get(key, "")))
        for key, cb in self.checks.items():
            cb.setChecked(bool(d.get(key, False)))
        # 版本多选 + 每版本解释器
        vers = [str(v) for v in (d.get("versions") or [])]
        if not vers:
            vers = [str(d.get("version", "3.14"))]
        pys = d.get("version_pythons") or {}
        for ver in KNOWN_VERSIONS:
            self.chk_ver[ver].setChecked(ver in vers)
            self.ed_verpy[ver].setText(
                str(pys.get(ver) or DEFAULT_VERSION_PYTHONS.get(ver, "")))
        if self.cmb_lang:
            code = str(d.get("lang", "zh_CN"))
            i = self.cmb_lang.findData(code)
            self.cmb_lang.setCurrentIndex(i if i >= 0 else 0)
        if self.cmb_from:
            i = self.cmb_from.findData(int(d.get("from_step", 0)))
            self.cmb_from.setCurrentIndex(i if i >= 0 else 0)
        if self.cmb_clean:
            i = self.cmb_clean.findData(str(d.get("clean_mode", "none")))
            self.cmb_clean.setCurrentIndex(i if i >= 0 else 0)
        self._sync_defaults()

    def collect(self) -> Config:
        """把界面上的值收成一个 Config（不落盘）。"""
        cfg = Config()
        for key, ed in self.edits.items():
            raw = ed.text().strip()
            if key == "only_steps":
                cfg.only_steps = raw
            elif key in ("from_step",):
                try:
                    cfg.from_step = int(raw or 0)
                except ValueError:
                    cfg.from_step = 0
            else:
                setattr(cfg, key, raw)
        for key, cb in self.checks.items():
            setattr(cfg, key, cb.isChecked())
        # 版本：勾了哪些就是哪些；一个都没勾就退回上次那个
        vers = self._checked_versions() or [(self.cfg.version or "3.14")]
        cfg.versions = vers
        cfg.version = vers[0]
        cfg.version_pythons = {v: self.ed_verpy[v].text().strip()
                               for v in KNOWN_VERSIONS}
        cfg.python = cfg.version_pythons.get(cfg.version, "") or cfg.python
        if self.cmb_lang:
            cfg.lang = str(self.cmb_lang.currentData() or "zh_CN")
        if self.cmb_from:
            cfg.from_step = int(self.cmb_from.currentData() or 0)
        if self.cmb_clean:
            cfg.clean_mode = str(self.cmb_clean.currentData() or "none")
        return cfg

    # ------------------------------------------------------------- 动作
    def on_save(self) -> None:
        cfg = self.collect()
        p = save_config(cfg)
        QMessageBox.information(self, "已保存", f"配置写入：\n{p}")

    def on_reset(self) -> None:
        if QMessageBox.question(self, "恢复默认",
                                "把所有配置项恢复成默认值？（不会立即写盘）") \
                == QMessageBox.StandardButton.Yes:
            self.load_from(Config())

    def on_verify(self) -> None:
        """不跑构建，只检查关键路径/工具在不在。"""
        cfg = self.collect()
        lines: list[str] = []

        def mark(ok: bool, text: str) -> None:
            lines.append(f"{'✔' if ok else '✘'}  {text}")

        lines.append(f"版本 {cfg.version}（分支 {cfg.branch}）")
        vers = cfg.selected_versions()
        if len(vers) >= 2:
            lines.append(f"多选并行：{'、'.join(vers)}（点「开始处理」会各起一个进程）")
            for v in vers:
                sub = cfg.for_version(v)
                lines.append(f"    Python {v} → {sub.full_version()}　{sub.resolved_root()}")
        lines.append(f"构建根目录 {cfg.resolved_root()}"
                     f" —— {'已存在' if Path(cfg.resolved_root()).exists() else '不存在（步骤 1 会创建）'}")
        lines.append(f"输出目录 {cfg.resolved_outdir()}")
        for v in vers:
            py = cfg.python_for(v)
            mark(Path(py).is_file(), f"Python {v} 解释器：{py}"
                                     + ("" if Path(py).is_file() else "（找不到）"))
        tex_ok = False
        for tool in ("xelatex", "latexmk", "makeindex"):
            w = shutil.which(tool, path=cfg.texlive_bin + os.pathsep + os.environ.get("PATH", ""))
            mark(bool(w), f"{tool}：{w or '（在 TeX Live bin 里找不到）'}")
            tex_ok = tex_ok or bool(w)
        mark(bool(shutil.which("git")), f"git：{shutil.which('git') or '（找不到）'}")
        mark(bool(shutil.which("python")),
             f"PATH 里的 python（步骤 7 修索引要用）："
             f"{shutil.which('python') or '（找不到，把 venv 填进「构建 venv」）'}")

        # venv 探测（这是最容易踩空的一处：本机实测那份叫 sphinx-venv，不在 <root>/venv）
        try:
            probe = Pipeline(cfg, ConsoleReporter())
            probe.resolve_state()
            vp = probe.resolve_venv()
            mark(Path(vp).is_file(), f"构建 venv：{vp}")
            if Path(vp).is_file():
                r = subprocess.run([str(vp), "-c", "import sphinx, python_docs_theme"],
                                   capture_output=True, creationflags=CREATE_NO_WINDOW)
                mark(r.returncode == 0, "venv 里已装 sphinx + python-docs-theme")
        except Exception as e:                                   # noqa: BLE001
            lines.append(f"✘  venv 探测失败：{e}")

        if cfg.zh_src.strip():
            mark(Path(cfg.zh_src).is_dir(), f"本地翻译源：{cfg.zh_src}")
        else:
            lines.append(f"✔  翻译源：联网下载（{cfg.url_zh()} 分支 {cfg.branch}）"
                         f"{'，并每次 fetch 到最新' if cfg.refresh_sources else ''}")
        lines.append(f"✔  源码：联网下载（{cfg.url_cpython()} 分支 {cfg.branch}）")
        # ★ 2026-10-04 起工具都已内联进本程序，tools/ 下只剩转发器 —— 所以这里
        #   检查的不是「脚本在不在」，而是「内联的那一段在不在」（缺了才真是坏了）。
        lines.append(f"✔  内置工具：{len(BUILTIN_TOOLS)} 个（已内联进本文件，"
                     f"不再依赖外部脚本）；tools/ 下是转发器：{Path(cfg.resolved_tools())}")
        if I18N_EXTRA:
            lines.append(f"✔  内置补充译文：{len(I18N_EXTRA)} 个 .po"
                         f"（{'地址 ' + cfg.i18n_extra_url if cfg.i18n_extra_url.strip() else '未配地址'}）")
        else:
            lines.append("✔  补充译文：程序不内置正文译文（正文用上游 .po 实时更新），"
                         "只内置标题表 TITLES")
            if cfg.i18n_extra_url.strip():
                lines.append(f"    额外补丁地址：{cfg.i18n_extra_url}")
        # GitHub 镜像：列出来，方便用户判断要不要手动固定一个
        urls = cfg.git_urls("python/cpython", cfg.cpython_url)
        lines.append(f"✔  GitHub 镜像（按顺序自动回退，共 {len(urls)} 个）：")
        for i, (name, url) in enumerate(urls, 1):
            lines.append(f"     {i}. {name:<14} {url}")
        root = Path(cfg.resolved_root())
        doc = root / P_CPYTHON / "Doc"
        lines.append(f"    CPython Doc —— {'已存在' if doc.is_dir() else '不存在，需要步骤 1 克隆'}")
        lines.append(f"    Include/patchlevel.h —— "
                     f"{'在' if (root / P_CPYTHON / 'Include' / 'patchlevel.h').is_file() else '缺失（典型坑：稀疏克隆漏了 Include）'}")
        lines.append(f"    build/latex —— {'已存在' if (doc / 'build' / 'latex').is_dir() else '不存在，需要步骤 6'}")

        QMessageBox.information(self, "路径校验", "\n".join(lines))


# ---------------------------------------------------------------------------
# 6.3 构建面板：步骤表 + 实时日志 + 双层进度条
# ---------------------------------------------------------------------------

class BuildPanel(QWidget):
    """右侧：进度可视化。"""

    COLS = ["步骤", "状态", "用时", "摘要 / 进度"]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.start_ts = 0.0
        self._running = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 12, 14, 14)
        lay.setSpacing(8)

        head = QHBoxLayout()
        self.lbl_state = QLabel("就绪")
        self.lbl_state.setObjectName("h1")
        self.lbl_hint = QLabel("点右下角「开始处理」启动全流程")
        self.lbl_hint.setObjectName("hint")
        head.addWidget(self.lbl_state)
        head.addSpacing(10)
        head.addWidget(self.lbl_hint)
        head.addStretch(1)
        self.lbl_elapsed = QLabel("")
        self.lbl_elapsed.setObjectName("hint")
        head.addWidget(self.lbl_elapsed)
        lay.addLayout(head)

        split = QSplitter(Qt.Orientation.Vertical)

        # ── 步骤表 ────────────────────────────────────────────────────────
        self.table = QTableWidget(len(STEPS), len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setWordWrap(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 210)
        self.table.setColumnWidth(1, 76)
        self.table.setColumnWidth(2, 66)
        self.table.verticalHeader().setDefaultSectionSize(28)
        for r, (row, label, title, sub) in enumerate(STEPS):
            it0 = QTableWidgetItem(f"{label}  ·  {title}")
            it0.setToolTip(f"{sub}\n（脚本里的步骤 {label}）")
            it0.setForeground(QColor("#1f2328"))
            f = it0.font()
            f.setBold(True)
            it0.setFont(f)
            self.table.setItem(r, 0, it0)
            for c in (1, 2, 3):
                self.table.setItem(r, c, QTableWidgetItem(""))
            self.table.setRowHeight(r, 28)
        self.table.setMinimumHeight(330)
        split.addWidget(self.table)

        # ── 日志 ──────────────────────────────────────────────────────────
        logwrap = QWidget()
        lv = QVBoxLayout(logwrap)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)
        bar = QHBoxLayout()
        lb = QLabel("运行日志")
        lb.setObjectName("hint")
        bar.addWidget(lb)
        bar.addStretch(1)
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setFixedWidth(64)
        self.btn_clear.clicked.connect(lambda: self.log_view.clear())
        self.btn_export = QPushButton("导出…")
        self.btn_export.setFixedWidth(72)
        self.btn_export.clicked.connect(self.on_export_log)
        self.btn_copy = QPushButton("复制")
        self.btn_copy.setFixedWidth(64)
        self.btn_copy.clicked.connect(self.on_copy_log)
        bar.addWidget(self.btn_copy)
        bar.addWidget(self.btn_export)
        bar.addWidget(self.btn_clear)
        lv.addLayout(bar)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(20000)
        self.log_view.setPlaceholderText("构建输出会实时出现在这里……")
        lv.addWidget(self.log_view, 1)
        split.addWidget(logwrap)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([360, 420])
        lay.addWidget(split, 1)

        # ── 进度条 ────────────────────────────────────────────────────────
        self.pb_total = QProgressBar()
        self.pb_total.setFormat("总进度 %v/%m 步（%p%）")
        self.pb_step = QProgressBar()
        self.pb_step.setFormat("当前步骤 %v/%m（%p%）")
        self.lbl_cur = QLabel("—")
        self.lbl_cur.setObjectName("hint")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        grid.addWidget(QLabel("总进度"), 0, 0)
        grid.addWidget(self.pb_total, 0, 1)
        grid.addWidget(QLabel("当前步骤"), 1, 0)
        grid.addWidget(self.pb_step, 1, 1)
        grid.addWidget(QLabel("正在处理"), 2, 0)
        grid.addWidget(self.lbl_cur, 2, 1)
        lay.addLayout(grid)

        # ── 按钮 ──────────────────────────────────────────────────────────
        btns = QHBoxLayout()
        self.btn_start = QPushButton("开始处理")
        self.btn_start.setObjectName("primary")
        self.btn_start.setMinimumHeight(38)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.setMinimumHeight(38)
        self.btn_stop.setEnabled(False)
        self.btn_open = QPushButton("打开输出目录")
        self.btn_open.setMinimumHeight(38)
        self.btn_logfile = QPushButton("打开完整日志")
        self.btn_logfile.setMinimumHeight(38)
        btns.addWidget(self.btn_start)
        btns.addWidget(self.btn_stop)
        btns.addWidget(self.btn_open)
        btns.addWidget(self.btn_logfile)
        btns.addStretch(1)
        lay.addLayout(btns)

    # ------------------------------------------------------------- 显示
    def log(self, level: str, text: str) -> None:
        color = LEVEL_COLOR.get(level, LEVEL_COLOR["info"])
        weight = "600" if level in ("step", "err", "ok") else "400"
        ts = "" if level in ("raw",) else f'<span style="color:#9aa4ae">[{now_hms()}] </span>'
        # 每行都带时间戳太重，只给非 raw 行加
        body = _esc(text).replace("\n", "<br>")
        try:
            self.log_view.appendHtml(
                f'<span style="color:{color};font-weight:{weight}">{ts}{body}</span>')
            sb = self.log_view.verticalScrollBar()
            sb.setValue(sb.maximum())
        except Exception:
            pass

    def set_row(self, row: int, state: str, dur: str = "", summary: str = "") -> None:
        for r, (i, _l, _t, _s) in enumerate(STEPS):
            if i == row:
                self.table.setRowHeight(r, 28)
                it = self.table.item(r, 1)
                if it:
                    it.setText(state)
                    it.setForeground(QColor(STATE_COLOR.get(state, "#24292f")))
                    f = it.font()
                    f.setBold(state == "执行中")
                    it.setFont(f)
                if dur:
                    self.table.setItem(r, 2, QTableWidgetItem(dur))
                if summary:
                    cell = self.table.item(r, 3)
                    if cell:
                        cell.setText(summary)
                        cell.setToolTip(summary)
                        cell.setForeground(QColor("#57606a"))
                if state == "执行中":
                    self.table.scrollToItem(self.table.item(r, 0))
                    self.table.selectRow(r)
                return

    def reset(self, selected: list[int]) -> None:
        for r, (i, _l, _t, _s) in enumerate(STEPS):
            self.table.setItem(r, 1, QTableWidgetItem("已跳过" if i not in selected else "待执行"))
            self.table.item(r, 1).setForeground(
                QColor(STATE_COLOR["已跳过"] if i not in selected else STATE_COLOR["待执行"]))
            self.table.setItem(r, 2, QTableWidgetItem(""))
            self.table.setItem(r, 3, QTableWidgetItem(""))
        self.pb_total.setRange(0, len(selected))
        self.pb_total.setValue(0)
        self.pb_step.setRange(0, 1)
        self.pb_step.setValue(0)
        self.lbl_cur.setText("—")

    # ------------------------------------------------------------ 日志动作
    def on_copy_log(self) -> None:
        QApplication.clipboard().setText(self.log_view.toPlainText())

    def on_export_log(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, "导出日志", "构建日志.txt",
                                           "文本 (*.txt *.log)")
        if p:
            Path(p).write_text(self.log_view.toPlainText(), encoding="utf-8")


# ---------------------------------------------------------------------------
# 6.35 多版本并行：子进程日志协议 + 单版本日志面板 + 汇总窗口
# ---------------------------------------------------------------------------
#
# 为什么用「子进程 + 结构化日志」而不是在一个界面里开 N 个 QThread：
#   ① 三个版本各要一份 venv、各要改 PATH / LC_ALL / 工作目录 —— 同一个进程里
#      这些是**共享**的（os.environ 是全局的），并发跑必然互相踩；
#   ② 步骤 7 已经会在内部再开线程池并发编译，外面再叠一层线程，出问题时
#      线程栈根本看不出来是哪个版本的；
#   ③ 杀进程时，进程边界最干净（`taskkill /T` 一杀一整棵，不留孤儿 xelatex）。
#
# 子进程就是**本程序自己**加 `--cli --json-log --config <临时配置>`：流水线一份代码，
# 不会出现「界面版能跑、命令行版跑不了」的分叉。

#: 协议行前缀（\x1e = 记录分隔符，正常日志里不会出现）。
JSON_MARK = "\x1eWBPDF\x1e"


def _self_cmd() -> list[str]:
    """「怎么把本程序再起一份」：打包后就是 exe 自己；源码模式要带上脚本路径。"""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve())]


def _child_env() -> dict[str, str]:
    """子进程环境：UTF-8 + 无缓冲，并清掉会让删除变慢 600 倍的 shim。"""
    env = dict(os.environ)
    # ★ 清掉 WorkBuddy CLI 注入的 safe-delete shim（PYTHONPATH 指向 vendor/shim）：
    #   它把每个 os.unlink / os.rmdir 改道去调 trash 子进程，实测一棵小目录树
    #   从 0.009 s 变成 16 s。交付的 exe 不加载它，但**源码模式**下会继承。
    env.pop("PYTHONPATH", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"     # 不缓冲才可能「边跑边看」
    for k in ("LC_ALL", "LANG", "LC_CTYPE"):
        env.pop(k, None)
    return env


def _plan_steps(cfg: Config) -> list[int]:
    """这次要跑哪几行步骤 —— 与 `run_cli()` 用的是同一套判据。"""
    only = cfg.only_set()
    return ([s[0] for s in STEPS if s[0] in only] if only
            else [s[0] for s in STEPS if s[0] >= cfg.from_step])


class JsonReporter:
    """子进程里的 reporter：把每条消息编成**一行 JSON** 打到 stdout。

    ★ 为什么不直接复用 ConsoleReporter 的彩色文本：父进程要按级别上色、要画进度、
      要知道「现在哪一步」。解析人类可读文本（`==> 步骤 7` / `    ✔ [7] …`）在
      中文 + GBK + ANSI 转义三者夹击下极脆 —— 实测 `↳` 在 GBK 控制台里能把整个
      步骤崩成退出码 127。结构化最稳。
    """

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        # ★ 心跳线程也会调 log()（见 `Pipeline.run`）——两条线程同时 print 有
        #   可能把一行 JSON 撕开，父进程解析失败就当没收到（丢一行日志）。
        #   加把锁，代价可以忽略。
        self._lock = threading.Lock()

    def _emit(self, **kw) -> None:
        try:
            line = JSON_MARK + json.dumps(kw, ensure_ascii=False)
            with self._lock:
                print(line, flush=True)
        except (OSError, ValueError):
            pass

    # ---- Reporter 协议 ----
    def log(self, text: str, level: str = "info") -> None:
        if level in ("cmd", "raw") and not self.verbose:
            return
        self._emit(ev="log", lvl=level, msg=str(text))

    def step_begin(self, i: int, title: str) -> None:
        _r, label, _t, _s = STEP_BY_ROW[i]
        self._emit(ev="begin", i=i, label=label, title=title)

    def step_end(self, i: int, ok: bool, summary: str, secs: float) -> None:
        self._emit(ev="end", i=i, ok=bool(ok), summary=str(summary), secs=float(secs))

    def sub(self, i: int, done: int, total: int, label: str = "") -> None:
        self._emit(ev="sub", i=i, done=int(done), total=int(total), label=str(label))

    def check_cancel(self) -> None:
        return

    def done(self, ok: bool, msg: str) -> None:
        self._emit(ev="done", ok=bool(ok), msg=str(msg))


class _ChildReader(QThread):
    """读一个子进程的 stdout：JSON 事件与普通行分开送回界面。"""

    sig_ev = pyqtSignal(dict)
    sig_raw = pyqtSignal(str)
    sig_exit = pyqtSignal(int)

    def __init__(self, argv: list[str], env: dict[str, str], cwd: str,
                 parent=None) -> None:
        super().__init__(parent)
        self.argv = argv
        self.env = env
        self.cwd = cwd
        self._proc: subprocess.Popen | None = None
        self._stop = False

    def run(self) -> None:
        rc = -1
        try:
            self._proc = subprocess.Popen(
                self.argv, cwd=self.cwd or None, env=self.env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                bufsize=1, creationflags=CREATE_NO_WINDOW)
            assert self._proc.stdout is not None
            for raw in self._proc.stdout:
                if self._stop:
                    break
                line = raw.rstrip("\r\n")
                if line.startswith(JSON_MARK):
                    try:
                        self.sig_ev.emit(json.loads(line[len(JSON_MARK):]))
                    except ValueError:
                        continue
                elif line.strip():
                    self.sig_raw.emit(strip_ansi(line))
            rc = self._proc.wait()
        except OSError as e:
            self.sig_raw.emit(f"无法启动子进程：{e}")
        finally:
            self.sig_exit.emit(rc)

    def stop(self) -> None:
        self._stop = True
        p = self._proc
        if p is not None and p.poll() is None:
            kill_tree(p.pid)          # onefile 是两层进程，必须杀整棵树


class RunPane(QWidget):
    """一个版本的日志面板 —— 长相与主界面「运行日志」一致。

        标题栏：Python 3.13（3.13.16）   执行中           总用时 03:12
        目录行：<构建根目录>
        进度条：3/10 步
        ┌ 运行日志                          重试  复制  导出…  清空 ┐
        │ …                                                          │
    """

    #: 面板上的「重试」被按下 —— 带上版本号，由 MultiRunWindow 去重跑。
    sig_retry = pyqtSignal(str)

    def __init__(self, cfg: Config, parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.ver = cfg.version
        self.full = cfg.full_version()
        self.t0 = 0.0
        self.final_ok: bool | None = None
        self.final_msg = ""
        self._done_steps = 0
        #: 失败的那一行步骤（0~12 的行号）—— 重试就从它开始
        self.fail_row: int | None = None
        #: 最近开始的步骤行号（兜底：连 end 都没收到就崩了时用它）
        self.cur_row: int | None = None
        #: 这是第几次尝试（1 = 首轮）
        self.attempt = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 8)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.lbl_title = QLabel(f"Python {self.ver}（{self.full}）")
        f = self.lbl_title.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() + 1.0)
        self.lbl_title.setFont(f)
        self.lbl_state = QLabel("待开始")
        self.lbl_state.setObjectName("state")
        self.lbl_state.setStyleSheet(f"color:{STATE_COLOR['待执行']}")
        self.lbl_time = QLabel("")
        self.lbl_time.setObjectName("hint")
        head.addWidget(self.lbl_title)
        head.addWidget(self.lbl_state)
        head.addStretch(1)
        head.addWidget(self.lbl_time)
        lay.addLayout(head)

        self.lbl_dir = QLabel(str(Path(cfg.resolved_root())))
        self.lbl_dir.setObjectName("hint")
        self.lbl_dir.setToolTip(str(Path(cfg.resolved_root())))
        lay.addWidget(self.lbl_dir)

        self.pb = QProgressBar()
        self.pb.setFormat("总进度 %v/%m 步（%p%）")
        self.pb.setRange(0, max(len(_plan_steps(cfg)), 1))
        self.pb.setValue(0)
        lay.addWidget(self.pb)

        # ── 日志框（标题 + 三个按钮，与主界面「运行日志」完全一致）─────────
        bar = QHBoxLayout()
        lb = QLabel("运行日志")
        lb.setObjectName("hint")
        bar.addWidget(lb)
        bar.addStretch(1)
        # ★ 「重试」平时**藏起来**：只有这个版本失败了才出现（见 `finish()`）。
        #   常驻一个灰按钮会让人以为随时能点，而运行中重试会抢同一份目录。
        self.btn_retry = QPushButton("重试")
        self.btn_retry.setFixedWidth(64)
        self.btn_retry.setToolTip("从失败的那一步重新开始：\n"
                                  "已克隆的源码、已建好的 venv 都会保留，不重头再来。")
        self.btn_retry.setVisible(False)
        bar.addWidget(self.btn_retry)
        self.btn_copy = QPushButton("复制")
        self.btn_copy.setFixedWidth(64)
        self.btn_export = QPushButton("导出…")
        self.btn_export.setFixedWidth(72)
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setFixedWidth(64)
        for b in (self.btn_copy, self.btn_export, self.btn_clear):
            bar.addWidget(b)
        lay.addLayout(bar)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(20000)
        self.log_view.setPlaceholderText("构建输出会实时出现在这里……")
        lay.addWidget(self.log_view, 1)

        self.btn_clear.clicked.connect(self.log_view.clear)
        self.btn_copy.clicked.connect(
            lambda: QApplication.clipboard().setText(self.log_view.toPlainText()))
        self.btn_export.clicked.connect(self.on_export)
        self.btn_retry.clicked.connect(lambda: self.sig_retry.emit(self.ver))

    # ------------------------------------------------------------- 显示
    def log(self, level: str, text: str) -> None:
        color = LEVEL_COLOR.get(level, LEVEL_COLOR["info"])
        weight = "600" if level in ("step", "err", "ok") else "400"
        ts = ("" if level == "raw"
              else f'<span style="color:#9aa4ae">[{now_hms()}] </span>')
        body = _esc(text).replace("\n", "<br>")
        try:
            self.log_view.appendHtml(
                f'<span style="color:{color};font-weight:{weight}">{ts}{body}</span>')
            sb = self.log_view.verticalScrollBar()
            sb.setValue(sb.maximum())
        except Exception:                                        # noqa: BLE001
            pass

    def set_state(self, text: str, key: str = "待执行") -> None:
        self.lbl_state.setText(text)
        self.lbl_state.setStyleSheet(f"color:{STATE_COLOR.get(key, '#24292f')}")

    def note_step(self, ok: bool, summary: str, row: int | None = None) -> None:
        """一步结束：进度 +1（失败时也 +1 —— 面板只表示「跑到哪」）。"""
        self._done_steps += 1
        self.pb.setValue(min(self._done_steps, self.pb.maximum()))
        if not ok:
            if row is not None:
                self.fail_row = row
            self.set_state("有步骤失败", "失败")

    def set_sub(self, done: int, total: int, label: str) -> None:
        if total > 1 and label:
            self.lbl_dir.setText(f"{Path(self.cfg.resolved_root()).name}　·　{label} "
                                 f"({done}/{total})")

    def tick(self) -> None:
        if self.t0:
            self.lbl_time.setText(f"已用时 {human_dur(time.monotonic() - self.t0)}")

    def finish(self, ok: bool, msg: str) -> None:
        self.t0 = 0.0
        self.set_state("完成" if ok else "失败", "完成" if ok else "失败")
        if ok:
            self.pb.setValue(self.pb.maximum())
        if msg:
            self.log("ok" if ok else "err", ("✔ " if ok else "✘ ") + msg)
        # ★ 只有失败才给「重试」：成功收起来（再跑一遍没有意义），
        #   运行中也不给（同一份目录里两个进程会互相抢文件）。
        self.btn_retry.setVisible(not ok)
        self.btn_retry.setEnabled(not ok)

    def begin_retry(self, from_row: int) -> None:
        """把面板复位成「重试中」—— 日志**不清**，接在后面续写。

        ★ 为什么不重新 new 一个面板 / 不清日志：用户刚看着一屏报错，清零等于
          把判断依据擦掉了。留一条分隔线，前后两轮的输出都在同一个框里。
        """
        self.attempt += 1
        self.fail_row = None
        self.cur_row = None
        self.final_ok = None
        self.final_msg = ""
        self._done_steps = 0
        rows = [s[0] for s in STEPS if s[0] >= from_row]
        self.pb.setRange(0, max(len(rows), 1))
        self.pb.setValue(0)
        self.set_state(f"重试中（第 {self.attempt} 次）", "执行中")
        self.btn_retry.setVisible(False)
        self.t0 = time.monotonic()
        label = STEP_BY_ROW[from_row][1] if from_row in STEP_BY_ROW else str(from_row)
        self.log("warn", f"———————— 第 {self.attempt} 次尝试：从步骤 {label} 重跑"
                         f"（源码与 venv 保留，日志续写）————————")

    def on_export(self) -> None:
        p, _ = QFileDialog.getSaveFileName(
            self, f"导出 Python {self.ver} 日志", f"构建日志-{self.ver}.txt",
            "文本 (*.txt *.log)")
        if p:
            Path(p).write_text(self.log_view.toPlainText(), encoding="utf-8")


class MultiRunWindow(QWidget):
    """多版本并行的汇总窗口：每个版本一个 RunPane，并排放在一个 QSplitter 里。"""

    def __init__(self, cfgs: list[Config], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("多版本并行构建")
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.cfgs = cfgs
        self.panes: dict[str, RunPane] = {}
        self.readers: dict[str, _ChildReader] = {}
        #: 每个版本**当前这一轮**用的配置（重试时会被替换成 from_step 改过的那份）
        self.sub_cfgs: dict[str, Config] = {c.version: c for c in cfgs}
        self.t0 = 0.0
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wbpdf-multi-"))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        head = QHBoxLayout()
        ttl = QLabel(f"多版本并行 · {len(cfgs)} 个版本")
        ttl.setObjectName("h1")
        self.lbl_sum = QLabel("准备中…")
        self.lbl_sum.setObjectName("hint")
        self.lbl_time = QLabel("")
        self.lbl_time.setObjectName("hint")
        head.addWidget(ttl)
        head.addSpacing(10)
        head.addWidget(self.lbl_sum)
        head.addStretch(1)
        head.addWidget(self.lbl_time)
        lay.addLayout(head)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        for c in cfgs:
            box = QFrame()
            box.setObjectName("card")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            pane = RunPane(c, box)
            bl.addWidget(pane)
            split.addWidget(box)
            self.panes[c.version] = pane
            pane.sig_retry.connect(self.retry)
            box.setMinimumWidth(380)
        lay.addWidget(split, 1)

        bottom = QHBoxLayout()
        self.btn_stop = QPushButton("全部停止")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.setMinimumHeight(34)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_all)
        self.btn_open = QPushButton("打开基准目录")
        self.btn_open.setMinimumHeight(34)
        self.btn_open.clicked.connect(self.on_open_base)
        # ★ 一次重试所有失败的版本 —— 三个版本里两个栽在网络上时，比挨个点省事。
        self.btn_retry_all = QPushButton("重试失败项")
        self.btn_retry_all.setMinimumHeight(34)
        self.btn_retry_all.setEnabled(False)
        self.btn_retry_all.setToolTip("把所有「失败」的版本从各自失败的那一步重新跑一遍")
        self.btn_retry_all.clicked.connect(self.retry_all_failed)
        self.btn_close = QPushButton("关闭")
        self.btn_close.setMinimumHeight(34)
        self.btn_close.clicked.connect(self.close)
        bottom.addWidget(self.btn_stop)
        bottom.addWidget(self.btn_retry_all)
        bottom.addWidget(self.btn_open)
        bottom.addStretch(1)
        bottom.addWidget(self.btn_close)
        lay.addLayout(bottom)

        #: 每个版本的目标目录，给「打开基准目录」用
        self.base_dir = str(Path(cfgs[0].base_dir or _guess_base_dir()))

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

        n = len(cfgs)
        self.resize(max(520 * n, 900), 720)

    # ------------------------------------------------------------- 启动
    def start_all(self) -> None:
        """★ 同时起：先全部 spawn，再各自读 —— 不串行等待。"""
        self.t0 = time.monotonic()
        for c in self.cfgs:
            pane = self.panes.get(c.version)
            if pane is None:
                continue
            try:
                root = Path(c.resolved_root())
                root.mkdir(parents=True, exist_ok=True)     # ★ 新建文件夹
            except OSError as e:
                pane.log("err", f"建不了构建根目录 {c.resolved_root()}：{e}")
                pane.finish(False, "目录建不了")
                continue
            cfg_file = self.tmpdir / f"{c.version}.json"
            try:
                save_config(c, str(cfg_file))
            except OSError as e:
                pane.log("err", f"临时配置写不进去：{e}")
                pane.finish(False, "配置写不进去")
                continue
            argv = _self_cmd() + ["--cli", "--json-log", "--config", str(cfg_file)]
            rd = _ChildReader(argv, _child_env(), str(app_dir()))
            # ★ 事件带上是**哪个 reader** 发出来的：重试会换掉 reader，上一轮
            #   迟到的 done/exit 不能把新一轮的状态又改回「失败」。
            rd.sig_ev.connect(lambda ev, v=c.version, r=rd: self.on_ev(v, ev, r))
            rd.sig_raw.connect(lambda t, v=c.version: self.panes[v].log("raw", t))
            rd.sig_exit.connect(lambda rc, v=c.version, r=rd: self.on_exit(v, rc, r))
            self.readers[c.version] = rd
            pane.log("meta", f"版本 Python {c.version}（{c.full_version()}）"
                             f"　解释器 {c.python}")
            pane.log("meta", f"构建根目录 {c.resolved_root()}")
            # onefile 的 exe 每次启动都要自解压（几秒），先说明一句，
            # 免得面板空白让人以为没启动。
            pane.log("meta", "正在启动子进程…（打包版首次启动要解压，几秒钟）")
            pane.set_state("执行中", "执行中")
            pane.t0 = time.monotonic()
            rd.start()
        self.btn_stop.setEnabled(True)
        self.timer.start()
        self._refresh()

    # ------------------------------------------------------------- 事件
    def on_ev(self, ver: str, ev: dict, reader=None) -> None:
        # ★ 迟到的旧事件直接丢：重试换过 reader 之后，上一轮的 done/end 不该再算数
        if reader is not None and self.readers.get(ver) is not reader:
            return
        pane = self.panes.get(ver)
        if pane is None:
            return
        kind = ev.get("ev")
        if kind == "log":
            pane.log(str(ev.get("lvl") or "info"), str(ev.get("msg") or ""))
        elif kind == "begin":
            i = ev.get("i")
            if isinstance(i, int):
                pane.cur_row = i
            pane.log("step", f"===== 步骤 {ev.get('label')} · {ev.get('title')} =====")
        elif kind == "end":
            i = ev.get("i")
            pane.note_step(bool(ev.get("ok")), str(ev.get("summary") or ""),
                           i if isinstance(i, int) else None)
        elif kind == "sub":
            pane.set_sub(int(ev.get("done") or 0), int(ev.get("total") or 1),
                         str(ev.get("label") or ""))
        elif kind == "done":
            # ★ 结论以子进程**自己报的**为准，一到就把面板定稿 —— 别等进程退出
            #   （onefile 退出还要拆临时目录，晚几百毫秒；测试/用户都会看到
            #    「明明跑完了还写着执行中」）。
            ok = bool(ev.get("ok"))
            msg = str(ev.get("msg") or "")
            if not ok and pane.fail_row is None:
                # 失败但没收到 end（步骤里抛了非 Fail 异常）：退回「最近开始的
                # 那一步」，总比从第 0 步重跑强。
                pane.fail_row = pane.cur_row
            pane.final_ok = ok
            pane.final_msg = msg
            pane.finish(ok, msg)
            self._refresh()

    def on_exit(self, ver: str, rc: int, reader=None) -> None:
        if reader is not None and self.readers.get(ver) is not reader:
            return
        pane = self.panes.get(ver)
        if pane is None:
            return
        if pane.final_ok is None:
            # 没收到 done（崩了 / 被杀）：只能按退出码判
            ok = rc == 0
            pane.final_ok = ok
            pane.final_msg = "完成" if ok else f"进程退出码 {rc}（没有收到结束消息）"
            pane.finish(ok, pane.final_msg)
        self._refresh()

    # ------------------------------------------------------------- 状态
    def _refresh(self) -> None:
        running = sum(1 for v, r in self.readers.items()
                      if v in self.panes and self.panes[v].final_ok is None)
        done = sum(1 for p in self.panes.values() if p.final_ok is not None)
        bad = sum(1 for p in self.panes.values() if p.final_ok is False)
        self.lbl_sum.setText(f"运行中 {running} · 完成 {done - bad} · 失败 {bad}")
        self.btn_retry_all.setEnabled(bad > 0)
        if running == 0 and self.t0:
            self.timer.stop()
            self.btn_stop.setEnabled(False)
            secs = time.monotonic() - self.t0
            self.lbl_time.setText(f"总用时 {human_dur(secs)}")
            self.lbl_sum.setText(f"全部结束：完成 {done - bad} · 失败 {bad}")

    def _tick(self) -> None:
        for p in self.panes.values():
            p.tick()
        if self.t0:
            self.lbl_time.setText(f"已用时 {human_dur(time.monotonic() - self.t0)}")

    # ------------------------------------------------------------- 动作
    def stop_all(self) -> None:
        self.btn_stop.setEnabled(False)
        for p in self.panes.values():
            if p.final_ok is None:
                p.log("warn", "收到停止指令，正在结束该版本的进程……")
        for rd in self.readers.values():
            rd.stop()
        # ★ 立刻把面板定成「已停止」：万一 kill_tree 没杀干净、子进程迟迟不退出，
        #   面板也不会永远挂在「执行中」——不然「重试」也点不了（它要求
        #   final_ok 已定稿），用户就彻底没路走了。
        for p in self.panes.values():
            if p.final_ok is None:
                p.final_ok = False
                p.final_msg = "已手动停止"
                p.finish(False, "已手动停止")
        self._refresh()

    # ------------------------------------------------------------- 重试
    def retry(self, ver: str) -> None:
        """把某个失败的版本**从失败那一步**重新跑一遍。

        与「关掉窗口再点一次开始」的区别（做这个按钮的全部理由）：
        · 起点是失败步骤，不是第 0 步 —— 已经克隆的 cpython、拉好的译文、
          建好的 venv 全部保留，省掉前面几分钟到几十分钟；
        · 目录不变（date_tag 没变 ⇒ 构建根还是同一个），不会多生一个文件夹；
        · 日志接在原来那个面板后面，不把失败现场擦掉。
        """
        pane = self.panes.get(ver)
        base = self.sub_cfgs.get(ver)
        if pane is None or base is None:
            return
        if pane.final_ok is None:                    # 还在跑
            QMessageBox.information(self, "还在运行",
                                    f"Python {ver} 还在运行，等它结束再重试。")
            return
        start = pane.fail_row if pane.fail_row is not None else base.from_step
        start = int(start or 0)
        # ① 先把上一轮的进程彻底清掉：onefile 是**两层**进程，只 terminate() 会留
        #    孤儿，而孤儿和新进程会抢同一份 build/latex —— 那才是真的「文件搞串」。
        old = self.readers.get(ver)
        if old is not None:
            if old.isRunning():
                old.stop()
            old.wait(5000)
        # ② 派生重试配置：同一个 root / 同一个 venv，只把起点挪到失败那一步
        c = Config(**asdict(base))
        c.from_step = start
        c.only_steps = ""
        cfg_file = self.tmpdir / f"{ver}.json"
        try:
            save_config(c, str(cfg_file))
        except OSError as e:
            pane.log("err", f"重试配置写不进去：{e}")
            return
        self.sub_cfgs[ver] = c
        # ③ 面板复位（日志保留，加一条分隔线）+ 起新进程
        pane.begin_retry(start)
        label = STEP_BY_ROW[start][1] if start in STEP_BY_ROW else str(start)
        pane.log("meta", f"重试起点：步骤 {label}（前面的克隆 / venv / 译文都不重做）")
        rd = _ChildReader(_self_cmd() + ["--cli", "--json-log", "--config", str(cfg_file)],
                          _child_env(), str(app_dir()))
        rd.sig_ev.connect(lambda ev, v=ver, r=rd: self.on_ev(v, ev, r))
        rd.sig_raw.connect(lambda t, v=ver: self.panes[v].log("raw", t))
        rd.sig_exit.connect(lambda rc, v=ver, r=rd: self.on_exit(v, rc, r))
        self.readers[ver] = rd
        self.btn_stop.setEnabled(True)
        if not self.t0:
            self.t0 = time.monotonic()
        self.timer.start()
        rd.start()                                   # 先起再刷：状态立刻变成「重试中」
        self._refresh()

    def retry_all_failed(self) -> None:
        """把所有失败的版本一起重试（三个里两个栽在网络上时最省事）。"""
        for v, p in list(self.panes.items()):
            if p.final_ok is False:
                self.retry(v)

    def on_open_base(self) -> None:
        open_in_explorer(Path(self.base_dir))

    def closeEvent(self, ev) -> None:                            # noqa: N802
        running = [v for v, p in self.panes.items() if p.final_ok is None]
        if running:
            if QMessageBox.question(
                    self, "还在运行",
                    f"还有 {len(running)} 个版本在跑（{'、'.join(running)}），"
                    f"确定全部停止并关闭？") != QMessageBox.StandardButton.Yes:
                ev.ignore()
                return
            self.stop_all()
            for rd in self.readers.values():
                rd.wait(5000)
        for rd in self.readers.values():
            if rd.isRunning():
                rd.wait(2000)
        try:
            force_delete(self.tmpdir)
        except OSError:
            pass
        ev.accept()


# ---------------------------------------------------------------------------
# 6.4 主窗口
# ---------------------------------------------------------------------------

class VolumeEditorDialog(QDialog):
    """分册配置编辑器 —— 可视化编辑 `volumes.json`。

    ★ 为什么要有这个窗口：**册数随版本变**（3.10 27 册 → 3.15 39 册），而且上游每年
      都会加或删几册（3.11 删了 distributing、3.13 拆出 builtins、每年加几篇 howto）。
      以前「加一行」要改 9000 行的主程序再重新打包 exe；现在在这里点几下，存成
      `volumes.json` 就生效 —— 同一份文件 CI 与命令行工具也在用。
    ★ 表格的**行顺序 = 合并册的一级顺序**（`merge_order`），所以「上移/下移」就是
      调合并册的章节顺序，`builtins` 因此能排在 reference 与 library 之间。
    ★ 「指南整块」那一行是占位符（代表 29 篇 howto 打包成的一块），它不能删，
      也不能改文件名 —— 只决定这块在合并册里的位置。
    """

    COLS = ["类型", "上游产物名（slug）", "文件名（含编号）", "书签标题", "最低版本", "最高版本"]
    #: 界面文字 → 内部 kind
    KINDS = [("前置册", "main"), ("指南整块", HOWTO_KEY), ("指南分册", "howto"), ("尾部册", "tail")]
    KIND_TIP = {
        "main": "合并册里的一级章节（01~08 那批）",
        HOWTO_KEY: "占位行：代表《Python 指南》整块；位置=这块在合并册里的位置",
        "howto": "《Python 指南》下的分册，文件名必须以 4 位编号开头（0901…）",
        "tail": "排在末尾的册（常见问题 / 内置参考手册）",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("分册配置 · 各版本册数不同，在这里改")
        self.resize(1240, 740)

        lay = QVBoxLayout(self)
        tip = QLabel(
            "行顺序 = 合并册的一级顺序。版本区间是闭区间（留空 = 不限）："
            "例如 distributing 只有 ≤3.10 有，就填「最高版本 3.10」；"
            "builtins 3.13 才拆出来，就填「最低版本 3.13」。"
            "文件名里的 {V} 会替换成当前版本号。")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.cellChanged.connect(lambda *_: self._refresh_preview())
        lay.addWidget(self.table, 1)

        self.lbl_preview = QLabel("")
        self.lbl_preview.setObjectName("hint")
        self.lbl_preview.setWordWrap(True)
        lay.addWidget(self.lbl_preview)

        bar = QHBoxLayout()
        for text, slot, tipx in (
            ("新增一行", self.on_add, "在末尾加一册（默认前置册）"),
            ("删除行", self.on_del, "删掉选中的行（「指南整块」不能删）"),
            ("上移", lambda: self.on_move(-1), "往前挪：合并册里就排在前面"),
            ("下移", lambda: self.on_move(+1), "往后挪"),
            ("自检", self.on_check, "跑 name-map 的全部一致性检查"),
        ):
            b = QPushButton(text)
            b.setToolTip(tipx)
            b.clicked.connect(slot)
            bar.addWidget(b)
        bar.addStretch(1)
        for text, slot, tipx in (
            ("还原内置默认", self.on_reset, "把表格恢复成程序内置的表（不删文件）"),
            ("另存为…", self.on_save_as, "存到别处；注意只有 sphinx-pdf/volumes.json 会被自动加载"),
            ("保存并生效", self.on_save, "写入 volumes.json 并立刻重新加载"),
        ):
            b = QPushButton(text)
            b.setToolTip(tipx)
            b.clicked.connect(slot)
            bar.addWidget(b)
        close = QPushButton("关闭")
        close.clicked.connect(self.reject)
        bar.addWidget(close)
        lay.addLayout(bar)

        self.lbl_where = QLabel("")
        self.lbl_where.setObjectName("hint")
        self.lbl_where.setWordWrap(True)
        lay.addWidget(self.lbl_where)

        self._load_rows()
        self._refresh_preview()

    # ------------------------------------------------------------ 表格读写
    def _kind_combo(self, kind: str) -> QComboBox:
        cb = QComboBox()
        for text, code in self.KINDS:
            cb.addItem(text, code)
        idx = max(0, cb.findData(kind))
        cb.setCurrentIndex(idx)
        cb.setToolTip(self.KIND_TIP.get(kind, ""))
        cb.currentIndexChanged.connect(lambda *_: self._refresh_preview())
        return cb

    def _add_row(self, kind: str, slug: str, name: str, title: str,
                 lo: str = "", hi: str = "") -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setCellWidget(r, 0, self._kind_combo(kind))
        for c, text in ((1, slug), (2, name), (3, title), (4, lo), (5, hi)):
            self.table.setItem(r, c, QTableWidgetItem(text))
        if kind == HOWTO_KEY:
            # 占位行：slug / 文件名 都不该手改，改灰掉免得误编辑
            self.table.item(r, 1).setText(HOWTO_KEY)
            for c in (1, 2):
                it = self.table.item(r, c)
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)

    def _load_rows(self) -> None:
        """按当前生效的表重建表格（合并顺序 → 行顺序）。"""
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        info = {s: (n, t) for s, n, t in (*MAIN, *TAIL)}
        for key in MERGE_ORDER:
            if key == HOWTO_KEY:
                self._add_row(HOWTO_KEY, HOWTO_KEY, HOWTO_ROOT_TITLE, "")
                for slug, name, title in HOWTO:
                    self._add_row('howto', slug, name, title,
                                  self._v(MIN_VERSION.get(slug)), self._v(MAX_VERSION.get(slug)))
                continue
            if key not in info:
                continue
            name, title = info[key]
            kind = 'main' if any(s == key for s, _n, _t in MAIN) else 'tail'
            self._add_row(kind, key, name, title,
                          self._v(MIN_VERSION.get(key)), self._v(MAX_VERSION.get(key)))
        self.table.blockSignals(False)
        self.lbl_where.setText(
            f"当前生效：{VOLUMES_NOTE}\n保存位置：{volumes_json_path() or default_volumes_json_path()}")

    @staticmethod
    def _v(t) -> str:
        return '%d.%d' % t if t else ''

    def _collect(self) -> tuple[list[dict], list[str]]:
        """把表格读成 (volumes, merge_order)；不合法的单元格抛 ValueError。"""
        vols: list[dict] = []
        order: list[str] = []
        seen: set[str] = set()
        for r in range(self.table.rowCount()):
            cb = self.table.cellWidget(r, 0)
            kind = cb.currentData() if cb else 'main'
            slug = (self.table.item(r, 1).text() if self.table.item(r, 1) else '').strip()
            if kind == HOWTO_KEY:
                order.append(HOWTO_KEY)
                continue
            name = (self.table.item(r, 2).text() if self.table.item(r, 2) else '').strip()
            title = (self.table.item(r, 3).text() if self.table.item(r, 3) else '').strip()
            lo = (self.table.item(r, 4).text() if self.table.item(r, 4) else '').strip()
            hi = (self.table.item(r, 5).text() if self.table.item(r, 5) else '').strip()
            if not slug or not name:
                raise ValueError(f"第 {r + 1} 行：slug 和文件名都不能空")
            if slug in seen:
                raise ValueError(f"第 {r + 1} 行：slug 重复（{slug}）")
            seen.add(slug)
            if kind == 'howto' and not (name[:4].isdigit() and len(name) > 4):
                raise ValueError(f"第 {r + 1} 行：指南分册的文件名要以 4 位编号开头（{name}）")
            for lab, raw in (("最低版本", lo), ("最高版本", hi)):
                if raw and ver_tuple(raw) == (0, 0):
                    raise ValueError(f"第 {r + 1} 行：{lab}「{raw}」不是 3.10 这种格式")
            item = {'slug': slug, 'name': name, 'title': title, 'kind': kind}
            if lo:
                item['min'] = lo
            if hi:
                item['max'] = hi
            vols.append(item)
            # ★ merge_order 只登记「一级」条目：main / tail + 指南整块的占位符。
            #   howto 是块**内部**的顺序（由它们在表格里的先后决定），混进来会让
            #   合并册去 MAIN/TAIL 里找一个不存在的键 → KeyError。
            if kind in ('main', 'tail'):
                order.append(slug)
        if HOWTO_KEY not in order:
            raise ValueError("「指南整块」那一行不能删")
        return vols, order

    # ------------------------------------------------------------ 预览/操作
    def _refresh_preview(self) -> None:
        try:
            vols, _order = self._collect()
        except ValueError as e:
            self.lbl_preview.setText(f"⚠ {e}")
            return
        rows = []
        for v in KNOWN_VERSIONS:
            cur = ver_tuple(v)
            n = 0
            for item in vols:
                lo = ver_tuple(item.get('min') or '0.0')
                hi = ver_tuple(item.get('max') or '999.0')
                if lo <= cur <= hi:
                    n += 1
            rows.append(f"{v} {n} 册")
        self.lbl_preview.setText("按当前表格算出的册数：" + " · ".join(rows)
                                 + f"（共 {len(vols)} 条登记）")

    def on_add(self) -> None:
        r = self.table.currentRow()
        r = self.table.rowCount() if r < 0 else r + 1
        self.table.insertRow(r)
        self.table.setCellWidget(r, 0, self._kind_combo('main'))
        for c, text in ((1, ''), (2, ''), (3, ''), (4, ''), (5, '')):
            self.table.setItem(r, c, QTableWidgetItem(text))
        self.table.setCurrentCell(r, 1)
        self._refresh_preview()

    def on_del(self) -> None:
        r = self.table.currentRow()
        if r < 0:
            return
        cb = self.table.cellWidget(r, 0)
        if cb and cb.currentData() == HOWTO_KEY:
            QMessageBox.information(self, "这一行不能删",
                                    "「指南整块」是占位行，它代表 29 篇 howto 打包成的那一块，"
                                    "删掉就没有《Python 指南》了。")
            return
        self.table.removeRow(r)
        self._refresh_preview()

    def on_move(self, step: int) -> None:
        r = self.table.currentRow()
        if r < 0:
            return
        cb = self.table.cellWidget(r, 0)
        is_howto = bool(cb and cb.currentData() == 'howto')
        block_row = next((i for i in range(self.table.rowCount())
                          if (self.table.cellWidget(i, 0)
                              and self.table.cellWidget(i, 0).currentData() == HOWTO_KEY)), -1)
        if not is_howto:
            # 顶层的行跨过「指南整块」是允许的：那正是「指南排在标准库之前/之后」的调整
            tgt = r + step
            if tgt < 0 or tgt >= self.table.rowCount():
                return
            if tgt == block_row:
                tgt += step
            if tgt < 0 or tgt >= self.table.rowCount():
                return
            if self.table.cellWidget(tgt, 0) and \
                    self.table.cellWidget(tgt, 0).currentData() == HOWTO_KEY:
                return
        else:
            tgt = r + step
            if tgt < 0 or tgt >= self.table.rowCount():
                return
            tcb = self.table.cellWidget(tgt, 0)
            if not (tcb and tcb.currentData() == 'howto'):
                return
        for c in range(1, self.table.columnCount()):
            a = self.table.item(r, c)
            b = self.table.item(tgt, c)
            if a and b and (a.flags() & Qt.ItemFlag.ItemIsEditable):
                ta, tb = a.text(), b.text()
                a.setText(tb)
                b.setText(ta)
        self.table.setCurrentCell(tgt, 1)
        self._refresh_preview()

    def on_check(self) -> None:
        try:
            vols, order = self._collect()
        except ValueError as e:
            QMessageBox.warning(self, "表格里有问题", str(e))
            return
        bad = selfcheck()
        if bad:
            QMessageBox.warning(self, "自检没过", "· " + "\n· ".join(bad)
                                + "\n\n（这些都是保存之后才会暴露的坑，先改表格再存）")
            return
        QMessageBox.information(self, "自检通过",
                                f"{len(vols)} 条登记、{len(order)} 个合并位置，"
                                f"编号与文件名都不撞车。")

    def on_reset(self) -> None:
        if QMessageBox.question(
                self, "还原内置默认",
                "把表格恢复成程序内置的表（外部 volumes.json 不动）。\n"
                "要真正生效，之后点「保存并生效」覆盖掉那个文件。\n\n继续？"
        ) != QMessageBox.StandardButton.Yes:
            return
        _restore_embedded()
        self._load_rows()
        self._refresh_preview()

    def _write(self, path: Path) -> None:
        vols, order = self._collect()
        data = {
            'schema': VOLUMES_SCHEMA,
            '_说明': ('分册配置。kind: main=前置册 / howto=Python 指南 / tail=尾部册；'
                     'min/max 是闭区间版本上下限（省略 = 不限）；name 里的 {V} 换成当前版本号。'
                     '改完跑 `--tool name-map --check` 自检，'
                     '`--tool volumes --verify` 可对着 github.com/python/cpython 各分支在线复核。'),
            'howto_root_title': (self.table.item(
                next(i for i in range(self.table.rowCount())
                     if self.table.cellWidget(i, 0)
                     and self.table.cellWidget(i, 0).currentData() == HOWTO_KEY), 2).text().strip()
                or HOWTO_ROOT_TITLE),
            'merge_order': order,
            'volumes': vols,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
        tmp.replace(path)                      # 原子替换：写一半断电也不会留下坏文件
        note = load_volumes(path, quiet=True)
        bad = selfcheck()
        msg = f"已保存：{path}\n{note}"
        if bad:
            msg += "\n\n⚠ 自检发现 %d 个问题：\n· %s" % (len(bad), "\n· ".join(bad))
        else:
            msg += "\n\n自检通过。下次构建就按新表改名字/合并。"
        self.lbl_where.setText(f"当前生效：{VOLUMES_NOTE}\n保存位置：{path}")
        QMessageBox.information(self, "保存完成", msg)
        parent = self.parent()
        if parent is not None and hasattr(parent, "_refresh_volume_hint"):
            parent._refresh_volume_hint()

    def on_save(self) -> None:
        try:
            self._write(volumes_json_path() or default_volumes_json_path())
        except ValueError as e:
            QMessageBox.warning(self, "表格里有问题", str(e))

    def on_save_as(self) -> None:
        p, _f = QFileDialog.getSaveFileName(
            self, "另存分册配置", str(default_volumes_json_path()), "JSON (*.json)")
        if not p:
            return
        try:
            self._write(Path(p))
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "保存失败", str(e))


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self.worker: BuildWorker | None = None
        self.multi: MultiRunWindow | None = None
        self.cur_steps: list[int] = []

        self.setWindowTitle("Python 中文文档分册 PDF 构建器 · 路线 A（Sphinx）")
        self.resize(1520, 960)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.settings = SettingsPanel(cfg)
        self.build = BuildPanel()
        sw = QScrollArea()
        sw.setWidgetResizable(True)
        sw.setFrameShape(QFrame.Shape.NoFrame)
        sw.setWidget(self.settings)
        sw.setMinimumWidth(560)
        sw.setMaximumWidth(760)
        split.addWidget(sw)
        split.addWidget(self.build)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([600, 920])
        self.setCentralWidget(split)

        # 信号
        self.build.btn_start.clicked.connect(self.on_start)
        self.build.btn_stop.clicked.connect(self.on_stop)
        self.build.btn_open.clicked.connect(
            lambda: open_in_explorer(Path(self.cfg.resolved_outdir())))
        self.build.btn_logfile.clicked.connect(self.on_open_log)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

        self.build.log("info", "就绪。默认配置直接可用：源码与翻译源联网下载、语言中文。"
                               "点「校验路径」确认环境，再点「开始处理」。")
        self.build.log("meta", "本程序是 build-sphinx-pdf.sh 的 Python 版："
                              "步骤 0/1/2/3/4/5/6/6b/7/7b/8 一一对应；"
                              "步骤 9（合并成一册）和步骤 10（清理过程文件）是本程序新增的可选步。")
        self.build.log("meta", f"配置文件：{config_path()}")

    # ------------------------------------------------------------ 启动
    def on_start(self) -> None:
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "正在运行", "上一轮还没结束，请先停止或等它跑完。")
            return
        if self.multi is not None and self.multi.isVisible():
            QMessageBox.information(self, "正在运行", "多版本并行窗口还开着，先关掉它再开新的一轮。")
            return
        cfg = self.settings.collect()
        vers = cfg.selected_versions()
        if not self.settings._checked_versions():
            QMessageBox.warning(self, "没选版本",
                                "请在「① 版本与目录」里至少勾一个版本"
                                "（3.13 / 3.14 / 3.15）。")
            return
        # ★ 勾了 2 个及以上 → 各起一个进程同时跑（见 6.35 的说明）
        if len(vers) >= 2:
            self.start_multi(cfg, vers)
            return
        only = cfg.only_set()
        if only:
            steps = [s[0] for s in STEPS if s[0] in only]
        else:
            steps = [s[0] for s in STEPS if s[0] >= cfg.from_step]
        if not steps:
            QMessageBox.warning(self, "没有可执行的步骤", "检查「起始步骤 / 只跑这些步」。")
            return

        # 会清空中间产物的两步，先问清楚
        if cfg.from_step <= 3 <= max(steps) and not cfg.keep_build_dir:
            warn = ("注意：步骤 3 会清空 Doc/locales 重新铺 .po；\n"
                    "步骤 4 默认会清空 Doc/build 重新构建（耗时最长的一步）。\n\n"
                    "只想重跑后半段？把「起始步骤」调到 6 或更高。\n\n确定继续？")
            if QMessageBox.question(self, "确认", warn) != QMessageBox.StandardButton.Yes:
                return

        # 语言不是 CJK：正文会是英文；开了「封面标题中文化」的话，那些中文标题
        # 还会因为 Latin 字体（FreeSans）没有汉字字形而整段消失。
        # 这个坑不报错、不中断，只是默默产出一套英文 PDF，必须在开跑前拦住。
        if cfg.lang not in CJK_LANGS:
            warn = f"「语言」当前是 {cfg.lang}，不是 CJK：\n\n" \
                   "· 正文会按英文原文排版，不套用 python-docs-zh-cn 的翻译；"
            if cfg.localize_titles:
                warn += ("\n· 步骤 6b 仍会把 11 册封面/页眉标题改成中文，但语言非 CJK 时\n"
                         "  Sphinx 不加载 xeCJK，汉字没有任何字体可用，会**整段静默丢掉**；\n"
                         "  编译日志里就是一片 Missing character: There is no 安 (U+5B89)。")
            warn += "\n\n要出中文 PDF，请把「语言」改回 zh_CN。\n（改完记得重跑步骤 2→3 铺 .po）" \
                    "\n\n确定仍按当前语言继续？"
            if QMessageBox.question(self, "语言不是中文", warn) != QMessageBox.StandardButton.Yes:
                return

        # 步骤 10 会删掉源码/venv/翻译源，这是不可逆的，开跑前必须再确认一次
        if 12 in steps and (cfg.clean_mode or "none") != "none":
            where = ("<构建根>/cpython/Doc/build（只删构建中间件）"
                     if cfg.clean_mode == "build" else
                     "<构建根>/cpython（CPython 源码）\n"
                     "  · <构建根>/venv（虚拟环境与全部依赖）\n"
                     "  · <构建根>/zh-cn（中文翻译源）\n"
                     "  · <构建根>/*.log")
            warn = (f"⚠ 步骤 10 会删除以下内容，删掉后不可恢复：\n\n  · {where}\n\n"
                    "成品 PDF 永远不会被删。\n"
                    "全删之后下次要重新联网克隆源码、重装依赖（十几分钟）。\n\n"
                    "确定要清理吗？")
            if QMessageBox.question(self, "确认清理过程文件", warn) \
                    != QMessageBox.StandardButton.Yes:
                return

        # 关掉联网下载又没填本地翻译源 —— 步骤 2 必然失败，先说清楚
        if not cfg.download_sources and not cfg.zh_src.strip():
            QMessageBox.warning(
                self, "翻译源没着落",
                "「从网站实时下载」被关掉了，而「本地翻译源目录」是空的。\n\n"
                "步骤 2 需要一处 python-docs-zh-cn 源码：\n"
                "· 打开「② 下载源」里的联网下载（推荐），或\n"
                "· 在「本地翻译源目录」里填一个已有的 python-docs-zh-cn 目录。")
            return

        self.cfg = cfg
        try:
            save_config(cfg)
        except OSError:
            self.build.log("warn", f"配置写不进磁盘（{config_path()}），本轮改动只在内存里生效")
        self.cur_steps = steps

        self.build.log_view.clear()
        self.build.reset(steps)
        self.build.log("step", f"开始处理：共 {len(steps)} 个步骤 "
                              f"（{'、'.join(STEP_BY_ROW[s][1] for s in steps)}）")
        self.build.log("meta", f"版本       Python {cfg.version}（分支 {cfg.branch}）")
        self.build.log("meta", f"构建根目录 {cfg.resolved_root()}")
        self.build.log("meta", f"输出目录   {Path(cfg.resolved_outdir())}")
        src = (f"联网下载（分支 {cfg.branch}"
               f"{'，每次 fetch 到最新' if cfg.refresh_sources else ''}）"
               if not cfg.zh_src.strip() and cfg.download_sources
               else f"本地 {cfg.zh_src or '(空)'}")
        self.build.log("meta", f"翻译源     {src}")
        if 11 in steps and not cfg.merge_pdf:
            self.build.log("warn", "步骤 9「合并成一册」未勾选，本轮不会生成合并册"
                                   "（勾上「⑤ 执行开关 → 步骤 9」再跑）")
        if 11 not in steps and cfg.merge_pdf:
            self.build.log("warn", "勾了「合并成一册」，但本轮步骤里没有步骤 9，"
                                   "合并会被跳过（把「起始步骤」调到 9 或更低）")
        if 12 in steps and (cfg.clean_mode or "none") == "none":
            self.build.log("meta", "步骤 10「清理过程文件」范围是「不清理」，本轮保留全部过程文件")

        self.worker = BuildWorker(cfg, steps)
        self.worker.sig_step_begin.connect(self.on_step_begin)
        self.worker.sig_step_end.connect(self.on_step_end)
        self.worker.sig_sub.connect(self.on_sub)
        self.worker.sig_log.connect(self.build.log)
        self.worker.sig_done.connect(self.on_done)
        self.worker.start()

        self.build.start_ts = time.monotonic()
        self.timer.start()
        self.build.btn_start.setEnabled(False)
        self.build.btn_stop.setEnabled(True)
        self.settings.setEnabled(False)
        self.build.lbl_state.setText("正在运行")
        self.build.lbl_state.setStyleSheet("color:#2f6feb")

    def start_multi(self, cfg: Config, vers: list[str]) -> None:
        """多版本并行：每个版本派生一份配置，在**多版本并行窗口**里各起一个进程。"""
        subs = [cfg.for_version(v) for v in vers]
        steps = _plan_steps(cfg)
        # ★ 并发预算：每个版本内部还会「几册同时编」。三个版本并行时如果不分，
        #   就是 3×6=18 个 latexmk 抢同一批核 —— 内存先炸（library 单册峰值 1 GB），
        #   反而比串行更慢。所以自动模式把这份预算按版本数**平分**。
        try:
            pinned = int(getattr(cfg, "jobs", 0) or 0)
        except (TypeError, ValueError):
            pinned = 0
        if pinned <= 0:
            cpu = os.cpu_count() or 4
            # 总预算 = 「核数-1」，但每个版本至少按单版本的上限（6）算 ——
            # 三个版本并行时不该让每个版本掉到 2 册并发（那样比串行还慢）。
            total = min(max(cpu - 1, 1), AUTO_JOBS_CAP * max(len(subs), 1))
            per = max(1, total // max(len(subs), 1))
            for c in subs:
                c.jobs = per
            jobs_note = (f"每个版本的册级并发：{per}"
                         f"（{cpu} 核 → 总并发 {total} ÷ {len(subs)} 个版本）")
        else:
            jobs_note = (f"每个版本的册级并发：{pinned}（你设定的）"
                         f"—— {len(subs)} 个版本 = 最多 {pinned * len(subs)} 个 xelatex 同时跑")
        lines: list[str] = []
        for c in subs:
            root = Path(c.resolved_root())
            try:
                root.mkdir(parents=True, exist_ok=True)      # ★ 先把文件夹建出来
            except OSError as e:
                QMessageBox.warning(self, "建不了目录",
                                    f"Python {c.version} 的构建根目录建不出来：\n"
                                    f"{root}\n\n{e}")
                return
            lines.append(f"Python {c.version}（{c.full_version()}）\n"
                         f"      解释器 {c.python}\n"
                         f"      目录   {root.name}")

        warn = (f"将**同时**运行 {len(subs)} 个版本（各一个进程、各用各的解释器）：\n\n  "
                + "\n  ".join(lines)
                + f"\n\n步骤：{'、'.join(STEP_BY_ROW[s][1] for s in steps)}"
                  f"（共 {len(steps)} 步）"
                  f"\n{jobs_note}")
        if 12 in steps and (cfg.clean_mode or "none") != "none":
            warn += ("\n\n⚠ 步骤 10 会删掉各版本的 cpython / venv / 翻译源"
                     "（成品 PDF 永远不删）。")
        if 11 in steps and not cfg.merge_pdf:
            warn += "\n\n步骤 9「合并成一册」没勾，不会生成合并册。"
        if QMessageBox.question(self, "多版本并行", warn + "\n\n确定同时开始？") \
                != QMessageBox.StandardButton.Yes:
            return

        self.cfg = cfg
        try:
            save_config(cfg)
        except OSError:
            pass
        # 主面板也留一行记录，免得「点了开始却没反应」的错觉
        self.build.log("step", f"多版本并行：{'、'.join(vers)}"
                               f"（已打开「多版本并行构建」窗口）")
        self.build.log("meta", "每个版本一个独立日志面板；关掉那个窗口才算这一轮结束。")

        self.multi = MultiRunWindow(subs, self)
        self.multi.show()
        self.multi.raise_()
        self.multi.activateWindow()
        self.multi.start_all()

    def on_stop(self) -> None:
        if self.worker and self.worker.isRunning():
            self.build.log("warn", "收到停止指令，正在结束当前命令……")
            self.worker.stop()
            self.build.btn_stop.setEnabled(False)

    # ------------------------------------------------------------ 回调
    def on_step_begin(self, row: int, title: str) -> None:
        self.build.set_row(row, "执行中")
        self.build.pb_step.setRange(0, 1)
        self.build.pb_step.setValue(0)
        self.build.lbl_cur.setText(title)
        done = sum(1 for r, _l, _t, _s in STEPS
                   if self.build.table.item(r, 1) and
                   self.build.table.item(r, 1).text() == "完成")
        self.build.pb_total.setValue(done)

    def on_step_end(self, row: int, ok: bool, summary: str, secs: float) -> None:
        self.build.set_row(row, "完成" if ok else "失败", human_dur(secs), summary)
        done = sum(1 for r, _l, _t, _s in STEPS
                   if self.build.table.item(r, 1) and
                   self.build.table.item(r, 1).text() == "完成")
        self.build.pb_total.setValue(done)
        self.build.pb_step.setValue(self.build.pb_step.maximum())

    def on_sub(self, row: int, done: int, total: int, label: str) -> None:
        self.build.pb_step.setRange(0, max(total, 1))
        self.build.pb_step.setValue(done)
        self.build.lbl_cur.setText(f"{label}　({done}/{total})")
        self.build.set_row(row, "执行中", "", f"{done}/{total} · {label}")

    def on_done(self, ok: bool, msg: str) -> None:
        self.timer.stop()
        self.build.btn_start.setEnabled(True)
        self.build.btn_stop.setEnabled(False)
        self.settings.setEnabled(True)
        secs = time.monotonic() - self.build.start_ts if self.build.start_ts else 0
        self.build.lbl_elapsed.setText(f"总用时 {human_dur(secs)}")
        if ok:
            self.build.lbl_state.setText("已完成")
            self.build.lbl_state.setStyleSheet("color:#1a7f37")
            self.build.log("ok", f"✔ {msg}")
        else:
            self.build.lbl_state.setText("已停止 / 失败")
            self.build.lbl_state.setStyleSheet("color:#cf222e")
            self.build.log("err", f"✘ {msg}")
        out = Path(self.cfg.resolved_outdir())
        if ok and self.cfg.open_outdir_when_done:
            open_in_explorer(out)
        if ok:
            QMessageBox.information(self, "完成", f"{msg}\n\n产物目录：{out}")
        else:
            QMessageBox.warning(self, "未完成", f"{msg}\n\n详细日志："
                                               f"{Path(self.cfg.resolved_root()) / 'gui-build.log'}")

    def _tick(self) -> None:
        if self.build.start_ts:
            self.build.lbl_elapsed.setText(
                f"已用时 {human_dur(time.monotonic() - self.build.start_ts)}")

    def on_open_log(self) -> None:
        p = Path(self.cfg.resolved_root()) / "gui-build.log"
        if p.is_file():
            open_in_explorer(p)
        else:
            QMessageBox.information(self, "还没有日志", f"{p} 尚未生成。")

    def closeEvent(self, ev) -> None:                            # noqa: N802
        if self.multi is not None and self.multi.isVisible():
            if not self.multi.close():          # 它自己会问「还在跑，确定停？」；用户取消 → False
                ev.ignore()
                return
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, "还在运行", "构建还没结束，确定退出？") \
                    != QMessageBox.StandardButton.Yes:
                ev.ignore()
                return
            self.worker.stop()
            self.worker.wait(4000)
        ev.accept()


# ---------------------------------------------------------------------------
# 6.5 入口
# ---------------------------------------------------------------------------

def run_cli(cfg: Config, rep=None) -> int:
    only = cfg.only_set()
    steps = ([s[0] for s in STEPS if s[0] in only] if only
             else [s[0] for s in STEPS if s[0] >= cfg.from_step])
    rep = rep if rep is not None else ConsoleReporter(cfg.verbose_log)
    rep.log(f"[命令行模式] 版本 Python {cfg.version}（{cfg.full_version()}）"
            f"　将执行 {len(steps)} 个步骤："
            f"{'、'.join(STEP_BY_ROW[s][1] for s in steps)}", "step")
    rep.log(f"[命令行模式] 构建根目录 {cfg.resolved_root()}", "meta")
    try:
        ok, msg = Pipeline(cfg, rep).main(steps)
    except Cancelled:
        ok, msg = False, "已停止"
    except KeyboardInterrupt:
        ok, msg = False, "被 Ctrl-C 中断"
    if isinstance(rep, JsonReporter):
        # 多版本并行：结论也走结构化，父进程据此给面板变绿/变红
        rep.done(ok, msg)
    else:
        print("\n" + _cli_paint(("✔ " if ok else "✘ ") + msg, "1;32" if ok else "1;31"))
    return 0 if ok else 1


#: 界面/日志里当装饰用的符号 —— 在**中文 Windows 的控制台**（ANSI 代码页 = GBK/cp936）
#: 里编不出来，会让 `print()` 直接抛 `UnicodeEncodeError`。
#: 实测：`↳ 退出码 0，用时 1s` 在 exe `--cli` 下把整个步骤 7b 崩成退出码 127，
#: 而日志里的内容是**成功**的 —— 用户看到的就是「明明跑对了却报错退出」。
#: （GBK 能编 `→ ● · ——`，编不了 `↳ ✔ ✘ ⚠`；这里只给编不出来的那些准备替身。）
_SYMBOL_ASCII = {
    "✔": "[OK] ", "✓": "[OK] ", "✘": "[X] ", "✗": "[X] ",
    "↳": "-> ", "⚠": "[!] ", "✅": "[OK] ", "❌": "[X] ",
}


class _TolerantStream:
    """给 `sys.stdout` 包一层：**写失败就当成功、编不出来的符号换成 ASCII**。

    ★ 场景一：`exe --check | head -14` —— 读者读够就走，管道被关掉。
      再 `print(..., flush=True)` 就是 `OSError: [Errno 22] Invalid argument`
      （Windows 上「写一个已关闭的管道」长这样），于是整个 `--check` 崩掉，
      还会写出一份 `gui-startup-error.log`，看着像「程序一启动就坏」。
    ★ 场景二：中文 Windows 的控制台/管道编码是 **GBK**（不是 UTF-8），
      `print("↳ …")` → `UnicodeEncodeError`，整条命令崩。**这一条真的炸过**：
      步骤 7b 干完活之后倒在打印那一行（`_ensure_streams()` 里的
      `reconfigure(errors=…)` 是第二道防线，这里先动手换成 ASCII 好读一些）。
    ★ 只吞 `OSError` / 处理 `UnicodeEncodeError`，其它异常照旧往外抛 —— 别把真问题藏了。
    """

    def __init__(self, inner) -> None:                 # noqa: ANN001
        self._inner = inner
        #: 先算一次「目标编码编不出来的符号」→ 替身。UTF-8 流上这张表是空的，
        #: 于是正常运行**一点额外开销都没有**。
        self._table: dict[str, str] = {}
        enc = getattr(inner, "encoding", None) or "utf-8"
        try:
            for ch, alt in _SYMBOL_ASCII.items():
                try:
                    ch.encode(enc)
                except (UnicodeEncodeError, LookupError):
                    self._table[ord(ch)] = alt
        except Exception:                              # noqa: BLE001
            self._table = {}

    def write(self, s: str) -> int:
        if self._table:
            s = s.translate(self._table)
        try:
            return self._inner.write(s)
        except OSError:
            return len(s)
        except UnicodeEncodeError:
            # 兜底：还有别的编不出来的字符 → 转义成 `\uXXXX`（可见、不丢信息）
            try:
                return self._inner.write(s.encode(
                    getattr(self._inner, "encoding", None) or "utf-8",
                    "backslashreplace").decode(
                    getattr(self._inner, "encoding", None) or "utf-8",
                    "replace"))
            except Exception:                          # noqa: BLE001
                return len(s)

    def flush(self) -> None:
        try:
            self._inner.flush()
        except OSError:
            pass

    def __getattr__(self, name: str):                  # encoding / fileno / …
        return getattr(self._inner, name)


def _ensure_streams() -> None:
    """保证 `sys.stdout` / `sys.stderr` 可写，返回去重后的日志路径（无则 None）。

    ★ `--windowed` 打包的 exe（或 pythonw 启动）**没有控制台**，Python 会把
      `sys.stdout` / `sys.stderr` 置成 `None`。而内置工具、`argparse` 的
      `--help`/报错都会 print —— 直接 `AttributeError: 'NoneType' object has
      no attribute 'write'`，看着像工具坏了，其实只是没地方写。
    这在 exe 里是**必经之路**：步骤 7 的 `makeindex-fix.py` 转发器就是以
    「无控制台」的方式把 exe 拉起来的（见 `_emit_makeindex_fix`）。
    ★ 接到文件而不是 devnull：这些输出是排查时唯一的线索，丢掉就白跑了。
    ★ 2026-10-06 补：**流存在也要处理**。中文 Windows 的控制台/管道编码是 GBK，
      `print("↳ …")` 会抛 `UnicodeEncodeError` 把整条命令崩掉（实测：步骤 7b
      做完全部工作后倒在打印那一行，退出码 127 —— 用户看到的是「明明成功了却报错」）。
      这里把错误处理器改成 `backslashreplace`：编不出来的字符退化成 `\u21b3`
      这样的可见转义，**永远不崩**。（`_TolerantStream` 还会先把符号换成 ASCII。）
    """
    for name in ("stdout", "stderr"):
        st = getattr(sys, name, None)
        if st is not None:
            try:
                st.reconfigure(errors="backslashreplace")
            except Exception:                        # noqa: BLE001
                pass
    if sys.stdout is not None and sys.stderr is not None:
        return None
    try:
        log = app_dir() / "tool-output.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        fh = log.open("a", encoding="utf-8", errors="replace")
    except Exception:                                # noqa: BLE001
        fh = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = fh
    if sys.stderr is None:
        sys.stderr = fh
    return log


def _tolerate_broken_output() -> None:
    """把 `sys.stdout` / `sys.stderr` 包成「写失败不崩」的版本。

    ★ 只给 `--tool` / `--cli` / `--check` 这几条**命令行**路径装：
      界面模式不需要（输出走 Qt 信号，不碰 stdio）。
    """
    if sys.stdout is not None:
        sys.stdout = _TolerantStream(sys.stdout)
    if sys.stderr is not None:
        sys.stderr = _TolerantStream(sys.stderr)


def main() -> int:
    # ★ 内置工具入口（tools/ 下那些转发器就走这里）——**必须在解析参数之前**，
    #   因为这条路径不读配置、也不要求 PyQt6。`--tool <名字> [工具自己的参数…]`
    _argv = sys.argv[1:]
    if _argv and _argv[0] == "--tool":
        _ensure_streams()      # ← windowed exe 下 sys.stdout 是 None，必须先兜住
        _tolerate_broken_output()          # 管道被提前关掉也不崩
        if len(_argv) < 2:
            print("用法：--tool <名字> [参数…]")
            print("可用：" + "、".join(sorted(BUILTIN_TOOLS)))
            return 2
        return run_builtin_tool(_argv[1], _argv[2:])

    ap = argparse.ArgumentParser(
        description="Python 中文文档分册 PDF 构建器（PyQt6 GUI / 命令行）")
    ap.add_argument("--cli", action="store_true", help="不开界面，直接在终端跑")
    ap.add_argument("--from", dest="from_step", type=int, default=None,
                    help="起始步骤行号 0..12")
    ap.add_argument("--only", dest="only", default=None,
                    help="只跑这些步骤，逗号分隔。按**步骤号**写（6 / 6b / 7 / 7b / 8 / "
                         "9 / 10），也接受行号兜底（11 = 步骤 9 合并、12 = 步骤 10）。"
                         "例：--only 6,6b、--only 11 --merge")
    ap.add_argument("--config", default=None, help="指定配置文件路径")
    ap.add_argument("--version", dest="version", default=None,
                    help="Python 版本 / 分支，如 3.13 / 3.14 / 3.15")
    ap.add_argument("--root", dest="root", default=None, help="构建根目录（覆盖配置）")
    ap.add_argument("--verbose", action="store_true", help="命令行模式显示完整输出")
    ap.add_argument("--merge", action="store_true",
                    help="步骤 9：把 38 册合并成一册（完整书签）")
    ap.add_argument("--merge-name", dest="merge_name", default=None,
                    help="步骤 9：合并册文件名（默认 Python <版本> 文档 <今天>.pdf）")
    ap.add_argument("--clean", choices=["none", "build", "all"], default=None,
                    help="步骤 10：跑完删掉过程文件。build = 只删构建中间件；"
                         "all = 连 cpython 源码 / venv / 翻译源 / 日志一起删")
    ap.add_argument("--check", action="store_true",
                    help="只打印配置并做步骤 0 的工具链检查，然后退出")
    ap.add_argument("--i18n-extra-url", dest="i18n_extra_url", default=None,
                    help="补充译文的更新地址（留空 = 只用内置那份）。"
                         "http(s) 地址（.json 结尾当清单、否则当目录前缀）、"
                         "file:// 或本机目录路径都支持")
    ap.add_argument("--books", default=None,
                    help="步骤 7：只编这几册（.tex 名，逗号分隔，如 reference,library）。"
                         "补稀疏路径 / 改一个 .rst 之后常用；留空 = 全编")
    ap.add_argument("--jobs", type=int, default=None,
                    help="步骤 7：同时编译几册（默认自动取 CPU 核数-1，上限 6）；"
                         "写 1 = 退回老的逐册串行（排查并发问题时用）")
    ap.add_argument("--json-log", dest="json_log", action="store_true",
                    help="（内部用）把每条日志编成一行 JSON 打到 stdout —— "
                         "多版本并行窗口靠它拿结构化的级别/进度，人不用管")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.from_step is not None:
        cfg.from_step = args.from_step
    if args.only:
        cfg.only_steps = args.only
    if args.version:
        cfg.version = args.version
        cfg.versions = [args.version]
        # ★ 版本换了，建 venv 的解释器也要跟着换 —— 否则会有
        #   「跑 3.15 的分支、却用 3.13 的解释器建 venv」这种事（步骤 0 会把
        #   它当成功报出来，因为解释器确实能用）。版本表里没有就保持原样。
        py = cfg.python_for(args.version)
        if py:
            cfg.python = py
    if args.root:
        cfg.root = args.root
    if args.verbose:
        cfg.verbose_log = True
    if args.merge:
        cfg.merge_pdf = True
    if args.merge_name is not None:
        cfg.merge_name = args.merge_name
    if args.clean is not None:
        cfg.clean_mode = args.clean
    if args.books is not None:
        cfg.books = args.books
    if args.jobs is not None:
        cfg.jobs = args.jobs
    if args.i18n_extra_url is not None:
        cfg.i18n_extra_url = args.i18n_extra_url

    if args.check or args.cli:
        # `--cli` / `--check` 是「本想在终端里看的」模式。打包成 windowed exe
        # 后终端里什么都看不到（sys.stdout 是 None）—— 兜住它并落到
        # <exe 所在目录>/tool-output.log，否则用户只会看到「双击没反应」。
        _ensure_streams()
        # ★ 多版本并行时子进程的输出要按 UTF-8 写管道：中文 Windows 的默认编码
        #   是 GBK，父进程按 UTF-8 解就会得到一片乱码（而且 JSON 里带中文）。
        #   必须在包 _TolerantStream 之前 reconfigure 真正的那个流。
        if args.json_log and sys.stdout is not None:
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:                                    # noqa: BLE001
                pass
        # 再包一层：`--check | head` 时管道会被提前关掉，写失败不该让整条命令崩。
        _tolerate_broken_output()
        if args.check:
            rep = ConsoleReporter(cfg.verbose_log)
            # 显示的是**真正加载的那份**——args.config 给了就别再报默认路径
            print(f"配置文件：{args.config or config_path()}")
            for k, v in asdict(cfg).items():
                print(f"  {k:<22} {v}")
            print(f"  {'→ 构建根目录':<22} {cfg.resolved_root()}")
            print(f"  {'→ 输出目录':<22} {cfg.resolved_outdir()}")
            p = Pipeline(cfg, rep)
            try:
                p.resolve_state()
                print(f"\n==> 步骤 0 前置检查")
                print("结果：" + p.step0())
                if cfg.zh_src.strip() and Path(cfg.zh_src).is_dir():
                    n = sum(1 for _ in Path(cfg.zh_src).rglob("*.po"))
                    print(f"本地翻译源 .po 数：{n}")
                else:
                    print(f"翻译源：联网下载 {cfg.url_zh()} 分支 {cfg.branch}")
                # ★ 镜像顺序 / 补译策略：一眼看清「会用哪个代理、有没有内置译文」
                urls = cfg.git_urls("python/cpython", cfg.cpython_url)
                print(f"GitHub 镜像（按顺序自动回退，共 {len(urls)} 个）：")
                for i, (name, url) in enumerate(urls, 1):
                    print(f"  {i}. {name:<14} {url}")
                if I18N_EXTRA:
                    print(f"内置补充译文：{len(I18N_EXTRA)} 个 .po")
                else:
                    print("补充译文：程序不内置正文译文（正文用上游 .po 实时更新），"
                          "只内置标题表 TITLES")
                if cfg.i18n_extra_url.strip():
                    print(f"额外补丁地址：{cfg.i18n_extra_url}")
                doc = Path(cfg.resolved_root()) / P_CPYTHON / "Doc"
                print(f"CPython Doc：{'已存在' if doc.is_dir() else '不存在'}")
                print(f"latex 目录：{'已存在' if (doc / 'build' / 'latex').is_dir() else '不存在'}")
                vp = p.resolve_venv()
                print(f"构建 venv  ：{vp}  {'（存在）' if Path(vp).is_file() else '（不存在，需跑步骤 4）'}")
                # ★ cairo 运行库 / cairosvg：只有文档里真有 `.. image:: *.svg` 时才必需，
                #   但缺了会让整个 sphinx-build 退出码 2（见 step6 的说明），所以这里也报。
                print(f"cairo 运行库：{p.cairo_dir or '（未在常见位置找到）'}")
                if Path(vp).is_file():
                    p.vp = Path(vp)
                    ok, why = p._cairo_probe()
                    print(f"cairosvg  ：{'可用' if ok else '不可用 —— ' + why[:80]}")
                out = Path(cfg.resolved_outdir())
                print(f"输出目录   ：{out}  {'（存在）' if out.is_dir() else '（不存在，步骤 8 会建）'}")
                return 0
            except Fail as e:
                print("\n" + _cli_paint(f"[错误] {e}", "1;31"))
                return 2
        return run_cli(cfg, JsonReporter(cfg.verbose_log) if args.json_log
                       else ConsoleReporter(cfg.verbose_log))

    # 走到这里就是要开界面了 —— 这时才要求 PyQt6
    if QT_ERROR:
        print(f"缺少图形界面依赖：{QT_ERROR}", file=sys.stderr)
        print("请先安装：pip install PyQt6\n"
              "（只是不想开界面、要跑全流程的话不需要它：\n"
              "  python pdf_builder_multi.py --cli）", file=sys.stderr)
        return 3

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    f = QFont("Microsoft YaHei UI", 9)
    app.setFont(f)
    app.setStyleSheet(QSS)
    win = MainWindow(cfg)
    win.show()
    return app.exec()


def _install_excepthook() -> None:
    """界面是用 pythonw / windowed exe 起的、没有控制台，异常必须落盘 + 弹窗。

    ★ 日志位置用 `app_dir()`（exe 旁边），不是 `__file__` —— 后者在打包后
      指向临时解压目录，用户既找不到、也留不住。
    """
    def hook(t, v, tb):
        import traceback
        text = "".join(traceback.format_exception(t, v, tb))
        log = app_dir() / "gui-startup-error.log"
        try:
            log.write_text(text, encoding="utf-8")
        except Exception:
            pass
        try:
            QMessageBox.critical(None, "出错了",
                                 f"{t.__name__}: {v}\n\n完整堆栈已写入：\n{log}")
        except Exception:
            print(text, file=sys.stderr)
    sys.excepthook = hook


if __name__ == "__main__":
    _install_excepthook()
    raise SystemExit(main())
