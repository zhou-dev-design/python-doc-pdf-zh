#!/usr/bin/env bash
# 把 Sphinx 产出的英文 PDF 名重命名为参考目录的中文名（与参考样张的 命名.txt 一致）
#
#   ★ 2026-09-26：映射表已收敛到 `tools/name_map.py` 一处，本脚本只做转调。
#     原来这里是**第二份**映射表（还有第三份在 GUI 里），三份必须手工同步，
#     实测漏同步过两次（asyncio 名、版本的 0925）。现在只剩一处。
#   ★ 2026-10-04：`tools/*.py` 也已内联进 `gui/pdf_builder_gui.py`，
#     所以这里**再少一跳**：直接调主程序的 `--tool rename-pdf`
#     （`tools/rename-pdf.py` 仍然可用，它只是等价的转发器）。
#
# 用法： bash rename-pdf.sh [PDF 目录] [版本号]
#        VERSION=3.15 bash rename-pdf.sh [PDF 目录]
#        加 --check 只检查不改名
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MAIN="$HERE/gui/pdf_builder_gui.py"

DIR="${1:-.}"
VERSION="${2:-${VERSION:-3.14}}"
# 第 3 个及以后的参数原样透传（如 --check）
EXTRA=()
if [ "$#" -ge 3 ]; then EXTRA=("${@:3}"); fi

# 找一个能跑 python 的解释器：优先标准名，再退回本机 managed 运行时
PY=""
for cand in python python3 py; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  for cand in \
    "C:/Users/zb137/.workbuddy/binaries/python/versions/3.13.12/python.exe" \
    "$HOME/.workbuddy/binaries/python/versions/3.13.12/python.exe"; do
    [ -x "$cand" ] && { PY="$cand"; break; }
  done
fi
if [ -z "$PY" ]; then
  echo "!! 找不到 python，无法运行 $MAIN --tool rename-pdf" >&2
  exit 2
fi

# bash 侧统一用 cygpath 显式转 Windows 路径（MSYS_NO_PATHCONV=1 时 /c/... 会传崩）
if command -v cygpath >/dev/null 2>&1; then
  DIR="$(cygpath -w "$DIR")"
  MAIN="$(cygpath -w "$MAIN")"
fi

exec "$PY" "$MAIN" --tool rename-pdf "$DIR" --version "$VERSION" ${EXTRA[@]+"${EXTRA[@]}"}
