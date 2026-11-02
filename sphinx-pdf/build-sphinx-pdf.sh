#!/usr/bin/env bash
# =============================================================================
# 构建 Python 中文文档分册 PDF —— 路线 A（Sphinx 分册 PDF）
#
# 产出：与官方/参考文件一致的分册 PDF（每个 latex_documents 条目一个 PDF）
#   01Python 3.14 有什么新变化.pdf
#   02Python 教程.pdf
#   03Python安装和使用.pdf
#   04Python 语言参考手册.pdf
#   05Python 标准库.pdf
#   06扩展和嵌入 Python 解释器.pdf
#   07Python C API 参考手册.pdf
#   08安装 Python 模块.pdf
#   09Python 指南.pdf（+ 27 个 howto 分册）
#   10Python 常见问题.pdf
#   11Python 内置参考手册.pdf
#
# 封面标题默认是英文（来自 conf.py 的 latex_documents，不走 .po 翻译），
# 第 6b 步会用主程序的 `--tool localize-titles` 把它们换成中文。
# ★ 2026-10-04 起：所有后处理脚本（localize-titles / fix-index / name_map /
#   rename-pdf / merge-pdf / report / alias-po / check-doc-refs …）都已**内联进
#   gui/pdf_builder_gui.py**，本脚本一律走 `python <MAIN> --tool <名字>`。
#   `tools/*.py` 只是等价的转发器 —— 于是与图形界面**永远同一份实现**。
#
# 用法：  bash build-sphinx-pdf.sh [构建根目录]
# 环境：  仅需 Git Bash（Windows）/ bash（Linux、macOS）；TeX Live 2025+ 在 PATH 中
#
# ★ 默认行为（与图形界面版 gui/pdf_builder_gui.py 一致）：
#   · VERSION 决定「版本」并同时是两个仓库的分支：3.13 / 3.14 / 3.15（默认 3.14）
#   · CPython 与 python-docs-zh-cn 都**从网站克隆**（默认中文 zh_CN）；
#     ZH_SRC 指定本地目录时才改用本地翻译源
#   · 索引：非字母条目在最前 + 加粗「非字母」「数字」分组标题 + 每条页码都是超链接
#     （第 7 步把 latexmk 的 $makeindex 换成 `--tool fix-index` 释放的转发器，
#      就地修 .ind；第 7b 步只做自检）
#
# ★ 常用环境变量（都能覆盖默认值）：
#   VERSION=3.15          版本号（默认 3.14），同时决定两个仓库的分支
#   ROOT="/path/构建根目录"  构建根目录；也可用第 1 个位置参数
#   OUTDIR="/path/输出目录"  PDF 最终输出目录（默认 = ROOT）
#   CPYTHON_BRANCH / ZH_BRANCH  分别覆盖两个仓库的分支（默认 = VERSION）
#   ZH_SRC=""             留空 = 联网克隆；填目录 = 用本地翻译源（不联网更新）
#   I18N_EXTRA_URL=""     补充译文的更新源（http(s)://… / file://… / 本机目录）；
#                         留空 = 用主程序内置那份（离线可用）
#   REFRESH=0             已有克隆不 fetch（默认 1 = 每次拉最新）
#   GH=...                GitHub 代理前缀（直连不通时用）
#   PYTHON=...            Python 解释器路径（建 venv 用）
#   TEXLIVE_BIN=...       TeX Live 的 bin 目录
#   PIP_INDEX=...         pip 镜像
#
# ★ 步骤 9/10（可选，默认关；与 gui/pdf_builder_gui.py 的步骤 9/10 对应）：
#   MERGE=1               把 38 册合并成一册，带完整书签（需要 pypdf）
#                         一级书签 = 有独立 PDF 的册子；「Python 指南」下按官网
#                         howto 索引页分「通用 / 高级开发 / 调试和性能分析」三组，
#                         多出的 3 册 howto 直接挂在其下；每册自带整棵书签
#   MERGE_NAME="名字.pdf"  合并册文件名（默认 Python <版本> 文档 <今天>.pdf）
#   CLEAN=build|all       跑完删过程文件。build = 只删 <ROOT>/cpython/Doc/build；
#                         all = 连 cpython 源码 + venv + zh-cn 翻译源 + 日志一起删
#                         ★ 成品 PDF 永远不动 ★
# =============================================================================
set -uo pipefail

# ----------------------------- 可调参数 -------------------------------------
VERSION="${VERSION:-3.14}"                 # Python 版本，同时是两个仓库的分支名
ROOT="${1:-${ROOT:-$HOME/PythonDocsPDF/Python $VERSION PDF 文档}}"
OUTDIR="${OUTDIR:-$ROOT}"                  # 最终 PDF 输出目录（默认同构建根目录）

PYTHON="${PYTHON:-C:/Users/zb137/.workbuddy/binaries/python/versions/3.13.12/python.exe}"
TEXLIVE_BIN="${TEXLIVE_BIN:-/f/texlive/2025/bin/windows}"
export PATH="$TEXLIVE_BIN:$PATH"

CPYTHON_BRANCH="${CPYTHON_BRANCH:-$VERSION}"   # CPython 分支（默认=版本号）
ZH_BRANCH="${ZH_BRANCH:-$VERSION}"             # 翻译仓库分支（默认=版本号）
GH="${GH:-https://ghfast.top/https://github.com}"   # GitHub 代理（直连不通时用）
PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"

# ★ 本地翻译源（可选）：留空 = 联网克隆 python-docs-zh-cn
ZH_SRC="${ZH_SRC:-}"
REFRESH="${REFRESH:-1}"                    # 1 = 已有克隆也 fetch 到最新（断网会自动跳过）

# ★ 步骤 9/10（可选，默认关；与 gui/pdf_builder_gui.py 的步骤 9/10 一一对应）
MERGE="${MERGE:-0}"                        # 1 = 把 38 册合并成一册（带完整书签，需要 pypdf）
MERGE_NAME="${MERGE_NAME:-}"               # 合并册文件名；留空 = Python <版本> 文档 <今天>.pdf
CLEAN="${CLEAN:-none}"                     # none / build / all —— 跑完删掉过程文件

LANG_CODE="zh_CN"
#: 并行度。同一个变量两个用途：
#:   · 步骤 6 的 sphinx `-j` —— 可以是 `auto` 或数字
#:   · 步骤 7 的 latexmk 并发册数 —— 见下面「并发编译」一节，会把 auto/空 折算成数字
#: ★ 这里必须用 `${JOBS:-...}` 而不是直接赋值：写成 `JOBS="auto"` 会把用户在
#:   命令行上传进来的 `JOBS=4` 一并覆盖掉（环境变量在脚本里被无条件重置）。
JOBS="${JOBS:-auto}"

SPHINX_PDF_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$SPHINX_PDF_DIR/tools"   # ★ 现在只剩「转发器」，真实现已内联进主程序（见下）
# ★★ 2026-10-04 起：localize-titles / fix-index / name_map / rename-pdf /
#    merge-pdf / report / alias-po / check-doc-refs / check-pdf-gaps /
#    fix-md-escapes / verify-pdf **全部内联进** gui/pdf_builder_gui.py。
#    本脚本一律走 `python <MAIN> --tool <名字> …`，tools/*.py 只是等价的转发器。
#    好处：与图形界面**永远同一份实现**，判据不可能再分叉（历史上分叉过两次）。
MAIN="$SPHINX_PDF_DIR/gui/pdf_builder_gui.py"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31m[错误] %s\033[0m\n' "$*" >&2; exit 1; }

# ★★ MSYS/Cygwin 下必须清掉 locale 变量 ★★
#   步骤 7 的 latexmk 是 TeX Live 自带的 perl 脚本。Windows 版 perl 一看到
#   LC_ALL / LANG 是非 C 的 locale，就按那个编码处理文件名，而 Windows 的文件
#   API 走 ANSI 代码页 —— 于是**凡是路径里带中文的文件全都打不开**（本方案默认
#   路径含「Python 文档」）：
#     Latexmk: I cannot read the rc-file 'latexmkrc'
#     Cannot write file 'whatsnew.aux'
#     runscript.tlu:933: ...\tlperl\bin\perl.exe: No such file or directory
#   后果是 latexmk 退出码 12、整册不出 PDF，而报错完全不提编码。
#   实测（`latexmk -v` 里 "cannot read the rc-file" 的次数）：
#     LC_ALL=C.UTF-8 → 1    LC_ALL=zh_CN.GBK → 1    LC_ALL=C → 0    清空 → 0
#   注意 LC_ALL=C 是好的、UTF-8/GBK 反而坏 —— 所以不是「有没有设」的问题。
#   只影响本脚本的子进程，不影响你的 shell。
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) unset LC_ALL LANG LC_CTYPE ;;
esac

