#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 `pdf_builder_multi.py` 打包成一个**可单独分发的 exe**（PyInstaller）。

    python build_exe.py                 # 默认 **onefile** → dist/PDF构建器-多版本.exe（单个文件）
    python build_exe.py --onedir        # 备选：目录形态 → dist/PDF构建器-多版本/（启动快）
    python build_exe.py --no-smoke      # 只打包
    python build_exe.py --venv D:\\x     # 换打包 venv 位置
    python build_exe.py --console       # 保留控制台（排查打包问题时用）

产物：
    onefile（默认）→ `dist/PDF构建器-多版本.exe`         ← **一个文件，拷到哪都能跑**
    onedir         → `dist/PDF构建器-多版本/`（目录）    ← 分发必须整个目录一起给

★★ 冒烟测试的核心判据（别再退化成「原地跑一下」）★★
  测试会把 exe **复制到一个全新的空目录**（没有 `_internal/`、没有源码、没有
  workspace）再运行。原地跑通过**不代表**单文件可用 —— onedir 的 exe 在
  `dist/PDF构建器-多版本/` 里跑得好好的，一拷出来就退出码 127。
  这就是 2026-10-06 那次「打包完成仍然出问题」的全部原因。

★★ 打包**不能**让程序不依赖外部环境 ★★
  exe 只把「界面 + 15 个后处理工具」合成一个文件。真正的构建链仍然要目标机器上有：
    · git          —— 稀疏克隆 cpython / 拉中文译文
    · TeX Live     —— xelatex / latexmk / makeindex（步骤 7）
    · 一个 Python  —— 步骤 4 要用它建**独立的**构建 venv 并 pip install sphinx
    · 网络         —— 克隆仓库 + pip
  也就是说：省掉的是「装 PyQt6 / 带一堆 .py」，不是「省掉 Python 和 TeX Live」。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = HERE / "pdf_builder_multi.spec"
REQUIREMENTS = HERE / "requirements.txt"
APP_NAME = "PDF构建器-多版本"
#: 唯一入口脚本（单版本版已退役，没有第二个入口了）。
DEFAULT_ENTRY = "pdf_builder_multi.py"

#: 打包用的 venv。跟 GUI 启动器同一个约定（都在 C:\pypdfbuild 下），
#: 但**刻意分开**：打包 venv 要多装一个 PyInstaller，不该污染运行用的那份。
DEFAULT_VENV = Path(r"C:\pypdfbuild\exe-venv")

#: pip 源，**按顺序试**。
#: ★ 必须留官方源兜底：实测清华源在这个 venv 里 `PyQt6` 会报
#:   `No matching distribution found`（首页 HTTP 200，但索引里没有可用文件），
#:   而官方 PyPI 正常。只配一个源 = 换台机器/换个镜像就可能直接装不上。
PIP_INDEXES = [
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://pypi.org/simple",
]

#: 建 venv 的解释器候选（与主程序 `_guess_python()` 同一套思路）。
BOOT_CANDIDATES = [
    r"C:\Users\zb137\.workbuddy\binaries\python\versions\3.13.12\python.exe",
    r"C:\Users\zb137\.workbuddy\binaries\python\versions\3.14.7\python.exe",
]


def find_bootstrap_python() -> str:
    """找「用来建 venv」的解释器。"""
    for c in BOOT_CANDIDATES:
        if Path(c).is_file():
            return c
    for name in ("python3", "python"):
        w = shutil.which(name)
        if w:
            return w
    raise SystemExit("找不到 Python 解释器 —— 先装 Python 3.11+ 并确保在 PATH 里")


