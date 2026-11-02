# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 —— 把 GUI 打成一个**可单独分发**的 exe。

用法（别直接调，用 build_exe.py，它会先备好带 PyInstaller 的 venv）：

    python build_exe.py                # 推荐：默认 **onefile**，产出一个 exe 文件
    python build_exe.py --onedir       # 备选：产出一个目录（启动快，但要整目录分发）
    python build_exe.py --no-smoke
    python -m PyInstaller --noconfirm --clean pdf_builder_gui.spec   # 手动（默认 onefile）

产物：
    onefile → `dist/PDF构建器.exe`            ← **单个文件**，拷到哪都能跑
    onedir  → `dist/PDF构建器/`（整个目录）  ← 里面 exe 只有 3 MB，靠 `_internal/`

────────────────────────────────────────────────────────────────────────────
★★ 为什么默认改成 onefile（2026-10-06）★★
  之前是 onedir。实测把它拷到别处单独运行 → **退出码 127、零输出、进程起不来**：
  那个 3.4 MB 的 exe 只是引导壳，PyQt6 / pypdf / Python 运行时全在旁边的
  `_internal/` 里。对「拿一个 exe 发给别人」这个需求来说，onedir **根本不算
  打好了** —— 用户复制走的那个文件注定跑不起来。
  onedir 不是没有优点（启动快、报错能直接翻 `_internal/`），所以留了 `--onedir`
  开关，但**默认必须是 onefile**。

★ onefile 的代价（已知、可接受，别当成 bug）
  1. **每次启动都要把内容解压到 `%TEMP%\\_MEIxxxxxx\\`** —— 首次启动（含 GUI
     双击）会明显慢几秒；
  2. 步骤 7 的 `makeindex-fix.py` 已改为**自包含脚本**（2026-10-28，由主程序
     源码切片生成、PATH 里的 python 直接跑），不再拉起 exe 自己 —— 旧方案
     「每册调一次 exe、每次重解压 37 MB」且继承 `_PYI_*` 后会启动失败弹模态框，
     已废弃；
  3. 自解压行为**更容易被杀软/Defender 误报**，必要时加白名单；
  4. 进程被强杀时残留的 `_MEIxxxxxx` 目录要手工清（Windows 关机/重启会回收）。

★ 主程序里与之配套的三处（都已适配，见 `app_dir()` 等）
  · `app_dir()`        用 `sys.executable`（exe 真实路径）的父目录，
                       而**不是** `_MEIPASS` —— 所以 `config.json` /
                       `tool-output.log` / `gui-startup-error.log` 仍然写在
                       **exe 旁边**，用户找得到（这是 onefile 最容易踩的坑）。
  · `_guess_python()`  冻结后**绝不回退** `sys.executable`（那是 exe 自己）。
  · `_ensure_streams()` onefile + `console=False` 下 `sys.stdout` 是 None，
                       把输出落到 `<exe 目录>/tool-output.log`。

★ 为什么 console=False（无控制台）
  图形界面不该弹黑框。代价是**没有 `sys.stdout`** —— 主程序里 `_ensure_streams()`
  已兜住：`--tool` / `--cli` / `--check` 在无控制台时写
  `<exe 目录>/tool-output.log`，而不是 `AttributeError` 崩掉。
  ⚠️ 这条是**必经之路**：步骤 7 的 `makeindex-fix.py` 转发器就是以
     「无控制台」的方式把 exe 拉起来的（见主程序 `_emit_makeindex_fix`）。

★ 为什么显式声明 pypdf
  它是**懒加载**（`_import_pypdf()` 里才 import），PyInstaller 的静态分析
  通常能扫到函数体内的 import，但那属于实现细节 —— 写在 spec 里才是契约。
  漏了它 = merge-pdf / report / verify-pdf / check-pdf-gaps 全部报「需要 pypdf」。

★ 为什么不收 tools/
  15 个内置工具已全部内联进主程序（2026-10-04），运行时不需要任何 .py。
  运行时会落到磁盘上的是 `makeindex-fix.py`（latexmk 的 `$makeindex`
  只能调外部文件），由主程序在步骤 7 **从打包进来的主程序源码切片生成**
  （自包含脚本，见 `datas` 与 `_tool_source()`）。
────────────────────────────────────────────────────────────────────────────
"""

import os

from PyInstaller.utils.hooks import collect_submodules

#: 是否保留控制台。用环境变量而不是命令行开关：**给了 spec 文件之后**
#: PyInstaller 会拒绝大部分命令行选项（`--console` 就在其列），所以只能从这里读。
#: 排查打包问题时：`set PDFBUILDER_EXE_CONSOLE=1` 再打包，就能看到 traceback。
_CONSOLE = os.environ.get("PDFBUILDER_EXE_CONSOLE") == "1"
#: 打包形态。默认 **onefile**（单文件）；设 `PDFBUILDER_EXE_ONEDIR=1` 退回目录形态。
_ONEDIR = os.environ.get("PDFBUILDER_EXE_ONEDIR") == "1"
#: 入口脚本与产物名 —— 都由 build_exe.py 用环境变量传进来（多版本版从
#: `pdf_builder_multi.py` 打包）。留空时就是原来的单版本版。
_ENTRY = os.environ.get("PDFBUILDER_EXE_ENTRY") or "pdf_builder_gui.py"
_BASE_NAME = os.environ.get("PDFBUILDER_EXE_NAME") or "PDF构建器"
_NAME = _BASE_NAME + ("-console" if _CONSOLE else "")

#: 懒加载/动态 import 的包，静态分析不一定可靠 —— 契约式显式声明。
hiddenimports = ["pypdf", *collect_submodules("pypdf")]

#: ★ 把主程序**源码**也打进去（2026-10-28）：步骤 7 生成自包含的
#:   `makeindex-fix.py` 时，frozen 模式要从 `sys._MEIPASS` 里读这份源码、
#:   按 `[TOOL-SRC:fix-index]` 标记切片（见 `_tool_source()` / `_emit_makeindex_fix()`）。
#:   只多 ~0.5 MB；没有它，释放脚本会退回旧转发器（每次起 exe、继承 _PYI_*
#:   后可能弹模态框卡死构建）。
datas = [(_ENTRY, ".")]

a = Analysis(
    [_ENTRY],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 打进来只是白占体积；都不是运行时依赖。
    excludes=["tkinter", "pydoc_data", "lib2to3"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

if _ONEDIR:
    # ── 目录形态（备选）───────────────────────────────────────────────────
    # exe 只是引导壳，真正的依赖在 COLLECT 出来的 `_internal/` 里。
    # ★ 分发时必须**整个目录**一起给，单独拷 exe 出去 = 退出码 127。
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,               # UPX 压缩常触发杀软误报，不值得
        console=_CONSOLE,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=_NAME,
    )
else:
    # ── 单文件形态（默认）─────────────────────────────────────────────────
    # ★ 与 onedir 的两点差别：
    #   1. `a.binaries` / `a.datas` 直接塞进 EXE，**不再** `exclude_binaries=True`；
    #   2. **没有 COLLECT** —— 有了它又变成目录了。
    # `runtime_tmpdir=None` = 解压到系统临时目录。别指到 exe 旁边：那里可能只读
    # （U 盘 / 网络盘 / Program Files），也会污染用户目录。
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,               # UPX 压缩常触发杀软误报，不值得
        upx_exclude=[],
        runtime_tmpdir=None,
        console=_CONSOLE,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
    )
