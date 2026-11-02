#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Linux / WSL 专用入口 —— 把构建器搬到 POSIX 上跑，**不改动 pdf_builder_multi.py 一个字节**。

为什么要单独一个脚本
--------------------
Sphinx 的并行只在 POSIX 上有效：

    # sphinx/util/parallel.py
    parallel_available = HAS_MULTIPROCESSING and os.name == 'posix'
    context = multiprocessing.get_context('fork')      # Windows 没有 fork

也就是说 Windows 上 `-j N` 对「读入 553 篇 + 套 9 万条译文」这一段**完全无效**
（实测每版只占 0.95 个核，三版合计 2.87 / 18 核），这一段要 20~29 分钟，是总时长的
主要部分。Linux 上 `-j 4~6` 能把它压到 4~6 分钟 —— 这就是移植的全部动机。

但主程序里有一小撮地方是 Windows 专有的（默认解释器路径、TeX Live 目录、`python`
这个名字的存在性）。与其去改那份「唯一实现」（项目约定：只允许一份实现，改错一处
静默失败），这里改成**继承 + 只覆盖胶水层**：

    pdf_builder_multi.py   ← 原样导入，一行不改（唯一实现仍在它那儿）
        └─ LinuxPipeline   ← 本文件，只覆盖 3 个方法

覆盖清单（就这三个）：
  1. `_make_env()`   Linux 要**保留**并强制 UTF-8 locale（Windows 那份是清掉 LC_*），
                     另外补一个 `python` 名字的软链（Ubuntu 24.04 起默认只有 python3）。
  2. `step0()`       在原有工具链检查前先把 `python` 别名准备好，检查逻辑一行不重写。
  3. `step4()`       父类建完 venv 后**重建一次 self.env** —— 父类的 env 是在
                     `__init__` 里算的，那时 venv 还不存在，PATH 里没有 venv/bin，
                     步骤 7 的 `python makeindex-fix.py` 就会去撞系统里另一个 Python。

其余一切（步骤 1~10、39 册命名表、索引修复、合并书签、验收报告）**全部复用原实现**。

用法
----
    # 0) 先体检（不动网络、不建目录），确认这台机器能不能跑
    python3 ci/linux/pdf_builder_linux.py --preflight --versions 3.13,3.14,3.15

    # 1) 单版本，全套
    python3 ci/linux/pdf_builder_linux.py --versions 3.15 --base ~/python-doc-build

    # 2) 三版本并行（一条命令，内部按版本各起一个子进程）
    python3 ci/linux/pdf_builder_linux.py --versions 3.13,3.14,3.15 --jobs 4 --merge

    # 3) 只重跑步骤 6 之后（前面已有产物时）
    python3 ci/linux/pdf_builder_linux.py --versions 3.15 --only 6,6b,7,7b,8,9

    # 4) 只想看解析出来的配置
    python3 ci/linux/pdf_builder_linux.py --versions 3.15 --print-config

    # 5) 国内本机、直连 github.com 不通时（改用镜像回退 + 清华 pip 源）
    python3 ci/linux/pdf_builder_linux.py --versions 3.15 --source auto \
        --pip-index https://pypi.tuna.tsinghua.edu.cn/simple

取源约定（`--source`）
----------------------
`github`（默认）= **只从 github.com 直连**，绝不试镜像站。这是为 CI 定的：
GitHub 的 runner 到 github.com 走机房内网，比任何第三方加速都快、也更可信；
主程序那套 `GH_MIRRORS` 是给「国内机器直连不通」准备的，在 runner 上只会白等超时。
国内本地跑请显式加 `--source auto`。

约定
----
* 产物落在 `--base` 下的 `Python <完整版本> PDF 文档 <YYYYMMDD>/`，与 Windows 版一致
  （命名规则仍是主程序里那份 `name_map`，这里不另立一套）。
* 判据仍然只看 ASCII 标记（`MISSING n` / `UNPRODUCED n` / `OK` / `FAIL`），别匹配中文。
* 本脚本**不联网下载自身**、不写系统目录，失败只返回非零退出码 + 明确的一行原因。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

