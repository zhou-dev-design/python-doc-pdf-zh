#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`pdf_builder_linux.py` 的逻辑自检 —— **任何操作系统都能跑**。

为什么需要它：真正的 POSIX 行为只能在 Linux 上验证，但移植代码里有几处
「只有在 Linux 上才会走到的分支」（locale、python 别名、TEXMF 缓存目录）。
这份脚本用「把 IS_POSIX 临时改成 True」的办法，在 Windows 上也能把这些分支
跑一遍 —— 抓到 90% 的低级错误（拼错属性名、忘了导入、路径拼错），
剩下的 10%（真的并行、真的 xelatex）留给 Linux 上的 `--preflight`。

只读，不联网，不建大目录；全程输出 ASCII 结论（OK / FAIL），便于 grep。

    python3 ci/linux/selftest.py
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import traceback
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pdf_builder_linux as L                     # noqa: E402

RESULTS: list[tuple[bool, str, str]] = []


def check(name: str, fn) -> None:
    try:
        detail = fn() or ""
        RESULTS.append((True, name, str(detail)))
    except Exception as e:                        # noqa: BLE001
        RESULTS.append((False, name, f"{type(e).__name__}: {e}"))
        if os.environ.get("PDFBUILD_SELFTEST_TRACE"):
            traceback.print_exc()


def make_pipe(root: Path, ver: str | None = None):
    """造一个最小可用的 Pipeline（不联网、不建 venv）。

    ★ 版本号必须取**当前解释器**的，不能写死：这套自检会跑在
      「3.13 / 3.14 / 3.15 三个各自独立的 job」里，写死 3.13 的话
      3.15 的 job 上 `find_interpreter("3.13")` 会正确地退回 sys.executable(3.15)，
      于是断言必挂 —— 2026-11-02 的第一次 CI 就是这么红的（54 秒、构建根都没建）。
    """
    if ver is None:
        ver = f"{sys.version_info[0]}.{sys.version_info[1]}"
    cfg = L.M.Config()
    cfg.version = ver
    cfg.versions = [ver]
    cfg.base_dir = str(root.parent)
    cfg.root = str(root)
    cfg.outdir = str(root)
    cfg.python = sys.executable
    cfg.version_pythons = {ver: sys.executable}
    cfg.texlive_bin = ""
    cfg.jobs = 2
    return L.LinuxPipeline(cfg, L.M.ConsoleReporter(False))


