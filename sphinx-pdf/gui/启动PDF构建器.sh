#!/usr/bin/env bash
# =============================================================================
#  Python 中文文档分册 PDF 构建器 —— GUI 启动器（Git Bash / Linux / macOS）
#
#  用法：
#    bash 启动PDF构建器.sh                    启动界面
#    bash 启动PDF构建器.sh --cli              命令行全流程
#    bash 启动PDF构建器.sh --cli --from 8     从「编译 PDF」开始
# =============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="${GUI_VENV:-C:/pypdfbuild/gui-venv}"
PY="$VENV/Scripts/python.exe"
[ -x "$PY" ] || PY="$VENV/bin/python"
BOOT="${BOOT_PYTHON:-C:/Users/zb137/.workbuddy/binaries/python/versions/3.13.12/python.exe}"

if [ ! -x "$PY" ]; then
  echo "[setup] 创建虚拟环境 $VENV"
  if [ -x "$BOOT" ]; then
    "$BOOT" -m venv "$VENV"
  else
    python3 -m venv "$VENV" || python -m venv "$VENV"
  fi
  [ -x "$PY" ] || { echo "[错误] 创建 venv 失败，请先装 Python 3.11+"; exit 1; }
  echo "[setup] 安装 PyQt6 / pypdf …"
  "$PY" -m pip install --upgrade pip -q
  "$PY" -m pip install -q -r "$HERE/requirements.txt" || exit 1
fi

exec "$PY" "$HERE/pdf_builder_gui.py" "$@"