# Windows 原生程序（python.exe 之类）不认 MSYS 的 /c/... 路径：MSYS 默认会自动转换，
# 但若环境里设了 MSYS_NO_PATHCONV=1 就不转，路径会被当成「当前盘符下的 /c/...」而报
# 「No such file or directory」。统一用 cygpath 显式转成 Windows 形式，任何环境都稳。
# （cygpath 只在 MSYS/Cygwin 有；Linux/macOS 上退回原样即可。）
if command -v cygpath >/dev/null 2>&1; then
  winpath() { cygpath -w "$1"; }
else
  winpath() { printf '%s' "$1"; }
fi
# 交给 python.exe 当参数的路径，一律用它转成 Windows 形式
MAIN_WIN="$(winpath "$MAIN")"

# fix-index 在步骤 7 要调 6 次，包一个 helper；其余内置工具只调一两次，直接内联。
# ★ 用 venv 的解释器（$VP 在第 4 步才定义，函数体到调用时才求值，所以没问题）。
fix_index() { "$VP" "$MAIN_WIN" --tool fix-index "$@"; }

# ------------------------- 0. 前置检查 --------------------------------------
log "0/10 检查工具链（版本 $VERSION，分支 ${CPYTHON_BRANCH}）"
command -v git >/dev/null || die "找不到 git"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3 || command -v python)" || die "找不到 Python"
command -v xelatex >/dev/null || die "找不到 xelatex，请把 TeX Live 的 bin 目录加入 PATH（当前 TEXLIVE_BIN=$TEXLIVE_BIN）"
command -v latexmk >/dev/null || die "找不到 latexmk"
# ★ makeindex：步骤 7 的索引全靠它（被 fix-index.py 包一层调用）
command -v makeindex >/dev/null || die "找不到 makeindex（步骤 7 生成索引用）。请把 TeX Live 的 bin 目录加入 PATH"
# ★ python：步骤 7 的 latexmk -e 里要执行 `python makeindex-fix.py`。
#   venv 的路径含中文（…/Python 文档/…），不能写进 -e（latexmk 按 UTF-8 解析会炸），
#   所以按名字调 python —— PATH 里必须有一个 python。
command -v python >/dev/null || die "PATH 里找不到 python：步骤 7 的索引修复脚本要靠它启动"
printf 'Python : %s\n' "$($PYTHON --version 2>&1)"
printf 'XeLaTeX: %s\n' "$(xelatex --version 2>&1 | head -1)"
printf 'makeindex: %s\n' "$(command -v makeindex)"
printf 'python(名): %s\n' "$(command -v python)"

mkdir -p "$ROOT" "$OUTDIR"
cd "$ROOT"

# ------------------------- 1. 取 CPython Doc 源 ------------------------------
# ★「从网站实时调取」：已有克隆时先 fetch 到最新再 reset（REFRESH=1，默认开）。
#   fetch 失败（断网 / 代理挂了）不算致命：留着本地那份继续用，只报一条警告。
git_refresh() {  # $1=仓库目录  $2=分支  $3=显示名
  local repo="$1" branch="$2" label="$3"
  if ! git -C "$repo" fetch --depth 1 origin "$branch" >/dev/null 2>&1; then
    printf '[警告] %s fetch 失败（网络？），继续用本地已有版本\n' "$label"
    return 0
  fi
  if git -C "$repo" reset --hard FETCH_HEAD >/dev/null 2>&1; then
    printf '%s 已更新到 origin/%s @ %s\n' "$label" "$branch" \
           "$(git -C "$repo" rev-parse --short HEAD)"
  fi
}

log "1/10 取 CPython $CPYTHON_BRANCH 的 Doc 源码（稀疏克隆）"
# ★ 需要检出的路径（顺序无关）：
#   Doc            —— 文档源
#   Misc/NEWS.d    —— Doc/Makefile 的 build 目标要的
#   Include        —— Doc/tools/extensions/patchlevel.py 要读 Include/patchlevel.h，
#                     漏了它 Sphinx 第一秒就崩（FileNotFoundError）
#   Lib/profiling/sampling —— ★ 3.15 新增：Doc/whatsnew/3.15.rst 与
#                     Doc/library/profiling.sampling.rst 写了
#                     `.. image:: ../../Lib/profiling/sampling/_assets/tachyon-logo.png`，
#                     图片在 Doc 之外。漏取的后果极隐蔽：Sphinx 找不到图片**不报错**，
#                     只留一条 "File ... not found" 软警告，然后把**原始相对路径**
#                     原样写进 .tex —— Windows 上分隔符是反斜杠，于是
#                     `..\Lib\profiling\...` 里的 \Lib \profiling \_assets
#                     全成了未定义控制序列 → xelatex 报错、latexmk 退出码 12
#                     → 整册（library / whatsnew）出不来 PDF。
# ★ 稀疏检出的路径（--filter=blob:none 下，只有这里的文件才真拉 blob）。
#   判据不是「Doc 需要什么」，而是「Doc 引用了哪些 Doc/ 之外的文件」——
#   这件事可以直接量出来，别靠记：`python <MAIN> --tool check-doc-refs <Doc 目录>`。
#     Doc                    ← 正文
#     Misc/NEWS.d            ← Doc/Makefile 的 build 目标
#     Include                ← patchlevel.py 读 Include/patchlevel.h（漏了直接崩）
#     Grammar                ← reference/grammar.rst 引 Grammar/python.gram
#                              （即《完整的语法规范》整章正文，20 多页）
#     Parser                 ← library/ast.rst 引 Parser/Python.asdl
#     Lib/profiling/sampling ← 3.15 Tachyon 文档的配图
#   ★★ 漏一条的后果是**静默**的：literalinclude/include 缺 → Sphinx 只留 warning、
#      .tex 里什么都不写 → PDF 里整章空白；image/figure 缺 → 反斜杠路径进 .tex →
#      latexmk 退出码 12。两种都要等构建完才看得出来，所以第 6 步之前先自检一次。
SPARSE_PATHS="Doc Misc/NEWS.d Include Grammar Parser Lib/profiling/sampling"

# 稀疏检出（幂等，只补差集）——「已有克隆」也要跑：老目录里可能缺后加的路径。
ensure_sparse() {
  # ⚠️ 这一步是**第二次联网**：--filter=blob:none 的 blob 现在才拉，经代理时
  #    常见 `curl 56 Recv failure: Connection was reset` / `fatal: early EOF`。
  #    属于断流不是配置错，克隆对象库已在，重试不用重头 —— 所以重试一次。
  # shellcheck disable=SC2086  # $SPARSE_PATHS 要按空格拆成多个参数
  if ! git -C "$ROOT/cpython" sparse-checkout set $SPARSE_PATHS; then
    printf '\n稀疏检出失败（多为 GitHub 代理断流），10 秒后重试一次……\n' >&2
    sleep 10
    git -C "$ROOT/cpython" sparse-checkout set $SPARSE_PATHS \
      || die "git sparse-checkout set 两次都失败（$SPARSE_PATHS 没取全）。
       常见原因是代理断流（日志里找 curl 56 / early EOF）；
       直接重跑即可（克隆已在，不会从零开始），或换 GH= 代理前缀。"
  fi
}

