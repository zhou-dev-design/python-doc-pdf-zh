#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""转发器 —— 真正的实现在 `gui/pdf_builder_gui.py` 里（2026-10-04 起内联）。

为什么还留着这个文件：
  * 手工排查照旧可以 `python verify-pdf.py <目录>`（批量看页数 / 书签 / 前 40 页链接数）；
  * 但**不会有第二份实现** —— 下面只是把参数原样交给主程序的 `--tool verify-pdf`。

★ 等价替代：`python gui/pdf_builder_gui.py --tool verify-pdf <目录>`
"""
import runpy
import sys
from pathlib import Path

_MAIN = (Path(__file__).resolve().parent / 'gui/pdf_builder_gui.py').resolve()
sys.argv = [str(_MAIN), '--tool', 'verify-pdf', *sys.argv[1:]]
runpy.run_path(str(_MAIN), run_name='__main__')   # 退出码随 SystemExit 传出