# ---------------------------------------------------------------------------
# 一、把主程序当库导入（不做任何修改）
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parents[2]
GUI_DIR = Path(os.environ.get("PDFBUILD_GUI_DIR") or (REPO / "sphinx-pdf" / "gui"))
if str(GUI_DIR) not in sys.path:
    sys.path.insert(0, str(GUI_DIR))

import pdf_builder_multi as M          # noqa: E402  （必须在 sys.path 调整之后）

IS_POSIX = os.name == "posix"

#: 体检结论用的机器判据（只认 ASCII，方便 grep / CI 判断）
OK, WARN, MISS = "OK", "WARN", "MISSING"

#: 解释器版本输出必须长这样，否则一律当「没拿到」（防坏 shim 的错误信息被当成版本号）
_VERSION_RE = re.compile(r"\d+\.\d+\.\d+")


def say(msg: str = "") -> None:
    """往终端打一行；打不出去不算失败（`| head` 会提前关管道）。"""
    try:
        print(msg, flush=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 二、解释器探测：版本 → 本机真实存在的 python
# ---------------------------------------------------------------------------
def _ver_tuple(text: str) -> tuple[int, int] | None:
    """从 `Python 3.13.18` / `3.13.18` 里取出 (3, 13)。"""
    out: list[int] = []
    for tok in str(text or "").replace("Python", " ").replace(".", " ").split():
        if tok.isdigit() and len(out) < 2:
            out.append(int(tok))
        elif out:
            break
    return (out[0], out[1]) if len(out) == 2 else None


def interpreter_version(py: str) -> str:
    """问解释器要版本号；拿不到（或输出不是版本号）就返回空串，不抛异常。

    ★ 为什么要校验格式：Windows 上 `python3.14.exe` 常常只是个 **shim**
      （chocolatey / 应用商店的占位符），跑起来会把
      `Cannot find file at 'c:\\python314\\python.exe'` 打到 stdout 并返回非零。
      不校验就会把这个错误信息当成"版本号"，后面 `--python-map` 指过去直接崩。
    """
    if not py or not Path(py).exists():
        return ""
    try:
        r = subprocess.run([py, "-c", "import sys;print('%d.%d.%d' % sys.version_info[:3])"],
                           capture_output=True, text=True, timeout=30)
        out = (r.stdout or "").strip()
        return out if _VERSION_RE.fullmatch(out) else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def find_interpreter(ver: str, mapping: dict[str, str] | None = None) -> str:
    """给 `3.13` 找一个真的是 3.13 的解释器。

    顺序：显式映射（`--python-map 3.13=/opt/py313/bin/python`）→ 环境变量
    `PDFBUILD_PY313` → PATH 上的 `python3.13` / `python313` → 常见安装位置
    → 跑得起来但版本不符的那个 → 最后才退回 `sys.executable`（此时完整版本号会
    退成 `3.13.0`，preflight 会明确报警）。

    ★ 为什么不用「同一个解释器凑合」：PDF 文件名与合并册名里要写**完整版本号**
      （`Python 3.13.18 文档 20261030.pdf`），那是问解释器得来的，不是猜的。
    ★ 为什么最后不看「第一个候选」：PATH 上可能有坏 shim（见
      `interpreter_version` 的注释），选它等于制造一个莫名其妙的失败。
    """
    want = _ver_tuple(ver)
    cands: list[str] = []
    if mapping and mapping.get(ver):
        cands.append(mapping[ver])
    env_key = "PDFBUILD_PY" + str(ver).replace(".", "")
    if os.environ.get(env_key):
        cands.append(os.environ[env_key])
    for name in (f"python{ver}", "python" + str(ver).replace(".", "")):
        w = shutil.which(name)
        if w:
            cands.append(w)
    for p in (f"/usr/bin/python{ver}", f"/usr/local/bin/python{ver}",
              f"/opt/python/{ver}/bin/python3"):
        if Path(p).exists():
            cands.append(p)

    probed = [(c, interpreter_version(c)) for c in cands]
    for c, got in probed:                 # ① 版本完全对得上
        if got and _ver_tuple(got) == want:
            return c
    for c, got in probed:                 # ② 跑得起来，只是版本不对
        if got:
            return c
    return sys.executable                 # ③ 都不行 → 至少能跑


# ---------------------------------------------------------------------------
# 三、平台胶水层：只覆盖 3 个方法
# ---------------------------------------------------------------------------
class LinuxPipeline(M.Pipeline):
    """在 POSIX 上跑得起来的 Pipeline（其余逻辑一律继承）。"""

    # ---------------------------------------------------------------- locale
    @staticmethod
    def _utf8_locale() -> str:
        """挑一个本机真的存在的 UTF-8 locale。

        ★ 为什么不能像 Windows 那样直接清掉 LC_*：Windows 的问题是「Perl 按 locale
          解释文件名 + 文件 API 走 ANSI 代码页」，所以清掉最安全。Linux 相反 ——
          `LANG=C`（POSIX 默认）下 xelatex / perl 会把中文文件名按字节硬拼，
          某些版本的 fontconfig 还会拒绝非 UTF-8 的路径。所以这里**要钉一个
          UTF-8 locale**，顺序：已有 UTF-8 的现成值 → C.UTF-8 → en_US.UTF-8。
        """
        for k in ("LC_ALL", "LC_CTYPE", "LANG"):
            v = (os.environ.get(k) or "").strip()
            if "utf" in v.lower() or "UTF" in v:
                return v
        try:
            avail = subprocess.run(["locale", "-a"], capture_output=True,
                                   text=True, timeout=10).stdout or ""
        except (OSError, subprocess.SubprocessError):
            avail = ""
        for want in ("C.utf8", "C.UTF-8", "en_US.utf8", "en_US.UTF-8"):
            if want.lower() in avail.lower():
                return want
        return "C.UTF-8"

    def _make_env(self) -> dict[str, str]:
        env = super()._make_env()           # ← 原实现（剥 _PYI*、拼 PATH、LATEXOPTS…）
        if not IS_POSIX:
            return env
        loc = self._utf8_locale()
        env["LANG"] = loc
        env["LC_ALL"] = loc
        env.setdefault("LC_CTYPE", loc)
        # ★ CI 里 HOME 可能不可写（容器以别的用户跑），TeX 的缓存目录会炸：
        #   把 TEXMFVAR / TEXMFCACHE 指到构建根里，保证一定可写。
        cache = Path(self.root) / ".texmf-var"
        try:
            cache.mkdir(parents=True, exist_ok=True)
            env.setdefault("TEXMFVAR", str(cache))
            env.setdefault("TEXMFCACHE", str(cache))
        except OSError:
            pass
        return env

    # ---------------------------------------------------------------- python 别名
    def _ensure_python_alias(self) -> str:
        """保证子进程里 `python` 这个名字能解析到解释器，返回软链所在目录。

        ★ 为什么必须有：步骤 7 里 latexmk 执行的是
          `python makeindex-fix.py …`（venv 路径可能含空格/中文，且 latexmk 的
          `-e` 只接受一段命令字符串，写全路径会踩引号/编码）。Ubuntu 24.04 起因
          PEP 394 收紧了默认安装，系统里**只有 `python3`、没有 `python`** ——
          真跑起来就是 latexmk：`python: not found`、索引静默不修。
          这里在 `<root>/.pyshim/python` 放一个软链，只影响本程序起的子进程。
        """
        if not IS_POSIX:
            return ""
        if shutil.which("python", path=self.env.get("PATH", "")):
            return ""                        # 已经有了（venv/bin 或系统），不画蛇添足
        target = Path(self.python or sys.executable)
        if not target.exists():
            return ""
        d = Path(self.root) / ".pyshim"
        try:
            d.mkdir(parents=True, exist_ok=True)
            link = d / "python"
            if link.is_symlink() or link.exists():
                try:
                    if link.resolve() == target.resolve():
                        return str(d)
                except OSError:
                    pass
                link.unlink()
            try:
                link.symlink_to(target)
            except OSError:
                # 有些文件系统（Docker 卷、SMB 挂载）不允许软链：退化成一个
                # 三行的 shell 包装器。功能一样，只是多一次 exec。
                link.write_text(f'#!/bin/sh\nexec "{target}" "$@"\n', encoding="utf-8")
                link.chmod(0o755)
            return str(d)
        except OSError as e:                 # 无权限 / 只读
            say(f"[warn] 无法建立 python 别名（{e}），步骤 7 的索引修复可能失败")
            return ""

    def _apply_python_alias(self) -> None:
        d = self._ensure_python_alias()
        if d:
            path = self.env.get("PATH", "")
            if d not in path.split(os.pathsep):
                # ★ 放**末尾**：venv/bin 在前面，优先用 venv 里的 python
                self.env["PATH"] = path + os.pathsep + d if path else d

    # ---------------------------------------------------------------- 覆盖点 1
    def step0(self) -> str:
        self._apply_python_alias()
        return super().step0()               # 原检查逻辑一行不重写

    # ---------------------------------------------------------------- 覆盖点 2
    def step4(self) -> str:
        try:
            return super().step4()
        finally:
            # ★ 父类的 self.env 是 __init__ 里算的，那时 venv 还不存在 ——
            #   不重建的话 PATH 里没有 venv/bin，步骤 7 的 `python` 会解析到别处。
            self.env = self._make_env()
            self._apply_python_alias()


# ---------------------------------------------------------------------------
# 三·五、POSIX 修补：makeindex-fix.py 里写死的 Windows 专属参数
# ---------------------------------------------------------------------------
# ★★ 2026-11-02 查到的真根因（CI 上「每册都失败」的真凶，查了一整天才挖出来）★★
#
#   现象（第 7 步）：每册 `latexmk 退出码 12`、PDF 里没有索引、`.ind` 一个都没有，
#   而 `<册>.log` 里**一条 LaTeX 错误都没有** —— 典型的「静默失败」，判据全绿。
#
#   真话在 latexmk 的转录里（`python` 跑 makeindex-fix.py 时崩了）：
#       Run number 1 of rule 'makeindex <册>.idx'
#       Running 'python makeindex-fix.py -s python.ist -o "<册>.ind" "<册>.idx"'
#       Traceback (most recent call last):
#         File ".../makeindex-fix.py", line 550, in fidx_main
#           rc = subprocess.run(cmd, creationflags=CREATE_NO_WINDOW).returncode
#       ValueError: creationflags is only supported on Windows platforms
#       Collected error summary:
#         makeindex <册>.idx: Command for 'makeindex <册>.idx' gave return code 256
#       Latexmk: Errors, so I did not complete making targets
#
#   因果链：主程序 `_emit_makeindex_fix()` 释放的自包含脚本，文件头写死了
#       CREATE_NO_WINDOW = 0x08000000
#   → fix-index 段里 `subprocess.run(cmd, creationflags=CREATE_NO_WINDOW)` 在 POSIX
#     上直接抛 ValueError → python 退出码 1（latexmk 记成 256）→ latexmk 在
#     「第 2 遍之前的 makeindex 规则」上中止 → **只留下第 1 遍的 PDF**：
#     目录空白、满屏 ??、没有索引，但页面内容和 `.log` 看着都正常。
#   ⇒ 所以之前「没有 TeX 错误」的结论不是漏看，而是**根本没出错**：xelatex 单独跑
#     退出码是 0、PDF 页数也对（howto-argparse 13 页）。坏的是索引这一步。
#
#   ⚠️ 主程序里同名常量的定义本身是对的：
#        CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0
#      只是**释放出去那份脚本**把值写死了。项目约定不改 pdf_builder_multi.py，
#      所以在这里把它换成本平台的正确值（Windows 上行为一字不变，根本不会走到这里）。
#      上游若把那一行改成 f"CREATE_NO_WINDOW = {CREATE_NO_WINDOW}"，本函数自动失效。
def _patch_emitted_makeindex_fix(dest) -> None:
    """把释放出来的 makeindex-fix.py 里那行 Windows 常量改成本平台的值。"""
    try:
        txt = dest.read_text(encoding="utf-8")
    except OSError:
        return
    marker = "CREATE_NO_WINDOW = 0x08000000"
    if marker not in txt:
        return          # 已经是平台相关写法（上游改过了）→ 什么都不做，保持幂等
    out = []
    for ln in txt.splitlines(keepends=True):
        if ln.startswith(marker):
            ln = ("CREATE_NO_WINDOW = 0                  "
                  "# POSIX：该参数只对 Windows 有意义\n")
        out.append(ln)
    dest.write_text("".join(out), encoding="utf-8")
    say("[fix] makeindex-fix.py：CREATE_NO_WINDOW 0x08000000 → 0"
        "（Windows 专属参数，POSIX 上传给 subprocess 会抛 ValueError）")


if IS_POSIX:
    _orig_emit_makeindex_fix = M._emit_makeindex_fix

    def _emit_makeindex_fix_posix(dest) -> None:
        # step7 里是 `_emit_makeindex_fix(...)` 的**模块全局**调用，所以这里换掉
        # 模块属性即可生效，不用碰主程序一行代码。
        _orig_emit_makeindex_fix(dest)
        _patch_emitted_makeindex_fix(dest)

    M._emit_makeindex_fix = _emit_makeindex_fix_posix


# ---------------------------------------------------------------------------
# 四、配置：把 Windows 默认值换成本机真实路径
# ---------------------------------------------------------------------------
class DirectSourceConfig(M.Config):
    """所有源码/译文**只从 github.com 直连抓**，不试任何镜像站。

    为什么要在 CI 里这么做（用户 2026-11-02 要求）：
      · 这套流程现在跑在 GitHub 自己的 runner 上 —— 它到 github.com 走机房内网，
        比任何第三方加速镜像都快，而且**内容最可信**（镜像可能滞后几天，甚至被篡改）；
      · 主程序里的 `GH_MIRRORS`（ghproxy / gh-proxy / ghfast / xget …）是给
        「本机在国内、直连不通」的场景准备的：每条失败都要等 300 秒看门狗，
        在 runner 上纯属白等。
      · 想恢复「自动回退镜像」的行为：`--source auto`（本地 WSL 在国内时用）。
    """

    def git_urls(self, repo: str, explicit: str = "") -> list[tuple[str, str]]:
        url = (explicit or "").strip()
        if not url:
            gh = (self.gh or "").strip().rstrip("/") or "https://github.com"
            url = f"{gh}/{repo}"
        return [("github 直连", url)]


def build_config(args, base_dir: str) -> "M.Config":
    cfg = (DirectSourceConfig() if args.source == "github" else M.Config())
    cfg.versions = list(args.versions)
    cfg.version = args.versions[0]
    cfg.base_dir = base_dir

    # 解释器：一次算好整张表 —— 主程序的 full_version()/for_version() 都读它
    mapping = {}
    for spec in (args.python_map or []):
        if "=" in spec:
            k, v = spec.split("=", 1)
            mapping[k.strip()] = v.strip()
    cfg.version_pythons = {v: find_interpreter(v, mapping) for v in args.versions}
    cfg.python = cfg.version_pythons[cfg.version]

    # TeX Live：Linux 上通常就在 PATH 里；显式给了才设（主程序会优先用它）
    cfg.texlive_bin = (args.texlive_bin or "").strip()

    # 取源地址：github = **只用直连**（CI 默认）／auto = 沿主程序的镜像回退表
    if args.source == "github":
        cfg.gh = (args.gh or "https://github.com").strip()
        cfg.cpython_url = ""          # 空 = <gh>/python/cpython.git
        cfg.zh_url = ""
    else:
        cfg.gh = (args.gh or "").strip()

    # pip 源：不设镜像站（CI 直连 PyPI 最快）；国内本地可 --pip-index 清华源
    cfg.pip_index = (args.pip_index or "https://pypi.org/simple").strip()
    cfg.lang = args.lang
    cfg.jobs = args.jobs

    cfg.only_steps = args.only or ""
    cfg.from_step = args.from_step or 0
    cfg.merge_pdf = not args.no_merge
    cfg.gen_report = not args.no_report
    cfg.build_html = args.build_html
    cfg.clean_mode = args.clean
    cfg.keep_build_dir = args.keep_build
    if args.i18n_extra_url is not None:
        cfg.i18n_extra_url = args.i18n_extra_url
    if args.root:
        cfg.root = args.root
        cfg.outdir = args.outdir or args.root
    return cfg


def pick_steps(cfg) -> list[int] | None:
    """`--only` 优先（按步骤号解析，主程序自带 `only_set()`）；否则从 `--from` 起。"""
    only = cfg.only_set()
    if only:
        return sorted(only)
    steps = [row for row, *_ in M.STEPS if row >= cfg.from_step]
    return steps or None


# ---------------------------------------------------------------------------
# 五、体检（不联网、不建大目录）
# ---------------------------------------------------------------------------
def preflight(args, base_dir: str) -> int:
    rows: list[tuple[str, str, str]] = []

    def add(level: str, name: str, detail: str) -> None:
        rows.append((level, name, detail))

    add(OK if IS_POSIX else WARN, "平台",
        f"os.name={os.name}" + ("" if IS_POSIX else "（非 POSIX：本次只做体检，-j 不会生效）"))

    add(OK if shutil.which("git") else MISS, "git",
        shutil.which("git") or "未找到，apt install git")

    for tool in ("latexmk", "xelatex", "makeindex", "pdfinfo", "pdffonts"):
        w = shutil.which(tool) or (str(Path(args.texlive_bin) / tool)
                                   if args.texlive_bin and (Path(args.texlive_bin) / tool).exists()
                                   else "")
        hint = {
            "latexmk": "texlive-latex-extra",
            "xelatex": "texlive-xetex",
            "makeindex": "texlive-binaries",
            "pdfinfo": "poppler-utils",
            "pdffonts": "poppler-utils",
        }.get(tool, "texlive")
        add(OK if w else MISS, tool, w or f"未找到，apt install {hint}")

    for ver in args.versions:
        py = find_interpreter(ver)
        got = interpreter_version(py)
        if not got:
            add(MISS, f"python {ver}", f"找不到解释器（试过 python{ver} / python3{ver}）")
        elif _ver_tuple(got) == _ver_tuple(ver):
            add(OK, f"python {ver}", f"{py} → {got}")
        elif Path(py) == Path(sys.executable):
            add(WARN, f"python {ver}",
                f"没有可用的 {ver} 解释器，退回当前解释器（{got}）："
                f"PDF 名会退成 {ver}.0；装一个 python{ver} 或用 --python-map 指定")
        else:
            add(WARN, f"python {ver}",
                f"{py} → {got}（版本不符：PDF 名会退成 {ver}.0）")

    # cairo：cairosvg 编 3.14/3.15 的 .svg 插图时要
    if not IS_POSIX:
        add(OK, "libcairo", "非 POSIX：由主程序 find_cairo_dir() 自己找，这里不判")
    else:
        try:
            import ctypes.util
            lib = ctypes.util.find_library("cairo")
            add(OK if lib else MISS, "libcairo",
                lib or "未找到，apt install libcairo2（3.14/3.15 有 svg 插图，缺了步骤 6 会失败）")
        except Exception as e:                          # noqa: BLE001
            add(WARN, "libcairo", f"探测失败：{e}")

    loc = LinuxPipeline._utf8_locale()
    add(OK if "utf" in loc.lower() else WARN, "locale", loc)

    # 磁盘：每册 PDF 约 50~90 MB，三版本 + 中间产物至少 8 GB
    try:
        target = Path(base_dir)
        while not target.exists() and target != target.parent:
            target = target.parent
        free_gb = shutil.disk_usage(target).free / 1e9
        add(OK if free_gb >= 8 else WARN, "磁盘",
            f"{target} 可用 {free_gb:.1f} GB" + ("" if free_gb >= 8 else "（建议 ≥ 8 GB）"))
    except OSError as e:
        add(WARN, "磁盘", f"取不到：{e}")

    cpus = os.cpu_count() or 1
    try:
        mem_gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
    except (ValueError, OSError, AttributeError):
        mem_gb = 0.0
    add(OK if cpus >= 4 else WARN, "CPU", f"{cpus} 核（步骤 6 的 -j 与步骤 7 的册级并发都看它）")
    if mem_gb:
        add(OK if mem_gb >= 8 else WARN, "内存", f"{mem_gb:.1f} GB")

    add(OK, "主程序", f"{Path(M.__file__).name} @ {GUI_DIR}")

    width = max(len(r[1]) for r in rows) + 2
    say("")
    say("=" * 70)
    say("Linux 构建环境体检")
    say("=" * 70)
    for level, name, detail in rows:
        say(f"  [{level:^7}] {name:<{width}} {detail}")
    fails = [r for r in rows if r[0] == MISS]
    say("=" * 70)
    say(f"结论：{len(rows) - len(fails)} 项通过，{len(fails)} 项致命缺失")
    if fails:
        say("缺的东西（按上面的提示 apt install 即可）：" +
            "、".join(r[1] for r in fails))
        return 1
    say("可以开始构建。示例：")
    say(f"  python3 {Path(__file__).name} --versions {','.join(args.versions)} "
        f"--jobs 4 --merge")
    return 0


# ---------------------------------------------------------------------------
# 六、构建（单版本；多版本时按版本各起一个子进程）
# ---------------------------------------------------------------------------
def run_one(args, ver: str, base_dir: str) -> int:
    cfg = build_config(_one_version_args(args, ver), base_dir)
    rep = M.ConsoleReporter(args.verbose)
    pipe = LinuxPipeline(cfg, rep)

    steps = pick_steps(cfg)
    say("")
    say(f"===== Python {ver} → {pipe.root}")
    say(f"      解释器   {cfg.python}")
    say(f"      TeX Live {cfg.texlive_bin or '(用 PATH)'}")
    say(f"      步骤     {steps if steps else '全部'}")
    say(f"      并发     {cfg.jobs or 'auto'}"
        f"（Linux 上 -j 与册级并发都吃这个值）")
    t0 = time.monotonic()
    ok, msg = pipe.main(steps)
    say(f"===== Python {ver} {'完成' if ok else '失败'}（{M.human_dur(time.monotonic() - t0)}）{msg}")
    return 0 if ok else 1


def _one_version_args(args, ver: str):
    """派生一份「只管这个版本」的参数（多版本扇出时用）。"""
    import copy
    a = copy.copy(args)
    a.versions = [ver]
    a.root = args.root if len(args.versions) == 1 else None
    a.outdir = None
    return a


def fan_out(args, base_dir: str) -> int:
    """多版本时：每个版本一个子进程，限制并发，输出直接透到父进程终端。"""
    vers = list(args.versions)
    limit = max(1, int(args.parallel or len(vers)))
    pending, running, failed = list(vers), [], []

    def spawn(v: str):
        cmd = [sys.executable, str(Path(__file__).resolve()),
               "--_child", "--versions", v, "--base", base_dir,
               "--lang", args.lang, "--clean", args.clean]
        if args.jobs:
            cmd += ["--jobs", str(args.jobs)]
        if args.only:
            cmd += ["--only", args.only]
        if args.from_step:
            cmd += ["--from", str(args.from_step)]
        if args.no_merge:
            cmd.append("--no-merge")
        if args.no_report:
            cmd.append("--no-report")
        if args.build_html:
            cmd.append("--build-html")
        if args.keep_build:
            cmd.append("--keep-build")
        if args.texlive_bin:
            cmd += ["--texlive-bin", args.texlive_bin]
        if args.pip_index:
            cmd += ["--pip-index", args.pip_index]
        if args.gh:
            cmd += ["--gh", args.gh]
        cmd += ["--source", args.source]
        for spec in (args.python_map or []):
            cmd += ["--python-map", spec]
        if args.verbose:
            cmd.append("--verbose")
        say(f"[fan-out] 启动 {v}：{' '.join(cmd[1:4])} …")
        return v, subprocess.Popen(cmd, env=os.environ.copy(),
                                   start_new_session=IS_POSIX)

    try:
        while pending or running:
            while pending and len(running) < limit:
                running.append(spawn(pending.pop(0)))
            time.sleep(1.0)
            for item in list(running):
                v, proc = item
                if proc.poll() is not None:
                    running.remove(item)
                    say(f"[fan-out] {v} 结束，退出码 {proc.returncode}")
                    if proc.returncode != 0:
                        failed.append(v)
    except KeyboardInterrupt:
        say("\n[fan-out] 收到中断，正在结束所有子进程……")
        for _v, proc in running:
            try:
                if IS_POSIX:
                    os.killpg(os.getpgid(proc.pid), 9)
                else:
                    proc.kill()
            except OSError:
                pass
        return 130

    if failed:
        say(f"[fan-out] 失败版本：{'、'.join(failed)}")
        return 1
    say("[fan-out] 全部版本成功")
    return 0


# ---------------------------------------------------------------------------
# 七、命令行
# ---------------------------------------------------------------------------
def default_base() -> str:
    return (os.environ.get("PDFBUILD_BASE")
            or str(Path.home() / "python-doc-build"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="pdf_builder_linux.py",
        description="Python 中文文档分册 PDF 构建器 · Linux/WSL 入口"
                    "（不改动 pdf_builder_multi.py）")
    ap.add_argument("--versions", default="3.14",
                    help="要构建的版本，逗号分隔，如 3.13,3.14,3.15（默认 3.14）")
    ap.add_argument("--base", default=None,
                    help=f"基准目录（默认 $PDFBUILD_BASE 或 {default_base()}）")
    ap.add_argument("--root", default=None, help="直接指定构建根（只允许单版本）")
    ap.add_argument("--outdir", default=None, help="PDF 输出目录（默认同构建根）")
    ap.add_argument("--only", default=None,
                    help="只跑这些步骤（步骤号，如 6,6b,7,7b,8,9）")
    ap.add_argument("--from", dest="from_step", type=int, default=None,
                    help="从第几步开始（步骤号 0~10）")
    ap.add_argument("--jobs", type=int, default=4,
                    help="并发数：步骤 6 的 sphinx -j 与步骤 7 的册级并发共用（默认 4）")
    ap.add_argument("--parallel", type=int, default=0,
                    help="多版本时同时跑几个（默认全部同时）")
    ap.add_argument("--lang", default="zh_CN", help="目标语言（默认 zh_CN）")
    ap.add_argument("--texlive-bin", default="", help="TeX Live 的 bin 目录（默认用 PATH）")
    ap.add_argument("--python-map", action="append", metavar="VER=PATH",
                    help="指定某版本用哪个解释器，可重复：--python-map 3.13=/opt/py313/bin/python")
    ap.add_argument("--pip-index", default="", help="pip 源（CI 建议 https://pypi.org/simple）")
    ap.add_argument("--gh", default="",
                    help="GitHub 前缀（--source github 时默认 https://github.com）")
    ap.add_argument("--source", default="github", choices=["github", "auto"],
                    help="源码/译文从哪取：github=只走 github.com 直连（CI 用，默认）；"
                         "auto=主程序那套镜像自动回退（国内本地直连不通时用）")
    ap.add_argument("--i18n-extra-url", default=None, help="补充译文地址（默认不打补丁）")
    ap.add_argument("--clean", default="none", choices=["none", "build", "all"],
                    help="步骤 10 清理范围（默认 none：CI 要留日志给验收报告）")
    ap.add_argument("--no-merge", action="store_true", help="不生成合并册（步骤 9）")
    ap.add_argument("--no-report", action="store_true", help="不生成验收报告（步骤 8）")
    ap.add_argument("--build-html", action="store_true", help="额外构建 HTML（步骤 5）")
    ap.add_argument("--keep-build", action="store_true", help="保留 build/（增量构建）")
    ap.add_argument("--preflight", action="store_true", help="只体检环境，不构建")
    ap.add_argument("--print-config", action="store_true", help="打印解析后的配置（JSON）")
    ap.add_argument("--verbose", action="store_true", help="显示 sphinx/latexmk 全部输出")
    ap.add_argument("--_child", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    args.versions = [v.strip() for v in str(args.versions).split(",") if v.strip()]
    if not args.versions:
        say("--versions 不能为空")
        return 2
    base_dir = args.base or default_base()

    if args.preflight:
        return preflight(args, base_dir)

    if args.print_config:
        cfg = build_config(_one_version_args(args, args.versions[0]), base_dir)
        pipe = LinuxPipeline(cfg, M.ConsoleReporter(False))
        info = {k: v for k, v in asdict(cfg).items()}
        info["_resolved"] = {"root": str(pipe.root), "outdir": str(pipe.outdir),
                             "tools_dir": str(pipe.tools), "steps": pick_steps(cfg)}
        say(json.dumps(info, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.root and len(args.versions) > 1:
        say("--root 只能配单版本（多版本时各版本必须各占一个目录，否则会互相覆盖）")
        return 2

    if len(args.versions) > 1 and not args._child:
        return fan_out(args, base_dir)
    return run_one(args, args.versions[0], base_dir)


if __name__ == "__main__":
    sys.exit(main())
