#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""转发器 —— 真正的实现在 `gui/pdf_builder_gui.py` 里（2026-10-04 起内联）。

为什么还留着这个文件：
  * `build-sphinx-pdf.sh` 与手工排查照旧可以 `python tools/report.py …`；
  * 但**不会有第二份实现** —— 下面只是把参数原样交给主程序的 `--tool report`，
    所以「脚本改了、主程序没跟上」这种静默分叉在这里不可能发生。

★ 本文件可以用 `python gui/pdf_builder_gui.py --tool emit-shims tools` 重新生成。
"""
import runpy
import sys
from pathlib import Path

_MAIN = (Path(__file__).resolve().parent / '../gui/pdf_builder_gui.py').resolve()
sys.argv = [str(_MAIN), '--tool', 'report', *sys.argv[1:]]
runpy.run_path(str(_MAIN), run_name='__main__')   # 退出码随 SystemExit 传出