def main() -> int:
    with redirect_stdout(io.StringIO()):          # 构造过程可能打印，先收起来
        pass

    tmp = Path(tempfile.mkdtemp(prefix="pdfbuild-selftest-"))
    root = tmp / "root"
    root.mkdir()
    pipe = make_pipe(root)

    # 1) 导入的是「原实现」，而且我们确实只覆盖了 3 个方法
    check("导入主程序", lambda: Path(L.M.__file__).name)
    check("继承关系", lambda: "Pipeline" if isinstance(pipe, L.M.Pipeline) else (_ for _ in ()).throw(
        AssertionError("不是 M.Pipeline 的子类")))

    def overrides():
        pairs = [("_make_env", L.M.Pipeline._make_env), ("step0", L.M.Pipeline.step0),
                 ("step4", L.M.Pipeline.step4)]
        got = []
        for name, base in pairs:
            mine = getattr(L.LinuxPipeline, name)
            if mine is base:
                raise AssertionError(f"{name} 没有覆盖（会走 Windows 分支）")
            got.append(name)
        return "覆盖 " + " / ".join(got)
    check("只覆盖平台胶水层", overrides)

    # 2) 解释器探测：拿到的必须真是那个 major.minor
    def interp():
        want = f"{sys.version_info[0]}.{sys.version_info[1]}"
        py = L.find_interpreter(want)
        got = L.interpreter_version(py)
        if not got:
            raise AssertionError(f"{want} 解释器不可用：{py}")
        if L._ver_tuple(got) != L._ver_tuple(want):
            raise AssertionError(f"拿到 {got}（{py}），不是 {want}.x")
        return f"{py} → {got}"
    check("解释器探测（跟随当前解释器）", interp)

    def interp_fallback():
        py = L.find_interpreter("9.9")
        if not py:
            raise AssertionError("没有退回 sys.executable")
        return Path(py).name
    check("找不到的版本退回 sys.executable", interp_fallback)

    # 3) POSIX 分支：locale / TEXMF / python 别名
    saved = L.IS_POSIX
    L.IS_POSIX = True
    try:
        def locale_ok():
            loc = L.LinuxPipeline._utf8_locale()
            if not loc:
                raise AssertionError("空 locale")
            return loc
        check("UTF-8 locale 选取", locale_ok)

        def env_ok():
            env = pipe._make_env()
            if "utf" not in env.get("LANG", "").lower():
                raise AssertionError(f"LANG={env.get('LANG')!r} 不是 UTF-8")
            if not str(env.get("TEXMFVAR", "")).startswith(str(root)):
                raise AssertionError(f"TEXMFVAR 没落到构建根：{env.get('TEXMFVAR')!r}")
            if env.get("LC_ALL") != env.get("LANG"):
                raise AssertionError("LC_ALL 与 LANG 不一致")
            return f"LANG={env['LANG']} TEXMFVAR={Path(env['TEXMFVAR']).name}"
        check("_make_env 的 POSIX 分支", env_ok)

        def shim_ok():
            # 造一个「没有 python 的 PATH」，逼它建别名
            bare = tmp / "barebin"
            bare.mkdir(exist_ok=True)
            pipe.env = {"PATH": str(bare)}
            pipe._apply_python_alias()
            shim = root / ".pyshim" / "python"
            if not (shim.exists() or shim.is_symlink()):
                raise AssertionError("没有生成 .pyshim/python")
            if str(shim.parent) not in pipe.env["PATH"].split(os.pathsep):
                raise AssertionError("别名目录没进 PATH")
            # ★ `shutil.which` 在 Windows 上按 PATHEXT 找 `python.exe`，认不出
            #   无扩展名的 `python`；这条断言只有真 POSIX 上才有意义。
            if os.name == "posix":
                found = shutil.which("python", path=pipe.env["PATH"])
                if not found:
                    raise AssertionError("PATH 里仍然找不到 python")
                return found
            target = os.readlink(shim) if shim.is_symlink() else f"(包装器 {shim.stat().st_size}B)"
            return f"Windows 上只验证生成（→ {Path(target).name}）"
        check("python 别名（Ubuntu 无 python 时）", shim_ok)

        def shim_idempotent():
            before = pipe.env["PATH"]
            pipe._apply_python_alias()                 # 再来一次不该重复追加
            if pipe.env["PATH"] != before:
                raise AssertionError("重复追加了 PATH")
            return "幂等"
        check("别名幂等", shim_idempotent)
    finally:
        L.IS_POSIX = saved

    # 4) 步骤解析沿用主程序（`--only 7` 必须是「编译 PDF」= 行 8）
    def steps_ok():
        cfg = pipe.cfg
        cfg.only_steps = "7"
        got = L.pick_steps(cfg)
        if got != [8]:
            raise AssertionError(f"--only 7 解析成 {got}，应为 [8]")
        cfg.only_steps = "6,6b,7,7b,8,9"
        got = L.pick_steps(cfg)
        if got != [6, 7, 8, 9, 10, 11]:
            raise AssertionError(f"多步骤解析成 {got}")
        cfg.only_steps = ""
        cfg.from_step = 6
        got = L.pick_steps(cfg)
        if not got or got[0] != 6:
            raise AssertionError(f"--from 6 从 {got} 开始")
        return "--only 7 → 行 8；--from 6 → 行 6 起"
    check("步骤号解析（复用主程序）", steps_ok)

    # 5) 取源策略：github = 单一直连、绝不落到镜像站
    def source_direct():
        cfg = L.DirectSourceConfig()
        cfg.gh = "https://github.com"
        for repo in ("python/cpython", "python/python-docs-zh-cn"):
            urls = cfg.git_urls(repo, "")
            if len(urls) != 1:
                raise AssertionError(f"{repo} 给了 {len(urls)} 个候选：{urls}")
            if not urls[0][1].startswith("https://github.com/"):
                raise AssertionError(f"{repo} 没走直连：{urls[0]}")
        return cfg.git_urls("python/cpython", "")[0][1]
    check("取源只走 github 直连（无镜像）", source_direct)

    def source_auto():
        cfg = L.M.Config()
        cfg.gh = ""
        urls = cfg.git_urls("python/cpython", "")
        if len(urls) < 2:
            raise AssertionError(f"--source auto 应有镜像回退，实际 {len(urls)} 个")
        return f"auto 模式 {len(urls)} 个候选（含镜像）"
    check("--source auto 仍保留镜像回退", source_auto)

    def source_explicit():
        cfg = L.DirectSourceConfig()
        cfg.gh = "https://github.com"
        got = cfg.git_urls("python/cpython", "https://example.com/x.git")[0][1]
        if got != "https://example.com/x.git":
            raise AssertionError(f"显式地址被忽略：{got}")
        return "显式地址优先"
    check("显式仓库地址优先", source_explicit)

    # 5) 配置派生：多版本时每个版本必须各自一个根
    def cfg_ok():
        cfg = pipe.cfg
        cfg.only_steps = ""
        cfg.from_step = 0
        one = cfg.for_version("3.14")
        if one.full_version().startswith("3.14"):
            return f"for_version 正常（{one.full_version()}）"
        raise AssertionError(f"for_version 得到 {one.full_version()}")
    check("Config.for_version", cfg_ok)

    def root_ok():
        cfg = pipe.cfg
        cfg.root = ""
        cfg.base_dir = str(tmp)
        r = Path(cfg.resolved_root())
        if "PDF 文档" not in r.name:
            raise AssertionError(f"构建根名字不对：{r.name}")
        return r.name
    check("构建根命名（沿用 name_map 约定）", root_ok)

    # ------------------------------------------------------------------ 汇总
    bad = [r for r in RESULTS if not r[0]]
    print("=" * 72)
    print("pdf_builder_linux.py 自检")
    print("=" * 72)
    w = max(len(r[1]) for r in RESULTS) + 2
    for ok, name, detail in RESULTS:
        print(f"  [{'OK' if ok else 'FAIL':^4}] {name:<{w}} {detail}")
    print("=" * 72)
    print(f"{len(RESULTS) - len(bad)} 通过 / {len(bad)} 失败")

    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