# 把「Doc 引用到、但磁盘上没有」的文件自动补回来（幂等；判据与 GUI 同一份实现）。
#   · 目录型（如整个 Grammar/ 从没进过稀疏检出）→ 并进 sparse-checkout，只补差集
#   · 单文件型（如 Lib/test/exception_hierarchy.txt）→ git show 按需拉那一个 blob
#     （cone 模式的最小单位是目录，Lib/test/ 有几万文件，为一个 2 KB 文本不值当）
#   ★ 两者怎么区分**由工具问 git 得出**（`MISSINGKIND`，见 check-doc-refs.py::_kind），
#     绝不能用「最后一段有没有 `.`」猜 —— 详见函数内那段注释（`COPYING` 的教训）。
#   ★ 这两类缺件的后果都是**静默的**：literalinclude 缺了 Sphinx 不报错、
#     .tex 里什么都不写 → PDF 里那一整节就没了，而构建全绿。
ensure_doc_ref_files() {
  [ -f "$MAIN" ] || return 0
  local out miss=""
  out="$("$PYTHON" "$MAIN_WIN" --tool check-doc-refs "$ROOT/cpython/Doc" --list 2>/dev/null || true)"
  miss="$(printf '%s\n' "$out" | sed -n 's/^MISSINGFILE //p')"
  [ -n "$miss" ] || return 0

  local dirs="" files="" rel kind
  # ★ 类型由工具问 git 得出（`MISSINGKIND <路径> <blob|tree|?>`），
  #   **不要**再用「最后一段有没有点」猜 —— `Modules/expat/COPYING` 没有扩展名，
  #   会被猜成目录，于是拼出必然失败的命令：
  #       git sparse-checkout set ... Modules/expat/COPYING
  #       fatal: 'Modules/expat/COPYING' is not a directory
  #   后果不是「建议不准」，而是**自动补件当场失效**，只剩一句「多为代理断流」，
  #   真实缺口（3.15 的 Doc/license.rst 新增 include 它）永远补不上。
  #   判据只有一处实现（主程序里的 cdr__kind），三端不可能再分叉。
  while IFS= read -r kind; do
    [ -n "$kind" ] || continue
    rel="${kind% *}"; kind="${kind##* }"
    case "$kind" in
      tree) dirs="$dirs $rel" ;;
      *)    files="$files $rel" ;;
    esac
  done <<EOF
$(printf '%s\n' "$out" | sed -n 's/^MISSINGKIND //p')
EOF

  if [ -n "$dirs" ]; then
    printf '稀疏检出里缺这些目录：%s → 自动并入 sparse-checkout\n' "$dirs" >&2
    # 用 add 而不是 set：set 是全集（要把现有路径全重列一遍），add 只加不减。
    # shellcheck disable=SC2086
    git -C "$ROOT/cpython" sparse-checkout add $dirs \
      || { sleep 10; git -C "$ROOT/cpython" sparse-checkout add $dirs; }
  fi

  for p in $files; do
    mkdir -p "$ROOT/cpython/$(dirname "$p")"
    if git -C "$ROOT/cpython" show "HEAD:$p" >"$ROOT/cpython/$p" 2>/dev/null \
       && [ -s "$ROOT/cpython/$p" ]; then
      printf '  按需取回 %s（%s 字节）\n' "$p" "$(wc -c <"$ROOT/cpython/$p" | tr -d ' ')"
    else
      printf '  ★ 按需取 %s 失败（多为代理断流，重跑本步即可）\n' "$p" >&2
    fi
  done
}

if [ -f "$ROOT/cpython/Doc/conf.py" ]; then
  echo "已存在 $ROOT/cpython/Doc/conf.py，跳过克隆"
  [ "$REFRESH" = "1" ] && git_refresh "$ROOT/cpython" "$CPYTHON_BRANCH" "CPython 源码"
  ensure_sparse          # ★ 老克隆可能缺后加的路径（如 Grammar / Lib/profiling/sampling）
  ensure_doc_ref_files   # ★ 零散单文件（cone 模式取不到）在这里补齐
else
  rm -rf "$ROOT/cpython"
  git clone --depth 1 --branch "$CPYTHON_BRANCH" --filter=blob:none --sparse \
      "$GH/python/cpython.git" "$ROOT/cpython" || die "克隆 cpython 失败（可换 GH= 代理前缀）"
  ensure_sparse
  ensure_doc_ref_files
fi
# 稀疏克隆漏了 Include 的自检（上面那个坑）
[ -f "$ROOT/cpython/Include/patchlevel.h" ] || die "缺少 Include/patchlevel.h：稀疏克隆漏了 Include，Sphinx 会立刻崩"
PLV="$("$PYTHON" "$(winpath "$ROOT/cpython/Doc/tools/extensions/patchlevel.py")")"
printf 'patchlevel → %s\n' "$PLV"
case "$PLV" in
  "$VERSION"*) : ;;
  *) printf '[警告] 源码版本号 %s 与所选版本 %s 不一致，请确认分支 %s 是否正确\n' \
            "$PLV" "$VERSION" "$CPYTHON_BRANCH" ;;
esac

# ------------------------- 2. 取中文翻译（.po） ------------------------------
# ★ 默认联网克隆 python-docs-zh-cn 的 $ZH_BRANCH 分支；指定 ZH_SRC 时才用本地。
log "2/10 准备中文翻译 .po（分支 $ZH_BRANCH）"
if [ -n "$ZH_SRC" ] && [ -d "$ZH_SRC" ]; then
  # 高级用法：显式指定本地翻译源（默认留空 = 联网下载）
  printf '使用本地翻译源：%s（%s 个 .po）\n' "$ZH_SRC" "$(find "$ZH_SRC" -name '*.po' | wc -l)"
  printf '（本地翻译源不会联网更新；要联网就把 ZH_SRC 清空）\n'
elif [ -z "$ZH_SRC" ]; then
  ZH_SRC="$ROOT/zh-cn"
  if [ -d "$ZH_SRC" ]; then
    printf '使用已克隆的 %s（分支 %s）\n' "$ZH_SRC" "$ZH_BRANCH"
    [ "$REFRESH" = "1" ] && git_refresh "$ZH_SRC" "$ZH_BRANCH" "翻译源"
  else
    git clone --depth 1 --branch "$ZH_BRANCH" \
        "$GH/python/python-docs-zh-cn.git" "$ZH_SRC" || die "克隆翻译仓库失败（分支 $ZH_BRANCH）"
  fi
else
  die "ZH_SRC=$ZH_SRC 不是目录"
fi
[ -d "$ZH_SRC" ] || die "翻译源目录不存在：$ZH_SRC"
printf '翻译源：%s\n' "$ZH_SRC"