def run(cmd: list[str], **kw) -> int:
    print("$ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], **kw).returncode


def ensure_venv(venv: Path) -> Path:
    py = venv / "Scripts" / "python.exe"
    if not py.is_file():
        py = venv / "bin" / "python"
    if py.is_file():
        print(f"打包 venv 已存在：{venv}")
    else:
        boot = find_bootstrap_python()
        print(f"建打包 venv：{venv}（用 {boot}）")
        rc = run([boot, "-m", "venv", str(venv)])
        if rc != 0 or not py.is_file():
            raise SystemExit(f"创建 venv 失败：{venv}")
    return py


def pip_install(py: Path, packages: list[str], indexes: list[str]) -> None:
    """装包，源按顺序回退；全失败才报错。"""
    last = 0
    for idx in indexes:
        rc = run([py, "-m", "pip", "install", "-q", "-i", idx, *packages])
        if rc == 0:
            return
        last = rc
        print(f"  ↑ 源 {idx} 失败（退出码 {rc}），换下一个源重试")
    raise SystemExit(f"装不上：{' '.join(packages)}（最后一个源退出码 {last}）")


def ensure_deps(py: Path, indexes: list[str]) -> None:
    """确保 venv 里有 PyQt6 / pypdf（打包要能 import 到它们）+ PyInstaller。

    ★ PyQt6 必须真的装进这个 venv：PyInstaller 是靠 **import 分析**收集依赖的，
      没装就一个 Qt DLL 都进不去，exe 起来只会报「缺少图形界面依赖」。
    """
    probe = ("import importlib.util as u, sys;"
             "need=[m for m in ('PyQt6','pypdf','PyInstaller') if u.find_spec(m) is None];"
             "print(','.join(need))")
    out = subprocess.run([str(py), "-c", probe], capture_output=True, text=True)
    missing = [m for m in (out.stdout or "").strip().split(",") if m]
    if not missing:
        print("依赖已齐：PyQt6 / pypdf / PyInstaller")
        return
    print(f"缺依赖：{'、'.join(missing)} —— 开始安装")
    run([py, "-m", "pip", "install", "--upgrade", "pip", "-q", "-i", indexes[0]])
    if "PyQt6" in missing or "pypdf" in missing:
        pip_install(py, ["-r", str(REQUIREMENTS)], indexes)
    if "PyInstaller" in missing:
        pip_install(py, ["pyinstaller"], indexes)


def _rd_force(p: Path) -> bool:
    """删文件/目录的最后一道兜底：系统自带的 `del /f` + `rd /s /q`。

    ★ 与主程序里的 `force_delete()` 是同一套思路（那边还有清只读位 + `\\\\?\\`
      长路径前缀 + 重试）。这里只要最后一道就够 —— 打包产物在 `dist/` 下，
      路径短、也不是只读文件，真正会卡住的是「exe 正被某个进程攥着句柄」，
      而 `del /f` 对这种情况比 Python 的 `unlink` 更有一拼之力。
    """
    if os.name != "nt":
        return False
    s = os.path.abspath(str(p))
    q = '"' + s + '"'
    cmd = (f"del /f /s /q {q} >nul 2>&1 & rd /s /q {q} >nul 2>&1"
           if os.path.isdir(s) else f"del /f /q {q} >nul 2>&1")
    try:
        subprocess.run(["cmd", "/c", cmd], capture_output=True, timeout=600)
    except Exception:                             # noqa: BLE001
        return False
    return not os.path.exists(s)


def _clear_other_form(name: str, onefile: bool) -> None:
    """清掉「另一种形态」的同名产物，免得按老路径拿到旧壳子。

    ★ 实测踩过：先打过 onedir（`dist/PDF构建器-多版本/`），再打 onefile 时
      `dist/` 里**两种形态并存**。若脚本/用户按老路径去取
      `dist/PDF构建器-多版本/PDF构建器-多版本.exe`，拿到的还是那个旧壳子，
      于是「明明重新打了还是不行」。所以每次打包前先互斥清理。
    """
    dist = HERE / "dist"
    stale = (dist / f"{name}.exe").exists() if not onefile else (dist / name).is_dir()
    if not stale:
        return
    target = (dist / name) if onefile else (dist / f"{name}.exe")
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)
        print(f"清掉另一种形态的同名产物：{target}")
    except OSError as e:
        if _rd_force(target):                      # ★ 兜底再试一次
            print(f"清掉另一种形态的同名产物（rd 兜底）：{target}")
            return
        # ★ 删不掉**不能**让整条打包命令挂掉（受限环境 / 文件被占用 / 杀软锁着）。
        #   两种形态路径本来就不同，并存不会打错包，只会让「按老路径取产物」的人
        #   拿到旧壳子 —— 所以这里只**大声警告**，并给出要手工删的路径。
        print(f"  ⚠ 清不掉旧产物（{e}）")
        print(f"    请手工删掉：{target}")
        print("    （不删也能打包，但 dist/ 里会两种形态并存，别拿错）")


def do_build(py: Path, console: bool, onefile: bool,
             name: str = APP_NAME, entry: str = DEFAULT_ENTRY) -> Path:
    base = name                                   # 不带 -console 的那个名字
    name = base + ("-console" if console else "")
    _clear_other_form(name, onefile)
    # ⚠️ 给了 .spec 之后，`makespec` 那一类选项一律不许再出现 —— 实测多写一个
    #    `--specpath` 就直接 `ERROR: option(s) not allowed` 退出。
    #    只保留输出目录这两个（它们对 spec 模式仍然有效）。
    cmd = [str(py), "-m", "PyInstaller", "--noconfirm", "--clean",
           "--distpath", str(HERE / "dist"),
           "--workpath", str(HERE / "build"),
           str(SPEC)]
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    # ★ 入口脚本与产物名也走环境变量：一个 spec 就能打两种程序
    #   （单版本 `pdf_builder_multi.py` / 多版本 `pdf_builder_multi.py`）。
    env["PDFBUILDER_EXE_ENTRY"] = entry
    env["PDFBUILDER_EXE_NAME"] = base
    # ★ 给了 spec 文件之后 PyInstaller 会拒绝 `--console` 这类命令行开关，
    #   所以「保留控制台」「打包形态」只能靠环境变量传给 spec（见 spec 顶部）。
    if console:
        env["PDFBUILDER_EXE_CONSOLE"] = "1"
    else:
        env.pop("PDFBUILDER_EXE_CONSOLE", None)
    if onefile:
        env.pop("PDFBUILDER_EXE_ONEDIR", None)      # onefile 是默认，显式清掉
    else:
        env["PDFBUILDER_EXE_ONEDIR"] = "1"
    t0 = time.monotonic()
    rc = run(cmd, cwd=str(HERE), env=env)
    dt = time.monotonic() - t0
    if rc != 0:
        raise SystemExit(f"PyInstaller 失败（退出码 {rc}），用时 {dt:.0f}s")
    exe = ((HERE / "dist" / f"{name}.exe") if onefile
           else (HERE / "dist" / name / (name + ".exe")))
    if not exe.is_file():
        raise SystemExit(f"打包报成功但找不到产物：{exe}")
    kind = "onefile（单个文件）" if onefile else "onedir（目录）"
    print(f"打包完成，用时 {dt:.0f}s，形态 {kind} → {exe}")
    return exe


def _size_mb(p: Path) -> float:
    """onefile 传文件、onedir 传目录，都能算。"""
    if p.is_file():
        return p.stat().st_size / 1048576
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1048576


def _decode(b: bytes) -> str:
    """尽力把子进程输出解成可读文本。

    ★ 别假设 UTF-8：**打包后的 exe 实测按 ANSI 代码页（中文 Windows = GBK）写
      管道**，连 `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1` 传进去都不生效
      （PyInstaller 引导那层吃掉了）。按 UTF-8 硬解会得到 `�Լ�ͨ��` 这种东西，
      看着像工具坏了 —— 其实只是两边编码不一致。
      先试 UTF-8（严格，解不开就抛），再退到 ANSI 代码页。
    """
    for enc in ("utf-8", "mbcs", "gbk"):
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return b.decode("utf-8", "replace")


def _find_sample_pdf() -> Path | None:
    """找一个真 PDF 来验 pypdf 有没有被打进包（懒加载只能这么验）。"""
    base = Path(r"C:\Users\zb137\Desktop\编程软件\Python 文档")
    if not base.is_dir():
        return None
    for pat in ("Python 3.1[3456]* PDF 文档/09*.pdf",
                "Python 3.1[3456]* PDF 文档/*.pdf",
                "**/09*.pdf"):
        hit = sorted(base.glob(pat))
        if hit:
            return hit[0]
    return None