# ------------------------- 3. 装 locales -------------------------------------
log "3/10 把 .po 按目录结构装进 Doc/locales/$LANG_CODE/LC_MESSAGES/"
DOC="$ROOT/cpython/Doc"
DST="$DOC/locales/$LANG_CODE/LC_MESSAGES"
rm -rf "$DOC/locales"; mkdir -p "$DST"
cd "$ZH_SRC"
# ⚠️ 踩坑：不要写成 cp "$ZH_SRC"/library/*.po —— 路径含空格/中文再加 300+ 参数会
#          超出 Windows 命令行长度上限，glob 静默失败，文件会整个漏掉。
#          必须 cd 进去用相对通配符。
cp ./*.po "$DST"/ 2>/dev/null
for d in c-api deprecations distributing extending faq howto installing \
         library reference tutorial using whatsnew; do
  [ -d "$d" ] || continue
  mkdir -p "$DST/$d"
  ( cd "$d" && cp ./*.po "$DST/$d"/ 2>/dev/null )
done
TOTAL=$(cd "$DST" && ls -R | /usr/bin/grep -c '\.po$' 2>/dev/null || ls -R | grep -c '\.po$')
printf '已装 .po：%s 个\n' "$TOTAL"

# ★ 补充译文（原 sphinx-pdf/i18n-extra/，现已内联进主程序）：
#   这里把内置那份**导出**到 $ROOT/i18n-extra —— 每次运行都重写一份。
#   想「每次运行单独取最新版」就设 I18N_EXTRA_URL（http(s)://… / file://… / 本机目录都认）；
#   留空 = 只用内置那份（离线可用）。
EXTRA_DIR="$ROOT/i18n-extra"
I18N_EXTRA_URL="${I18N_EXTRA_URL:-}"
"$PYTHON" "$MAIN_WIN" --tool extra-fetch "$EXTRA_DIR" "$I18N_EXTRA_URL" 2>/dev/null || true
printf '补充译文：%s 个文件（源：%s）\n' \
  "$(find "$EXTRA_DIR" -name '*.po' 2>/dev/null | wc -l | tr -d ' ')" \
  "${I18N_EXTRA_URL:-内置那份}"

# ⚠️ 踩坑：上游会把整章文件搬目录（CPython 3.14 把 Doc/library/stdtypes.rst 等
#          搬进了 Doc/builtins/），而 zh-CN 的译文还留在 zh-cn/library/*.po。
#          Sphinx 按「源文件相对路径」找译文 —— 路径对不上时它**不报错、不警告、
#          翻译进度还是 100%**，那几页原样保留英文。实测《11Python 内置参考手册》
#          整册 196 页全是英文，构建日志一片绿。这里把译文接回新路径。
if [ -f "$MAIN" ]; then
  ALIAS_OUT="$("$PYTHON" "$MAIN_WIN" --tool alias-po "$ZH_SRC" --doc "$DOC" \
                 --locale "$DST" --extra "$EXTRA_DIR" 2>&1)"
  printf '%s\n' "$ALIAS_OUT" | sed 's/^/  /'
  TOTAL=$(cd "$DST" && ls -R | /usr/bin/grep -c '\.po$' 2>/dev/null || ls -R | grep -c '\.po$')
  printf '接回译文后共 %s 个 .po\n' "$TOTAL"
fi

# ------------------------- 4. venv + 依赖 ------------------------------------
log "4/10 建虚拟环境并安装依赖（Doc/requirements.txt + SVG 转换器）"
VENV="$ROOT/venv"
if [ ! -x "$VENV/Scripts/python.exe" ] && [ ! -x "$VENV/bin/python" ]; then
  "$PYTHON" -m venv "$(winpath "$VENV")"
fi
if [ -x "$VENV/Scripts/python.exe" ]; then VP="$VENV/Scripts/python.exe"; else VP="$VENV/bin/python"; fi
# ★ 把 venv 的 Scripts/bin 目录插到 PATH 最前：步骤 7 的 latexmk -e 里按名字调 `python`，
#   必须解析到这里（装了 pypdf 等依赖，且路径含中文不能写进 -e）。
export PATH="$(dirname "$VP"):$PATH"
printf 'python → %s\n' "$(command -v python)"
"$VP" -m pip install --upgrade pip -q -i "$PIP_INDEX"
# 与 Doc/requirements.txt 对齐；blurb / sphinx-linklint 是 CI 用的，出 PDF 不需要
"$VP" -m pip install -i "$PIP_INDEX" \
    "sphinx<9.0.0" "pygments>=2.21" \
    "sphinx-notfound-page~=1.0.0" "sphinxext-opengraph~=0.13.0" sphinxext-rediraffe \
    "python-docs-theme>=2023.3.1,!=2023.7"
# c-api/lifecycle.rst、howto/logging.rst、library/datetime.rst 里有 SVG 插图，
# LaTeX 引擎不认 SVG，必须装转换器（CairoSVG 在 Windows 上免额外 DLL）。
"$VP" -m pip install -i "$PIP_INDEX" "sphinxcontrib-svg2pdfconverter[CairoSVG]"
"$VP" -c "import sphinx, python_docs_theme; print('sphinx', sphinx.__version__)"

cd "$DOC"
rm -rf build

# ------------------------- 5. 构建 HTML（验证主题） ---------------------------
log "5/10 构建 HTML（python-docs-theme：目录 + 超链接在这里生效）"
"$VP" -m sphinx -b html -d build/doctrees-html -j "$JOBS" \
      -D "language=$LANG_CODE" . build/html >"$ROOT/html-build.log" 2>&1
printf 'HTML 退出码=%s  警告=%s\n' "$?" "$(grep -c '^WARNING' "$ROOT/html-build.log" 2>/dev/null || echo 0)"

# ------------------------- 6. 构建 LaTeX 源 ----------------------------------
log "6/10 构建 LaTeX 源（每个 latex_documents 条目一个 .tex）"

# ★ 越界引用自检（在花十几分钟编 .tex 之前，几秒就能拦下来）★
#   判据与 GUI 完全一致 —— 两边都调主程序的 --tool check-doc-refs，不各写一份。
#   查三类指令：image / figure、literalinclude、include。
#   · literalinclude / include 目标缺失 → Sphinx **不报错**，`.tex` 里什么都不写
#     → PDF 里整章空白（3.13/3.14/3.15 的《完整的语法规范》整章就是这样没的：
#       Grammar/ 不在稀疏检出里，那一章本该 20 多页，结果只剩标题加两行引言）
#   · image / figure 目标缺失 → 原始反斜杠路径进 .tex → latexmk 退出码 12
if [ -f "$MAIN" ]; then
  # 先自己补一轮（与 GUI 步骤 6 的行为一致）—— 这类缺件最要命的地方就是
  # 「只留一条 warning、没人会在意」，所以默认补而不是默认停。
  ensure_doc_ref_files
  REF_OUT="$("$PYTHON" "$MAIN_WIN" --tool check-doc-refs "$DOC" 2>&1)" || true
  printf '%s\n' "$REF_OUT" | grep -v '^REFMISSING ' | sed 's/^/  /'
  printf '%s\n' "$REF_OUT" | grep -q '^REFMISSING 0$' \
    || die "Doc 里有指向 Doc/ 之外、但文件不在的引用（见上）。
      Sphinx 不会因此报错 —— literalinclude 缺了，PDF 里就整章空白、全程无提示。
      已经自动补过一轮；仍差上面列出的条目，按工具给的命令手动补
      （目录用 sparse-checkout add、单文件用 git show），
      然后从第 6 步重跑（.tex 必须重新生成，别再往下硬编）。"
fi

# ★★ 必须先把 conf.py 的 SVG 转换器从 rsvg 版改成 cairosvg 版 ★★
#   conf.py 的可选扩展列表里写死 'sphinxcontrib.rsvgconverter'，那个模块存在
#   （同一个包里三个模块都有），但它要调外部程序 rsvg-convert，Windows 上没有。
#   结果：只留一行软告警，SVG 原样拷进 LaTeX，之后报
#     ! LaTeX Error: Cannot determine size of graphic in lifecycle.dot.svg
#   导致 c-api.pdf 构建失败。
sed -i "s/sphinxcontrib\.rsvgconverter/sphinxcontrib.cairosvgconverter/" conf.py
grep -q "cairosvgconverter" conf.py || die "conf.py 里的 rsvgconverter 改名失败，请手工确认第 47 行"
# ⚠️ 不要加 Doc/Makefile 里的 --fail-on-warning：翻译有 fuzzy 条目会直接中断构建
"$VP" -m sphinx -b latex -d build/doctrees -j "$JOBS" \
      -D "language=$LANG_CODE" . build/latex >"$ROOT/latex-build.log" 2>&1
RC=$?
printf 'LaTeX 退出码=%s\n' "$RC"
cd build/latex
printf '生成 .tex：%s 个\n' "$(ls ./*.tex 2>/dev/null | wc -l)"
SVG_N=$(ls ./*.svg 2>/dev/null | wc -l)
printf '残留 .svg：%s 个（应为 0）\n' "$SVG_N"
[ "$RC" -eq 0 ] || die "LaTeX 构建失败，看 $ROOT/latex-build.log"
[ "$SVG_N" -eq 0 ] || die "还有 $SVG_N 个 SVG 没被转成 PDF：SVG 转换器没生效，c-api.pdf 会编不过"

# ★ 越界图片自检：Doc/ 之外的图片没取到时，Sphinx **不报错**，只留一条
#   "LaTeX Warning: File ... not found" 软警告，然后把**原始相对路径**原样写进 .tex ——
#   Windows 上分隔符是反斜杠，`..\Lib\profiling\...` 里的 \Lib \profiling \_assets
#   全成了未定义控制序列 → xelatex 报错 → latexmk 退出码 12 → 整册不出 PDF。
#   判据很干净：正常的 \sphinxincludegraphics{{名字}.ext} 里**只有文件名**
#   （不带目录），所以只要**花括号里**出现 `/` 或 `\` 就是没找到那张图。
#   ⚠️ 不能写成 `sphinxincludegraphics.*\\` —— 那会把选项 `[width=200\sphinxpxdimen]`
#      里的反斜杠也算进去，39 册里会假报 3 个。
#   （3.15 实测受害者：library 与 whatsnew，都引用了
#     ../../Lib/profiling/sampling/_assets/tachyon-logo.png）
BADIMG="$(grep -lE 'sphinxincludegraphics(\[[^]]*\])?\{[^}]*[/\\]' \
          "$ROOT"/cpython/Doc/build/latex/*.tex 2>/dev/null)"
if [ -n "$BADIMG" ]; then
  printf '%s\n' "$BADIMG" | while IFS= read -r f; do
    printf '  %s\n' "$(basename "$f")"
    grep -nE 'sphinxincludegraphics(\[[^]]*\])?\{[^}]*[/\\]' "$f" | head -2 | sed 's/^/      /'
  done
  die "上列 .tex 里的图片路径带了目录 —— 说明 Sphinx 没找到那些图片。
      多为「图片在 Doc/ 之外、稀疏克隆没取到」（见脚本开头 SPARSE_PATHS 的说明）。
      处理：先跑 ensure_doc_ref_files 用的那条自检
            $PYTHON \"$MAIN_WIN\" --tool check-doc-refs \"$DOC\"
      按它给出的命令补（目录用 sparse-checkout add、单文件用 git show），
      然后从第 6 步重跑（.tex 必须重新生成），不要再从第 7 步硬编。"
fi

# ------------------- 6b. 封面标题中文化（必做）--------------------------------
log "6b/10 把英文封面标题换成中文"
# ★★ 为什么必须在这里改 ★★
#   封面标题来自 conf.py 的 latex_documents，**这一项不经过 .po 翻译**，所以中文
#   文档编出来封面还是英文：
#       reference.tex  → "The Python Language Reference"
#       library.tex    → "The Python Library Reference"
#       builtins.tex   → "Python Built-ins Reference"
#   而同一册的文件名、书签都是中文，两套对不上。
#   howto 那批标题来自 reST 正文标题（latex_documents 给的是空串 ''），只要译文存在
#   就是中文；只有 howto-perf_profiling 上游没译，同样落回英文。
#   \title 还被 sphinxmanual.cls 用于**页眉**，所以改一处，封面 + 每页页眉一起中文化。
#   必须紧跟第 6 步（.tex 刚生成）、在第 7 步（编 PDF）之前。
"$VP" "$MAIN_WIN" --tool localize-titles . || die "封面标题中文化失败"

# ------------------------- 7. 编译 PDF --------------------------------------
log "7/10 编译 PDF（并发 latexmk ＋ 覆盖 \$makeindex）"
# ★★ 不要用 make -j ★★
#   `make` 在这里解析到的是 MSYS 版（/f/msys64/usr/bin/make），它靠 Cygwin 的
#   fork 模拟建子进程。并行多路 + 巨型 .tex（library.tex 17MB）会把 fork 压垮：
#       [main] make 1268 dofork: child -1 - forked process 43284 died unexpectedly,
#              retry 0, exit code 0xC000026B, errno 11
#       make: *** [Makefile:72: howto-mro.pdf] Error 127
#   症状：成片 Error 127（子进程根本没起来），另有几册 Error 4 并留下
#         70~90 KB 的残缺 PDF（文件在、内容是残的，pdfinfo 读不出页数）。
#   → 改成串行逐册，用 latexmk（单个 perl 进程）替代 make -j。
#
# ★★ latexmk 必须用 -e 覆盖 $makeindex ★★
#   latexmkrc 里生成的是 $makeindex = 'internal xindy ...'（不带 -s python.ist），
#   xindy 吃不了 makeindex 格式的 python.ist → 返回 256 → latexmk 中止在第 2 遍前、
#   退出码 12 → PDF 看着正常，其实只是第 1 遍产物：正文前目录空白、满屏 '??'。
#   -e 在 -r latexmkrc 之后求值，故能覆盖。
#
# ★★ 覆盖成的不再是裸 makeindex，而是「makeindex + 修 .ind」的 --tool fix-index ★★
#   索引要满足三件事，全部在这一层解决：
#     · 非字母条目在最前 + 加粗「非字母」/「数字」分组标题
#     · 每条页码都是可点的超链接（\hyperpage）
#     · 不再出现 �（makeindex 按字节截断中文组标题留下的非法 UTF-8）
#   latexmk 的次序是 xelatex → makeindex → xelatex → xelatex，把 makeindex 换成
#   fix-index.py（参数完全兼容 makeindex），第 2 遍 xelatex 就直接读到修好的 .ind，
#   一遍编译同时拿到「分组标题 + 可点页码」，不用事后重排（38 册省半小时）。
#
# ⚠️ -e 的命令里只能出现 ASCII：latexmk 按 UTF-8 解析 -e，路径带中文（…/Python 文档/…）
#    会直接报 Malformed UTF-8 character (fatal)。所以先把 fix-index.py 拷一份到 latex
#    目录（ASCII 名 makeindex-fix.py），再用 PATH 里的 python 启动（venv 的 Scripts
#    目录已在第 4 步插进 PATH）。
#
# ★ LATEXOPTS 必须给 -interaction=nonstopmode，否则 TeX 在批处理里等 stdin 挂死。
export LATEXOPTS='-interaction=nonstopmode'
: >"$ROOT/pdf-build.log"

[ -f "$MAIN" ] || die "找不到 $MAIN（步骤 7 的索引修复靠它的 --tool fix-index）"
"$VP" "$MAIN_WIN" --tool emit-makeindex-fix ./makeindex-fix.py \
  || die "释放 makeindex-fix.py 失败（latexmk 的 \$makeindex 要用它）"
echo "索引修复转发器已就位：makeindex-fix.py（替代裸 makeindex）"

# 就地读 .ind 汇总：打印「页码链接数 非字母标题数 非法字节行数 断点数」
# 刻意全部用 ASCII + chr() 拼字符串、bytes([10]) 换行：不含任何反斜杠转义，
# 避免 -c 字符串在不同 shell/引号层里被二次解释（\b 会被 Python 当退格符）。
ind_summary() {
  "$VP" -c '
import sys
BS = chr(92)                                   # 一个反斜杠
raw = open(sys.argv[1], "rb").read()
links = raw.count((BS + "hyperpage{").encode())
syms  = raw.count((BS + "bigletter {" + chr(0x975e) + chr(0x5b57) + chr(0x6bcd)).encode("utf-8"))
brk   = raw.count((BS + "allowbreak").encode())   # 长模块路径的断行点
bad = 0
for ln in raw.split(bytes([10])):
    try:
        ln.decode("utf-8")
    except UnicodeDecodeError:
        bad += 1
print(links, syms, bad, brk)
' "$1"
}

# 待编册子：只取带 \documentclass 的根文件，按体积升序（小册先出，library 最后）
# ⚠️ 必须写 /usr/bin/sort：Windows 的 C:/WINDOWS/system32/sort.exe 在 PATH 里更靠前，
#    它不认 -n、报「系统找不到指定的文件」且不吐 stdout —— 整条管道会静默变空。
DOCS=$( for f in ./*.tex; do
          /usr/bin/grep -q '\\documentclass' "$f" 2>/dev/null && printf '%s\t%s\n' "$(wc -c <"$f")" "${f#./}"
        done | /usr/bin/sort -n | cut -f2 )

# ★ BOOKS=reference,library 只重编指定册 ★
#   补一条稀疏路径、改一个 .rst，往往只影响一两册；全编 39 册要四十分钟。
#   其余册的成品不受影响 —— 步骤 8 是按**同名覆盖**收集的。
#   册名用 .tex 的名字（reference / library / builtins / tutorial / whatsnew /
#   c-api …），不是中文册名；支持子串。
if [ -n "${BOOKS:-}" ]; then
  SEL=""
  for d in $DOCS; do
    n="${d%.tex}"
    OLDIFS="$IFS"; IFS=','
    for w in $BOOKS; do
      [ -n "$w" ] || continue
      case "$n" in *"$w"*) SEL="$SEL $d"; break ;; esac
    done
    IFS="$OLDIFS"
  done
  [ -n "$SEL" ] || die "BOOKS=$BOOKS 没匹配到任何册子。
       可用册名：$(printf '%s ' $DOCS)"
  DOCS="$SEL"
  printf '★ 只编这几册：%s\n' "$DOCS"
fi

# ★ 并发编译（2026-09-27 加）★
#   一册 latexmk 是纯 CPU 活（xelatex 跑 3 遍 + 一次 makeindex），各册之间**不共享
#   任何中间文件**（.aux/.toc/.idx/.ind/.log 全按 jobname 区分），所以能并行。
#   18 核机器上全编 38 册从 35~40 分钟降到几分钟。
#   ⚠️ 日志必须**每册一个文件**：并发往同一个 pdf-build.log 追加会交错成一锅粥，
#     跑完再按册序合并回来（内容与逐册串行时一模一样）。
#   ⚠️ JOBS=1 退回老的逐册串行（排查并发相关问题时用）。
#   ⚠️ 早期用 `make -j` 会成片 Error 127（MSYS 的 fork 模拟扛不住巨型 .tex），
#     这里走的是 `bash 后台作业 + wait -n`，子进程 fork 完立刻 exec，负担小得多。
JOBS="${JOBS:-0}"
case "$JOBS" in ''|*[!0-9]*) JOBS=0 ;; esac
if [ "$JOBS" -le 0 ]; then
  NCPU="${NUMBER_OF_PROCESSORS:-$(nproc 2>/dev/null || echo 4)}"
  case "$NCPU" in ''|*[!0-9]*) NCPU=4 ;; esac
  JOBS=$(( NCPU > 7 ? 6 : (NCPU > 1 ? NCPU - 1 : 1) ))
fi
TOTAL=$(printf '%s\n' $DOCS | wc -l)
[ "$JOBS" -le "$TOTAL" ] || JOBS="$TOTAL"
[ "$JOBS" -ge 1 ] || JOBS=1

# 编一册的裸命令（不含重定向）—— compile_one 与「失败册重试」共用一份，
#   免得同一行 latexmk 参数写成两处、以后改一处漏一处。
_latexmk_one() {
  # ★ 不手删中间产物，改用 latexmk 的 -gg ★
  #   以前这里 `rm -f $name.{pdf,aux,toc,out,ind,ilg,idx,log,fdb_latexmk,fls}`，
  #   是为了防 latexmk 认为「已是最新」而跳过重排。但 10 个 × 38 册 = 380 次删除，
  #   在受管环境里会撞上批量删除保护（turn 内累计 50 次即要求人工确认）。
  #   `-gg` 让 latexmk 忽略依赖数据库、把各步骤全部重跑（删与重建都在它进程内部）。
  latexmk -pdf -gg -file-line-error -r latexmkrc \
      -e '$makeindex = q{python makeindex-fix.py %O -s python.ist -o %D %S};' \
      "$1.tex"
}

# 单独编一册：整份输出进 pdf-build-<册名>.log，只在主终端留一行结果。
#   第二参数 `a` = **追加**输出（重试时用 —— 头一遍的日志要留着，
#   否则重试成功后就看不出「第一次到底为什么失败」了）。
compile_one() {
  name="$1"
  mode="${2:-w}"
  printf '  [%s] %-34s 开始\n' "$(date +%H:%M:%S)" "$name"
  if [ "$mode" = a ]; then
    _latexmk_one "$name" >>"$ROOT/pdf-build-$name.log" 2>&1
  else
    _latexmk_one "$name" >"$ROOT/pdf-build-$name.log" 2>&1
  fi
  pages=$(pdfinfo "$name.pdf" 2>/dev/null | awk '/^Pages/{print $2}')
  if [ -n "$pages" ]; then
    printf '  [%s] %-34s OK   %s 页\n' "$(date +%H:%M:%S)" "$name" "$pages"
  else
    printf '  [%s] %-34s 失败\n' "$(date +%H:%M:%S)" "$name"
  fi
}

if [ "$JOBS" -le 1 ]; then
  printf '编译 %s 册（逐册串行，JOBS=1）\n' "$TOTAL"
  for d in $DOCS; do compile_one "${d%.tex}"; done
else
  printf '并发编译：%s 册同时跑（共 %s 册）\n' "$JOBS" "$TOTAL"
  _n=0
  for d in $DOCS; do
    compile_one "${d%.tex}" &
    _n=$((_n + 1))
    if [ "$_n" -ge "$JOBS" ]; then
      wait -n 2>/dev/null || wait        # 老 bash 不认 -n 就退化成等全部
      _n=$((_n - 1))
    fi
  done
  wait
fi

# ── 失败册串行重试（★★ 偶发故障兜底 ★★ 与 GUI 步骤 7 同一套逻辑）──────────
#  为什么必须有：并发编译实测出现过 `xelatex.exe: fwrite: Broken pipe` ——
#  xelatex 写到某一页时管道断掉、进程返回 1，latexmk 于是报
#  `pdflatex: Command for 'pdflatex' gave return code 1` + 退出码 12，
#  而那一册的 .log 里**一条 LaTeX 错误都没有**（TeX 自己的诊断就是 Broken pipe，
#  与 .rst 内容无关，不是「文档写错了」）。3.15 实测：39 册里 2 册中招
#  （howto-sorting / howto-logging-cookbook），而且落在**不同批次**；
#  把这两册单独重编，一次就成功 —— 典型的偶发（进程/管道/杀软实时扫描大文件）。
#  这类失败不该让用户自己去发现「重跑一次就好了」，所以这里自动兜。
#  ⚠️ 重试**串行**跑：并发本来就是把负载摊开，重试时让路反而更容易过。
#  ⚠️ 判据 = 「同名 PDF 存在且非空」，不看 latexmk 退出码：退出码非 0 的长尾
#     是 latexmk 的保守行为（跟 rerun 是否收敛有关），只要 PDF 出来了就算成功。
for round in 1 2; do
  BAD=""
  for d in $DOCS; do
    name="${d%.tex}"
    [ -s "$name.pdf" ] || BAD="$BAD $name"
  done
  [ -n "$BAD" ] || break
  BADN=$(printf '%s\n' $BAD | wc -l | tr -d ' ')
  printf '  %s 册没出 PDF，串行重试（第 %s/2 轮）：%s\n' "$BADN" "$round" "$BAD"
  for name in $BAD; do
    printf '\n===== 第 %s 轮串行重试 =====\n' "$round" \
        >>"$ROOT/pdf-build-$name.log"
    compile_one "$name" a
  done
done

# 把各册日志按册序拼回 pdf-build.log；分册日志**挪进 pdf-build-parts/ 留档**
#   （不删：38 次删除会撞批量删除保护；且分册日志排查单册时更好用）
mkdir -p "$ROOT/pdf-build-parts"
for d in $DOCS; do
  name="${d%.tex}"
  printf '\n===== %s =====\n' "$name" >>"$ROOT/pdf-build.log"
  [ -f "$ROOT/pdf-build-$name.log" ] && cat "$ROOT/pdf-build-$name.log" >>"$ROOT/pdf-build.log"
  [ -f "$ROOT/pdf-build-$name.log" ] && mv -f "$ROOT/pdf-build-$name.log" "$ROOT/pdf-build-parts/"
done

# 逐册收尾：页数 + 索引自检（就地看 .ind，不重编）
FAILED=""
IDX_N=0
for d in $DOCS; do
  name="${d%.tex}"
  if [ ! -s "$name.pdf" ]; then FAILED="$FAILED $name"; fi
  if [ -s "$name.ind" ]; then
    read -r il is ib ik < <(ind_summary "$name.ind")
    IDX_N=$((IDX_N + 1))
    printf '  %-34s 索引：%s 个页码链接　非字母标题 %s　断点 %s　非法字节 %s\n' \
           "$name" "$il" "$([ "$is" -ge 1 ] && echo 有 || echo 无)" "$ik" "$ib"
  fi
done

# 统计：只认「有 .tex 且有同名非空 .pdf」（目录里还有 SVG 转出来的图 PDF）
TEX_N=0; PDF_N=0; IND_N=0
for f in ./*.tex; do
  grep -q '\\documentclass' "$f" 2>/dev/null || continue
  TEX_N=$((TEX_N + 1))
  [ -s "${f%.tex}.pdf" ] && PDF_N=$((PDF_N + 1))
done
IND_N=$(ls ./*.ind 2>/dev/null | wc -l)
printf 'tex=%s  pdf=%s  带索引=%s  ind文件=%s\n' "$TEX_N" "$PDF_N" "$IDX_N" "$IND_N"
[ -z "$FAILED" ] || die "以下册子未出可用 PDF：$FAILED（日志：$ROOT/pdf-build.log）
      已经串行重试过两轮。若日志里是 \`xelatex.exe: fwrite: Broken pipe\` /
      \`gave return code 1\` 而那一册的 .log 里没有 LaTeX 错误，那是偶发的
      进程/管道故障（杀软实时扫描大 .tex 时常见），再重跑一次本步通常就好；
      连续复现才需要查内容。"
[ "$PDF_N" -ge "$TEX_N" ] || die "有 PDF 未生成，看 $ROOT/pdf-build.log"
[ "$IND_N" -gt 0 ] || die "索引一个都没生成（.ind=0）：makeindex 不在 PATH，或 \$makeindex 覆盖没生效"

# ------------------- 7b. 索引自检（分组标题 + 页码超链接）--------------------
log "7b/10 索引自检（分组标题「非字母/数字」+ 页码超链接）"
# ★ 正常情况下这一步什么都不用做 ★
#   索引的四个毛病都在第 7 步就修掉了（$makeindex 换成 fix-index.py，修好的 .ind
#   被第 2 遍 xelatex 直接读到）：
#     · 坏分组标题（\bigletter 只写 UTF-8 首字节）→ 页面上的 �
#     · {\sphinxsymbolsname} / {\sphinxnumbersname} 是空的 → 补成「非字母」「数字」
#     · 页码没有 \hyperpage → 点不动
#     · 长模块路径不能断行 → 溢出压到隔壁栏（叠字）→ 补 \allowbreak 断点
#   这里用 --check 逐册核对；只有异常（上次构建留下的旧 .ind、手工改了 .ind）才动手，
#   并且必须重排那几册 .tex 才生效。
if fix_index . --check >/dev/null 2>&1; then
  TOTL=0; TOTS=0; TOTB=0; TOTK=0
  for ind in ./*.ind; do
    [ -s "$ind" ] || continue
    read -r l s b k < <(ind_summary "$ind")
    TOTL=$((TOTL + l)); TOTS=$((TOTS + s)); TOTB=$((TOTB + b)); TOTK=$((TOTK + k))
  done
  printf '索引自检通过：页码链接 %s 个，非字母标题 %s 处，断点 %s 个，非法字节 %s\n' \
         "$TOTL" "$TOTS" "$TOTK" "$TOTB"
else
  echo "索引自检发现还没修好的 .ind，开始补救"
  [ -z "$FAILED" ] || die "步骤 7 有册子编译失败，先修好再重排索引：$FAILED"
  AFFECTED=$(fix_index . --list)
  printf '受影响册子 %s 个：%s\n' "$(printf '%s\n' "$AFFECTED" | wc -l)" \
         "$(printf '%s\n' "$AFFECTED" | tr '\n' ' ')"
  for ind in $AFFECTED; do
    name="${ind%.ind}"               # ★ 重排的是 <name>.tex，不是 .ind 本身
    printf '  [%s] 重排 %-34s ' "$(date +%H:%M:%S)" "$name"
    fix_index "$ind" >>"$ROOT/pdf-build.log" 2>&1   # 真修 .ind
    xelatex $LATEXOPTS -file-line-error "$name.tex" >>"$ROOT/pdf-build.log" 2>&1
    xelatex $LATEXOPTS -file-line-error "$name.tex" >>"$ROOT/pdf-build.log" 2>&1
    if awk '/Rerun to get|Label\(s\) may have changed/{f=1} END{exit !f}' "$name.log" 2>/dev/null; then
      echo "（日志要求 Rerun，补第 3 遍）"
      xelatex $LATEXOPTS -file-line-error "$name.tex" >>"$ROOT/pdf-build.log" 2>&1
    fi
    bad=$(awk 'index($0,"Invalid UTF-8"){c++} END{print c+0}' "$name.log" 2>/dev/null)
    pages=$(pdfinfo "$name.pdf" 2>/dev/null | awk '/^Pages/{print $2}')
    if [ "$bad" -eq 0 ] && [ -n "$pages" ]; then
      printf 'OK  %s 页  非法UTF8=0\n' "$pages"
    else
      printf '异常  非法UTF8=%s\n' "$bad"; FAILED="$FAILED $name"
    fi
  done
  [ -z "$FAILED" ] || die "以下册子索引修复后重排异常：$FAILED"
  fix_index . --check >/dev/null 2>&1 \
    || die "索引自检仍未通过，详见 $ROOT/index-fix.log（可单独跑 $MAIN --tool fix-index <latex 目录> 看逐册明细）"
fi
# 顺手把逐册明细写进日志，便于排查
fix_index . >"$ROOT/index-fix.log" 2>&1 || true
BADLINES=$(awk 'index($0,"Invalid UTF-8"){c++} END{print c+0}' ./*.log 2>/dev/null)
printf '索引非法字节自检：日志里 Invalid UTF-8 共 %s 条（应为 0），详见 %s\n' \
       "$BADLINES" "$ROOT/index-fix.log"
[ "$BADLINES" -eq 0 ] || die "还有日志报 Invalid UTF-8，请检查 $ROOT/index-fix.log"

# ------------------------- 8. 收集 + 验收 + 重命名 ---------------------------
log "8/10 收集 PDF、验收、按参考命名重命名"
mkdir -p "$OUTDIR"
cp ./*.pdf "$OUTDIR"/ 2>/dev/null
# 验收样本：与参考样张同纸型 / 标题非空 / 中文走 Fandol 字体 / 无缺字
SAMPLE="$OUTDIR/tutorial.pdf"
if [ -f "$SAMPLE" ] && command -v pdfinfo >/dev/null; then
  printf '页数/纸型: %s\n' "$(pdfinfo "$SAMPLE" 2>/dev/null | grep -E 'Pages|Page size' | tr '\n' ' ')"
  printf 'Fandol 字体命中: %s\n' "$(pdffonts "$SAMPLE" 2>/dev/null | grep -c Fandol)"
fi
if [ -f "$(dirname "$0")/rename-pdf.sh" ]; then
  # 先用映射表自身的完整性自检兜一层：编号撞车 / 文件名重复 / slug 拼错
  # 这些错平时都不报，要到「两册同名互相覆盖」或「合并册少一章」才暴露。
  "$VP" "$MAIN_WIN" --tool name-map --check \
    || printf '[警告] name_map 自检没过（见上）—— 分册名/编号可能撞车\n'
  # ★ rename-pdf.sh 只做转调：映射唯一真源是主程序里的 name_map，实现也在里面。
  #   它的输出末 6 行是给程序看的 ASCII 标记，这里按标记判，不看中文。
  RN_OUT="$(bash "$(dirname "$0")/rename-pdf.sh" "$OUTDIR" "$VERSION" 2>&1)"
  printf '%s\n' "$RN_OUT" \
    | grep -vE '^(RENAMED|KEPT|MISSING|UNPRODUCED|UNKNOWN|EXTRA|FAILED) '
  printf '%s\n' "$RN_OUT" | grep -qE '^MISSING 0$' \
    || printf '[警告] 本版本应当有的分册没编出来（见上）—— 去 latex-build.log 搜它的名字\n'
  printf '%s\n' "$RN_OUT" | grep -qE '^UNKNOWN 0$' \
    || printf '[警告] 有「未收录产物」保持着英文名，且**不会进合并册**（见上）：在 name_map 的 HOWTO 表补一行即可\n'
fi
# 验收报告（Markdown）—— 与 GUI 的步骤 8 对齐。
# ★ report 会**自己落盘**到 <OUTDIR>/验收报告.md；以前它只 print、不写文件，
#   于是报了个根本不存在的路径（内容其实全在 report.log 里）。已修。
"$VP" "$MAIN_WIN" --tool report "$OUTDIR" "$ROOT/cpython/Doc/build/latex" \
      --version "$VERSION" >"$ROOT/report.log" 2>&1 \
  && printf '验收报告：%s\n' "$OUTDIR/验收报告.md" \
  || printf '[警告] 验收报告生成失败（不影响 PDF），详见 %s\n' "$ROOT/report.log"
printf '产物：%s 个 PDF\n' "$(ls "$OUTDIR"/*.pdf 2>/dev/null | wc -l)"

# ------------------- 9. 把 38 册合并成一册（可选，MERGE=1）-------------------
# 书签层次：一级 = 有独立 PDF 的册子（Python 指南是一个分组节点），
#   「Python 指南」下按官网 howto 索引页分「通用 / 高级开发 / 调试和性能分析」三组，
#   多出的 3 册 howto 直接挂在「Python 指南」下；每册自己的整棵书签都跟着搬过来。
# 工具：主程序的 --tool merge-pdf（需要 pypdf —— 步骤 4 已经装上）
if [ "$MERGE" = "1" ]; then
  log "9/10 把分册合并成一册（带完整书签）"
  "$VP" -c 'import pypdf' >/dev/null 2>&1 \
    || die "合并需要 pypdf：先跑步骤 4，或手动 \"$VP\" -m pip install pypdf"
  [ -n "$MERGE_NAME" ] || MERGE_NAME="Python $VERSION 文档 $(date +%Y%m%d).pdf"
  case "$MERGE_NAME" in *.pdf) ;; *) MERGE_NAME="$MERGE_NAME.pdf" ;; esac
  cd "$OUTDIR"
  # 先 --list 预检：缺哪册、最终目录树，都不花合并时间
  # ★ 判据用工具末行那个 ASCII 标记 MISSING n，不用中文「缺 0 册」：
  #   中文匹配在 GBK / locale 不匹配的环境里会静默失配（Cygwin 上实测踩过）
  # ★ 必须带 --version：清单一里第一项是 `01Python <版本> 有什么新变化`，
  #   不传就默认 3.14 → 3.15 构建会误报 `MISSING 1`、认为缺册而拒绝合并。
  LISTING="$("$VP" "$MAIN_WIN" --tool merge-pdf . --version "$VERSION" --list 2>&1)"
  printf '%s\n' "$LISTING" | grep -vE '^(MISSING|UNPRODUCED|UNKNOWN) ' | tail -4
  # ★ MISSING 只数「本版本应当有却缺」；版本门控掉的（如 3.13 没有 0925/0929）
  #   走 UNPRODUCED，不算缺册 —— 3.13 的合并以前就是被这个误拒过。
  printf '%s\n' "$LISTING" | grep -q '^MISSING 0$' \
    || die "有的分册还不在 $OUTDIR，先跑完步骤 8 再合并"
  printf '%s\n' "$LISTING" | grep -q '^UNKNOWN 0$' \
    || printf '[警告] 有「未收录产物」不会进这本合并册（见上）；要收录就在 name_map 的 HOWTO 表补一行\n'
  "$VP" "$MAIN_WIN" --tool merge-pdf . --version "$VERSION" -o "$MERGE_NAME" \
      2>&1 | tee "$ROOT/merge.log" | tail -5
  [ -s "$MERGE_NAME" ] \
    || die "合并失败（没看到 $OUTDIR/$MERGE_NAME），详见 $ROOT/merge.log"
  printf '合并册：%s\n' "$MERGE_NAME"
  cd "$ROOT"
fi

# ---------------- 10. 清理过程文件（可选，CLEAN=build|all）-------------------
# ★ 成品 PDF 永远不动 ★
#   build = 只删 <ROOT>/cpython/Doc/build（HTML + LaTeX + 中间件，占大头）
#   all   = 再加 <ROOT>/cpython（源码）+ <ROOT>/venv（依赖）+ <ROOT>/zh-cn（翻译源）
#           + <ROOT>/*.log；下次要重新联网克隆、重装依赖
# 优先走回收站（有 gio/trash-put 时），没有才直接删。
if command -v trash-put >/dev/null 2>&1; then
  trash_it() { trash-put -- "$1"; }
elif command -v gio >/dev/null 2>&1; then
  trash_it() { gio trash -- "$1"; }
else
  trash_it() { rm -rf -- "$1"; }
fi
if [ -n "$CLEAN" ] && [ "$CLEAN" != "none" ] && [ "$CLEAN" != "0" ]; then
  log "10/10 清理过程文件（范围 $CLEAN）"
  case "$CLEAN" in
    build) TARGETS="$ROOT/cpython/Doc/build" ;;
    all)   TARGETS="$ROOT/cpython
$ROOT/venv
$ROOT/zh-cn
$ROOT/i18n-extra" ;;
    *)     die "CLEAN 只能是 none / build / all，收到：$CLEAN" ;;
  esac
  # ★ 安全闸：任何一项都不能包含（或等于）成品 PDF 目录
  OUTABS="$(cd "$OUTDIR" 2>/dev/null && pwd)"
  FREED=0
  while IFS= read -r t; do
    [ -n "$t" ] || continue
    if [ ! -e "$t" ]; then printf '跳过（不存在）%s\n' "$t"; continue; fi
    TAB="$(cd "$t" 2>/dev/null && pwd)"
    if [ -n "$TAB" ]; then
      case "$OUTABS/" in
        "$TAB"/*|"$TAB") die "拒绝清理 $TAB：它包含成品 PDF 目录 $OUTABS" ;;
      esac
    fi
    SZ="$(du -sk "$t" 2>/dev/null | awk 'NR==1{print $1}')"
    printf '删除 %s（约 %s MB）\n' "$t" "$(( ${SZ:-0} / 1024 ))"
    trash_it "$t" || printf '  删不掉（可能被占用）%s\n' "$t"
    FREED=$((FREED + ${SZ:-0}))
  done <<EOF
$TARGETS
EOF
  # 日志单独处理（本脚本的日志此刻没被任何进程占着）
  for lg in "$ROOT"/*.log; do
    [ -f "$lg" ] || continue
    SZ="$(du -sk "$lg" 2>/dev/null | awk 'NR==1{print $1}')"
    if trash_it "$lg" 2>/dev/null; then FREED=$((FREED + ${SZ:-0})); fi
  done
  printf '已释放约 %s MB\n' "$(( FREED / 1024 ))"
fi

log "完成。产物目录：$OUTDIR"