def _kill_tree(pid: int) -> bool:
    """杀掉整棵进程树（Windows），成功返回 True。

    ★ 为什么不能只 `Popen.terminate()`：PyInstaller **onefile 是两层进程** ——
      引导进程解压完会再起一个自己当子进程，真正的程序跑在内层。
      `terminate()` 只打外层，内层继续活着、还开着 exe 文件，
      于是临时目录删不掉（实测残留一个 276 MB 的进程）。
    """
    if os.name != "nt":
        return False
    try:
        r = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, timeout=30)
        return r.returncode == 0
    except Exception:                             # noqa: BLE001
        return False


def _cleanup_dir(d: Path, tries: int = 6) -> None:
    """尽力删掉冒烟用的临时目录；删不掉只提示，**不报错**。

    ★ 实测：exe 刚跑完（尤其 GUI 被 terminate）时，Windows 还攥着文件句柄
      （杀软也常在扫这个新解压出来的二进制），立刻 `rmtree` 会
      `PermissionError: [WinError 5] 拒绝访问`。这不是程序问题，
      但会让冒烟测试在**最后一步**崩掉、整条命令以失败退出 —— 非常误导。
      所以这里退避重试，仍不行就留一句话（那个目录在 %TEMP% 下，系统会回收）。
    """
    for _ in range(tries):
        try:
            shutil.rmtree(d)
            return
        except OSError:
            time.sleep(0.6)
    if _rd_force(d):                              # ★ 兜底
        return
    print(f"  （提示：临时目录没删干净 → {d}；在 %TEMP% 下，系统会自己回收）")


def smoke(exe: Path) -> bool:
    """冒烟：把 exe **拷到干净目录**运行，证明单文件真的能独立用。

    ★ 这一步是本次修复的核心。原来只在 `dist/PDF构建器-多版本/` 原地跑 ——
      onedir 在那儿当然没问题（`_internal/` 就在旁边），
      可这个「通过」什么也没证明：把 exe 拷出去立刻退出码 127。
      所以现在：新建空目录 → 只拷**这一个文件**进去 → 在那里运行。

    这个 exe 是 **console=False**：从资源管理器双击时 `sys.stdout` 是 None。
    但**被父进程用管道拉起时**句柄是有效的，所以这里既看 stdout，
    也把 exe 旁边的 `tool-output.log` 当备选依据。
    """
    print("\n=== 冒烟测试（在干净目录里跑，证明单文件可独立用）===")
    ok = True

    sandbox = Path(tempfile.mkdtemp(prefix="pdfbuilder-smoke-"))
    try:
        probe = sandbox / exe.name
        shutil.copy2(exe, probe)                 # ★ 只拷这一个文件，别无他物
        print(f"  隔离目录：{sandbox}")
        print(f"  目录内文件：{[p.name for p in sandbox.iterdir()]}")

        log = sandbox / "tool-output.log"

        def call(*extra: str, timeout: int = 600) -> tuple[int, str]:
            log.unlink(missing_ok=True)
            r = subprocess.run([str(probe), *extra], capture_output=True,
                               timeout=timeout)
            text = _decode((r.stdout or b"") + (r.stderr or b""))
            if not text.strip() and log.is_file():
                text = log.read_text(encoding="utf-8", errors="replace")
            return r.returncode, text

        # ★ 判据是「**起得来、认得出工具**」，不是「退出码 0」：
        #   裸 `--tool`（不带工具名）本来就返回 2（用法提示），
        #   源码模式一模一样。早先按 rc==0 判 → 明明成功却报失败。
        rc, text = call("--tool")
        names = [n for n in ("name-map", "merge-pdf", "fix-index") if n in text]
        if len(names) == 3:
            print(f"  ✔ 单文件启动正常（rc={rc}，--tool 列表含工具名 3/3）")
        else:
            print(f"  ✘ 单文件启动失败：退出码 {rc}，输出 {len(text)} 字符")
            if text.strip():
                print("    " + text.strip().splitlines()[-1])
            print("    → 说明这个 exe 还依赖旁边的文件（onedir 壳子 / 缺 _internal）")
            ok = False

        rc, text = call("--tool", "name-map", "--check")
        tail = text.strip().splitlines()
        print(f"  name-map --check: 退出码 {rc}  {tail[-1] if tail else '(无输出)'}")
        ok &= rc == 0

        pdf = _find_sample_pdf()
        if pdf:
            rc, text = call("--tool", "check-pdf-gaps", str(pdf))
            hit = "需要 pypdf" not in text and rc == 0
            print(f"  check-pdf-gaps  : 退出码 {rc}，未报缺 pypdf → {hit}")
            ok &= hit
        else:
            print("  check-pdf-gaps  : 跳过（没找到样例 PDF）")

        # GUI 能不能起来：无参启动，看进程活不活（起来后杀掉）。
        # ★ 放最后并**杀整棵进程树**，否则残留进程会锁着文件（见下）。
        try:
            p = subprocess.Popen([str(probe)], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            time.sleep(8)
            alive = p.poll() is None
            if alive:
                # ★ onefile 是「引导进程 + 真正的子进程」两层：只 terminate 外层，
                #   内层会活下来继续开着 exe 文件 → 临时目录删不掉
                #   （实测留下一个 276 MB 的进程 + `PermissionError: WinError 5`）。
                #   所以用 taskkill /T 连子孙一起杀；不行再退到 kill。
                if not _kill_tree(p.pid):
                    p.kill()
                try:
                    p.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
            print(f"  GUI 启动（8s）  : {'活得很好 ✔' if alive else '自行退出了 ✘'}")
            ok &= alive
        except Exception as e:                    # noqa: BLE001
            print(f"  GUI 启动        : 异常 {e} ✘")
            ok = False

        print(f"\n  产物体积：{_size_mb(exe):.0f} MB"
              f"{'（单个文件）' if exe.is_file() else '（目录）'}")
    finally:
        _cleanup_dir(sandbox)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="把 GUI 打包成 exe（PyInstaller）")
    ap.add_argument("--venv", default=str(DEFAULT_VENV), help="打包用的 venv 目录")
    ap.add_argument("--onedir", action="store_true",
                    help="打成目录形态（启动快，但必须整个目录一起分发；默认是 onefile）")
    ap.add_argument("--clean", action="store_true", help="打包前删掉 build/ 与 dist/")
    ap.add_argument("--console", action="store_true",
                    help="保留控制台窗口（排查打包问题时用；成品应不带）")
    ap.add_argument("--no-smoke", action="store_true", help="不跑冒烟测试")
    ap.add_argument("--index", default=None,
                    help="pip 源（可重复用逗号分隔；按顺序试，默认清华源→官方 PyPI）")
    ap.add_argument("--entry", default=DEFAULT_ENTRY,
                    help="入口脚本（默认 pdf_builder_multi.py；多版本版用 pdf_builder_multi.py）")
    ap.add_argument("--name", default=APP_NAME,
                    help=f"产物名（默认 {APP_NAME}）")
    args = ap.parse_args()

    if not SPEC.is_file():
        raise SystemExit(f"找不到 spec：{SPEC}")

    if args.clean:
        for d in ("build", "dist"):
            p = HERE / d
            if p.exists():
                print(f"删 {p}")
                shutil.rmtree(p, ignore_errors=True)

    venv = Path(args.venv).expanduser()
    py = ensure_venv(venv)
    indexes = [s.strip() for s in args.index.split(",")] if args.index else PIP_INDEXES
    ensure_deps(py, indexes)
    if not (HERE / args.entry).is_file():
        raise SystemExit(f"找不到入口脚本：{HERE / args.entry}")
    exe = do_build(py, args.console, onefile=not args.onedir,
                   name=args.name, entry=args.entry)
    if args.no_smoke:
        return 0
    return 0 if smoke(exe) else 1


if __name__ == "__main__":
    raise SystemExit(main())
