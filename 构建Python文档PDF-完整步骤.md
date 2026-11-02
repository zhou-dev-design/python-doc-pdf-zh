# 构建 Python 中文文档 PDF 的完整步骤

> 目标：把 Python 3.14 的**中文**文档编译成 PDF，样式与官方/参考文件一致，**目录（TOC）和超链接都要有**。
>
> 参考来源：
> - devguide `#building-the-documentation`：<https://devguide.python.org/documentation/start-documenting/#building-the-documentation>
> - devguide `#using-sphinx-build`：<https://devguide.python.org/documentation/start-documenting/#using-sphinx-build>
> - 翻译构建说明（关键）：<https://devguide.python.org/documentation/translations/translating/#how-do-i-build-a-docs-translation>
> - 翻译仓库：<https://github.com/python/python-docs-zh-cn/tree/3.14>
> - 本目录的 `Makefile`（Sphinx 的 texinfo 输出用）
> - 参考样张：`PDF(截止20251002)\python-3.14-docs-pdf-a4\docs-pdf\04Python 语言参考手册.pdf`

---

## 0. 先看结论（省时间）

有**两条路**能出 PDF，产出**完全不一样**，先选对路：

| | 路线 A：Sphinx（推荐） | 路线 B：Texinfo |
|---|---|---|
| 输入 | CPython 的 reST 源 + zh-cn 的 .po 翻译 | 本目录现成的 `python.texi` |
| 命令 | `make latex` → `build/latex` 里 `make all-pdf` | `make pdf`（即 `texi2pdf` 跑 3 遍） |
| 引擎 | XeLaTeX（`conf.py` 已写死） | pdfTeX（默认）／XeTeX（中文必须） |
| 产出 | **分册 PDF**（reference / library / tutorial / c-api / …） | 一个 6000+ 页的单体 PDF |
| 封面 | "The Python Language Reference"＋`Python Software Foundation` 地址块 | Texinfo 的朴素标题页 |
| 目录 | `\tableofcontents`，3 级 | 同左 |
| 超链接 | hyperref 内部交叉引用 + 外链脚注 | hyperref，但锚点体系不同 |
| 与参考样张一致？ | ✅ 完全一致 | ❌ 样式对不上 |

**结论：**
- 要**和参考文件《04Python 语言参考手册.pdf》一模一样** → 走**路线 A**。
- 只是想让手里这份 `python.texi` 变成一个能看的 PDF → 走**路线 B**（本目录 `Makefile` 就是干这个的，但中文必须额外改 3 处）。

> 已核实：参考样张 `04Python 语言参考手册.pdf` 的 PDF 元数据是
> `Creator: LaTeX with hyperref` / `Producer: xdvipdfmx (20220710)`，
> 即 **XeLaTeX 产物**；封面文字 `发行版本 3.14.0rc3`、`Guido van Rossum and the Python development team`、
> `Python Software Foundation / Email: docs@python.org` 分别来自 Sphinx 的本地化字符串、
> `conf.py` 的 `_doc_authors`、以及 `latex_elements['preamble']` 里的 `\authoraddress`。
> 所以它是 **CPython 的 Doc 用 Sphinx + `-D language=zh_CN` + XeLaTeX** 编出来的分册 PDF。

---

## 1. 先认清"文件"是什么

### 1.1 本目录 `python-3.14-docs-texinfo/`

这是 **Sphinx 8.2.3 的 `texinfo` builder 的输出**（中文版，Python 3.14.7，生成日期 2026-09-10），不是 reST 源：

| 文件 | 大小 | 说明 |
|---|---|---|
| `python.texi` | 19 MB | **单体** texinfo 源，整篇没有一条 `@include`；首行 `\input texinfo` |
| `python.info` | 22.9 MB | 同一内容的 Info 版（`makeinfo` 产物） |
| `python-figures/` | 19 张 | 17 个 PNG + 2 个 **SVG**（`datetime-inheritance.svg`、`lifecycle.dot.svg`） |
| `Makefile` | 1.4 KB | Sphinx 为 texinfo 目录生成的 Makefile |

### 1.2 `Makefile` 到底在干什么

```make
MAKEINFO          = makeinfo --no-split
MAKEINFO_html     = makeinfo --no-split --html
MAKEINFO_plaintext= makeinfo --no-split --plaintext
TEXI2PDF          = texi2pdf --batch --expand
ALLDOCS           = $(basename $(wildcard *.texi))     # → python

all: info
info / plaintext / html / pdf / install-info / uninstall-info / clean

%.pdf: %.texi
	-$(TEXI2PDF) '$<'      # ← 连着跑三遍，`-` 表示忽略单次报错
	-$(TEXI2PDF) '$<'
	-$(TEXI2PDF) '$<'
```

三个要点：

1. **`pdf` 目标连跑 3 遍 `texi2pdf`** —— 因为目录、交叉引用（"见第 N 页"）、索引都要迭代收敛，一遍不够。
2. 每行前面的 `-` 是 make 的"忽略错误"语法，所以**中途报错也会继续**，最后你看目录里有没有 `.pdf` 才算数。
3. `texi2pdf` 自己不带引擎，它会去找系统中的 `tex`/`pdftex`；找不到就报
   `You don't have a working TeX binary (tex) installed anywhere in your PATH`。

---

## 2. 路线 A：Sphinx 构建（与参考文件一致）

### 2.1 依赖清单

| 类别 | 要求 | 本机实测 |
|---|---|---|
| Python | ≥ 3.11 | 3.13.14 ✅ |
| git | 任意近版 | ✅ |
| TeX 发行版 | TeX Live 2025 / MiKTeX，需含 `xelatex`、`latexmk`、`ctex`(或 `xeCJK`)、`makeindex`/`xindy` | TeX Live 2025（`F:\texlive\2025`）✅ |
| 中文字体 | Windows 自带宋体/黑体即可；Linux 需 Noto CJK / 思源 | ✅ |
| 网络 | `pip` 装 Sphinx、`python-docs-theme` 等 | ✅ |

### 2.2 取两份源码（这一步最容易被忽略）

> devguide「How do I build a docs translation?」明确要求：**需要同时有 CPython 仓库和翻译仓库**，
> 并把 PO 文件放进 `Doc/locales/LANG/LC_MESSAGES/`。

`python-docs-zh-cn` 是**纯翻译仓库**（只有 `.po`，根目录 9 个 + `library/` 326 个 + 各子目录），
**单独 clone 它构建不了**，必须配 CPython 的 `Doc/`。

```bash
# 1) CPython 源码（只取 Doc 和 Misc/NEWS.d，省流量）
git clone --depth 1 --branch 3.14 --filter=blob:none --sparse https://github.com/python/cpython.git
cd cpython
git sparse-checkout set Doc Misc/NEWS.d

# 2) 中文翻译仓库
cd ..
git clone --depth 1 --branch 3.14 https://github.com/python/python-docs-zh-cn.git zh-cn

# 3) 把 PO 按原目录结构拷进 locales（LANG=zh_CN）
cd cpython/Doc
mkdir -p locales/zh_CN/LC_MESSAGES
cp -r --parents ../../zh-cn/*.po locales/zh_CN/LC_MESSAGES/ 2>/dev/null || true
# 更稳妥的写法（保持子目录层级）：
cd ../../zh-cn
find . -name '*.po' -exec sh -c 'mkdir -p "../cpython/Doc/locales/zh_CN/LC_MESSAGES/$(dirname "{}")" && cp "{}" "../cpython/Doc/locales/zh_CN/LC_MESSAGES/{}"' \;
```

**`Misc/NEWS.d` 不能省**：`Doc/Makefile` 的 `build` 目标会检查 `../Misc/NEWS` 或 `../Misc/NEWS.d`，
两者都没有会直接 `exit 1`（报 `Neither Misc/NEWS.d nor Misc/NEWS found; cannot build docs`）。

### 2.3 建虚拟环境 + 装依赖（devguide `#building-the-documentation`）

Unix / macOS：

```bash
cd cpython/Doc
make venv            # 内部 python -m venv venv && pip install -r requirements.txt
```

Windows（**`make.bat` 没有 `venv` 目标**，必须手动建并**激活**）：

```bat
cd cpython\Doc
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade -r requirements.txt
```

> `requirements.txt` 里就是 Sphinx、`blurb`、**`python-docs-theme`**、`sphinxcontrib-svg2pdfconverter` 等。
> 装了 `uv` 的话 `make venv` 会走 uv 分支，更快。

### 2.4 构建 HTML（这里才是 `python-theme` 生效的地方）

```bash
# 方式一：用 make（Unix）
make SPHINXOPTS="-D language=zh_CN" html

# 方式二：直接用 Sphinx（devguide #using-sphinx-build 的写法）
python -m sphinx -b html . build/html -D language=zh_CN
```

- **主题**：`Doc/conf.py` 里 `html_theme = 'python_docs_theme'`、`html_theme_path = ['tools']`，
  这个主题就是 `python-docs-theme` 包提供的，也就是 docs.python.org 的样子。
- **目录**：左侧全局 TOC 由 `toctree` 生成，页内小目录由主题渲染。
- **超链接**：`:ref:`/`:func:`/`:class:` 等 Sphinx 交叉引用自动变成站内链接。
- 构建完打开 `build/html/index.html`；`make check` 可跑 sphinx-lint，`make linkcheck` 可查死链。

> ⚠️ **`python-docs-theme` 只作用于 HTML 构建。** PDF 走 LaTeX，用的是 Sphinx 自己的
> `sphinxmanual`/`sphinxhowto` 文档类和 `sphinx.sty`，与 HTML 主题无关。
> 想要"官方样式"的 PDF，靠的是 `conf.py` 里的 LaTeX 配置，而不是 theme。

### 2.5 生成 LaTeX 源

```bash
make SPHINXOPTS="-D language=zh_CN" latex
# 或
python -m sphinx -b latex . build/latex -D language=zh_CN
```

产物在 `build/latex/`，里面会有**多个 `.tex`**，因为 `Doc/conf.py` 的 `latex_documents` 把文档分成了多册：

```
c-api.tex  extending.tex  faq.tex  howto-*.tex  installing.tex
library.tex  reference.tex  tutorial.tex  using.tex  whatsnew.tex
```

> 参考样张目录里 `01…10` 这一串分册文件，来源就是这里。
> 想改成"一整本"，就精简 `latex_documents`，只保留一个根文档（如 `contents`）。

`conf.py` 里与 PDF 相关的关键配置（3.14 分支实测）：

```python
latex_engine = 'xelatex'                     # ← 无条件写死，因为要排中文
latex_elements = {
    'preamble': r'''
\authoraddress{
  \sphinxstrong{Python Software Foundation}\\
  Email: \sphinxemail{docs@python.org}
}
\let\Verbatim=\OriginalVerbatim
\let\endVerbatim=\endOriginalVerbatim
\setcounter{tocdepth}{2}                     # ← 目录到 subsection（3 级）
''',
    'papersize': 'a4paper',
    'pointsize': '10pt',
    'maxlistdepth': '8',
}
latex_documents = [ ... 'manual'/'howto' ... ]   # 决定分册
latex_appendices = ['glossary', 'about', 'license', 'copyright']
```

### 2.6 编译 PDF（关键一步）

`build/latex/` 里 Sphinx 会生成一个 Makefile，用它驱动 `latexmk`，自动跑够遍数、自动生成目录与索引：

```bash
cd build/latex
make all-pdf          # 内部：latexmk -pdf  → xelatex（因为 latex_engine=xelatex）
```

`build/latex/Makefile` 常用目标：

| 目标 | 作用 |
|---|---|
| `make all-pdf` | 生成**所有** PDF（每个 `latex_documents` 一项一个） |
| `make <名字>.pdf` | 只编一册，如 `make reference.pdf` |
| `make clean` | 清中间文件 |
| `make latexpdf` | ⚠️ **Sphinx 自带 Makefile 才有**；CPython 的 `Doc/Makefile` 和 `build/latex/Makefile` 都**没有**这个目标 |
| 在 `Doc/` 下 `make dist-pdf` | 一条命令编 A4 PDF 并打包成 zip（Unix） |

**中文如果出现缺字/方框/乱码**（自建项目常见，CPython 这套已配好），在 `conf.py` 里补一段
导言区即可：

```python
latex_engine = 'xelatex'
latex_elements = {
    'preamble': r'''
\usepackage{ctex}          # 或者用 xeCJK + 显式指定字体
''',
}
# 若需要打印 URL：latex_show_urls = 'footnote'
```

> 参考样张里 `发行版本 3.14.0rc3`、`十月 01, 2025` 这些中文字就是靠 `xelatex` + CJK 字体排出来的。
> 顺带一提，`conf.py` 的 `smartquotes_excludes` 里显式排除了 `zh_CN`（避免中文被套上英文引号）。

### 2.7 一键脚本

见同目录 `build-sphinx-pdf.sh`（含上面全部步骤，Python 路径、LANG 可改）。

---

## 3. 路线 B：Texinfo 构建（用本目录 `Makefile`）

### 3.1 直接跑

```bash
cd python-3.14-docs-texinfo
make pdf                    # = texi2pdf --batch --expand python.texi ×3
# 没有 make 就手写：
texi2pdf --batch --expand python.texi
texi2pdf --batch --expand python.texi
texi2pdf --batch --expand python.texi
```

前提：`makeinfo`、`texinfo.tex`、TeX 引擎都在 PATH 里。

### 3.2 但**中文**直接跑会全军覆没——必须额外做 3 件事

原因：`python.texi` 头部只有 `@documentencoding UTF-8`，**没有 `@documentlanguage zh`**；
TeX 默认按英文处理，所有汉字都会以 `Missing character` 静默丢掉；而默认的 `texi2pdf`
用的是 **pdfTeX**，pdfTeX 根本排不了 UTF-8 中文。

| # | 改动 | 为什么 |
|---|---|---|
| 1 | 第 1 行 `\input texinfo` → `\input texinfo-zh` | `texinfo-zh.tex` 会先载入 `zhspacing.sty`（中英混排间距），再载入 `texinfo.tex` |
| 2 | 在 `@documentencoding UTF-8` 后插入 `@documentlanguage zh` | 让 texinfo 去读 `txi-zh.tex`（中文标题词、日期格式、中文字体定义） |
| 3 | 用 **XeTeX** 引擎（`xetex`，不是 `xelatex`） | 只有 XeTeX 能载 UTF-8 中文字体；`texinfo-zh.tex` 里也写死了 "The TeX engine is not XeTeX" |

外加**字体**：TeX Live 自带的 `txi-zh.tex` 默认要两套字体 ——
`NotoSerifCJK-Regular.ttc`（思源宋体）和 `ukai.ttc`（AR PL 楷体）。
没装就替换成系统字体（本仓库已给出补丁版）。

### 3.3 实测可用的完整命令

```bash
# 0) 环境（本机实测路径，按需改）
export PATH="/f/texlive/2025/bin/windows:$PATH"     # 让 texi2pdf 找得到 tex
export TEXINPUTS="C:/pypdfbuild/texmf;"             # 让 TeX 优先找到补丁版 txi-zh.tex

# 1) 生成改造版 texi：换入口 + 加语言
sed -e '1s|\\input texinfo|\\input texinfo-zh|' \
    -e '4a @documentlanguage zh' \
    python.texi > python-zh.texi

# 2) SVG 插图转成 PDF（XeTeX 不支持 SVG，见 3.4）
python tools/svg2pdf.py python-figures

# 3) 编译三遍（目录/交叉引用/索引需要迭代）
xetex -interaction=nonstopmode python-zh.texi
xetex -interaction=nonstopmode python-zh.texi
rm -f python-zh.pdf     # ← 若上一遍的 PDF 被占用，先删掉，否则会 Unable to open
xetex -interaction=nonstopmode python-zh.texi
```

补丁版 `txi-zh.tex` 只改了两处字体名（你装好思源宋体+AR PL 楷体的话就不需要它）：

```bash
sed -e 's/NotoSerifCJK-Regular\.ttc:2/simsun.ttc:0/g' \
    -e 's/ukai\.ttc/simkai.ttf/g' \
    /path/to/texlive/2025/texmf-dist/tex/texinfo/txi-zh.tex > pdf-build/texmf/txi-zh.tex
```

### 3.4 SVG 插图必须转换

`python-figures/` 里有 2 个 SVG（`datetime-inheritance.svg`、`lifecycle.dot.svg`），
但 `python.texi` 里引用的是**无扩展名**的基名：

```
@image{python-figures/datetime-inheritance,,,……,svg}
@image{python-figures/lifecycle.dot,,,……,svg}
```

texinfo 的 XeTeX 图片加载器只认 `pdf/png/jpg/jpeg`，所以会报
`Could not find image file ... for XeTeX`。解决：**生成同名 `.pdf` 或 `.png`**，
文件名必须是 `datetime-inheritance.pdf` 和 `lifecycle.dot.pdf`（注意 `lifecycle.dot` 那个点号要保留）。
本仓库的 `pdf-build/tools/svg2pdf.py` 用了 `svglib` + `reportlab`：

```bash
pip install svglib
python pdf-build/tools/svg2pdf.py python-figures
# OK    datetime-inheritance.svg -> datetime-inheritance.pdf  (386x188pt)
# OK    lifecycle.dot.svg -> lifecycle.dot.pdf  (465x845pt)
```

### 3.5 本机实测结果

| 项目 | 结果 |
|---|---|
| 工具链 | TeX Live 2025 + GNU Texinfo 7.2 + XeTeX 0.999997 |
| 单遍耗时 | 约 **47 秒** |
| 遍数 | 3 遍（合计 ~2.5 分钟） |
| 产物 | `python-zh.pdf`，**6065 页**，约 **45 MB** |
| 剩余告警 | 13 处 `You can't use @unskip in vertical mode`（Sphinx 输出的 `@*` 紧跟标题导致），**无害** |
| 图片/字体错误 | 0（转完 SVG、补完字体后） |

### 3.6 路线 B 的局限

能出 PDF，但**做不到**参考样张的样子：封面是 Texinfo 的朴素标题页、没有分册、
公式/代码/表头样式都不一样。要"和参考文件格式一致"，只能走路线 A。

---

## 4. 目录与超链接：怎么保证"都有"

这是最容易出问题的地方，分格式说清楚。

### 4.1 HTML（`python-docs-theme`）

| 需求 | 靠什么 | 检查点 |
|---|---|---|
| 全局目录 | 各 `index.rst` 里的 `.. toctree::` + 主题侧边栏 | 随便打开一页，左侧栏应有完整层级 |
| 页内目录 | 主题对标题的自动渲染 / `.. contents::` | 长页面顶部应有本页目录 |
| 站内超链接 | Sphinx 交叉引用（`:ref:`、`:func:`、`:class:`、`:term:`） | 点击应跳到目标锚点 |
| 外链 | `[文字](url)` | 直接用浏览器验证 |
| 死链检查 | `make linkcheck` | 输出 `build/linkcheck/output.txt` |

主题配置在 `conf.py`：

```python
html_theme = 'python_docs_theme'
html_theme_path = ['tools']
html_theme_options = {
    'collapsiblesidebar': True,
    'issues_url': '/bugs.html',
    'license_url': '/license.html',
    'root_include_title': False,
}
```

### 4.2 PDF（LaTeX）

| 需求 | 靠什么 | 检查点 |
|---|---|---|
| **目录（正文前 TOC）** | `\tableofcontents`（Sphinx 自动插入） | 翻开前几页应有"Contents/目录"并带点线+页码 |
| 目录深度 | `latex_elements['preamble']` 里的 `\setcounter{tocdepth}{2}` | 想更深设成 3 |
| **PDF 书签（导航窗格）** | `hyperref` 自动从 `\section` 生成 outline | 用 Adobe/Edge 打开看左侧书签树；缺书签多半是 hyperref 被覆盖 |
| **内部超链接** | `hyperref` + Sphinx 的 `\hyperref[...]` | 点目录、点"见 xxx"应能跳页 |
| 外链 | `latex_show_urls`（`'footnote'`/`'inline'`/`'false'`） | 默认不打印 URL，只在脚注/内联显示 |
| 链接不画红框 | `\usepackage[hidelinks]{hyperref}` 或 `latex_elements['hyperref']` | 参考样张用的就是 hidelinks |

**PDF 没有目录/超链接，按这个顺序排查：**

1. **builder 用错了** —— `-b html` 出的东西不会有 PDF 目录；PDF 必须是 `-b latex`。
2. **编译遍数不够** —— LaTeX 要至少 2～3 遍才能把目录和 `\ref` 填上，表现为目录页码全是 `??`。
   用 `build/latex/Makefile` 的 `make all-pdf`（`latexmk` 会自动补遍数）就不会有这个问题。
3. **`tocdepth` 被设成 0** —— `conf.py` 的 `latex_elements['preamble']` 或文档类选项里查一下。
4. **hyperref 被 `latex_elements['preamble']` 覆盖** —— 自己重定义 hyperref 会把 Sphinx 的设置冲掉。
5. **阅读器没显示书签** —— 换个阅读器（Edge/Adobe）再确认，不是所有阅读器默认展开目录面板。

---

## 5. 故障排查表（都是实测踩过的）

| 报错 | 原因 | 解决 |
|---|---|---|
| `You don't have a working TeX binary (tex) installed anywhere in your PATH` | TeX 的 bin 目录没进 PATH | 加上，如 `F:\texlive\2025\bin\windows` |
| `/usr/bin/perl: bad interpreter: No such file or directory` | Git Bash 与 MSYS2 混用，脚本 shebang 解析不了 | 换到 MSYS2 shell，或显式 `perl /path/to/makeinfo ...` |
| `Required CJK package is not found. Used 'texinfo-zh.tex' instead of 'texinfo.tex'` | 走了 `\input texinfo` 而不是 `texinfo-zh` | 第 1 行改成 `\input texinfo-zh` |
| `Font ... not loadable: Metric (TFM) file or installed font not found` | 缺 `NotoSerifCJK-Regular.ttc` / `ukai.ttc` | 装思源宋体+AR PL 楷体，或用补丁版 `txi-zh.tex` 换 SimSun/KaiTi |
| `Could not find image file ... for XeTeX` | SVG 插图 | 转成同名 `.pdf`/`.png`（见 3.4） |
| `You can't use 'unskip' in vertical mode` | Sphinx 输出里 `@*` 紧跟标题 | 无害，忽略 |
| `xdvipdfmx:fatal: Unable to open "xxx.pdf"` | 目标 PDF 被其它程序占用/未释放 | 先删除旧 PDF 再编译 |
| 中文全是方框/消失 | 用了 pdfTeX，或缺 CJK 字体包 | 换 `xetex`/`xelatex`；`latex_elements['preamble']` 加 `\usepackage{ctex}` |
| `Neither Misc/NEWS.d nor Misc/NEWS found; cannot build docs` | 稀疏 clone 时漏了 `Misc/` | `git sparse-checkout set Doc Misc/NEWS.d` |

---

## 6. 本机环境实况（可直接照抄）

```
Python     : 3.13.14（C:\Users\zb137\.workbuddy\binaries\python\versions\3.13.12）
TeX        : TeX Live 2025  →  F:\texlive\2025\bin\windows
             含 xetex / xelatex / latexmk / pdftotext / dvisvgm
             含 texinfo.tex、texinfo-zh.tex、txi-zh.tex、zhspacing.sty、ctex、xeCJK
Texinfo    : GNU Texinfo 7.2（MSYS2 /usr/bin；注意上表中 perl 那个坑）
字体       : 无 NotoSerifCJK / ukai；有 simsun.ttc、simkai.ttf、msyh.ttc、simhei.ttf
中文翻译   : python-docs-zh-cn 3.14 已就位 → python-3.14-docs-texinfo/python-docs-zh-cn-3.14
```

---

## 7. 速查表

```bash
# ── 路线 A：Sphinx（和参考文件一致，分册 PDF） ──────────────────────────
git clone --depth 1 --branch 3.14 --filter=blob:none --sparse https://github.com/python/cpython.git
cd cpython && git sparse-checkout set Doc Misc/NEWS.d
git clone --depth 1 --branch 3.14 https://github.com/python/python-docs-zh-cn.git ../zh-cn
mkdir -p Doc/locales/zh_CN/LC_MESSAGES      # 把 zh-cn 的 *.po 按结构拷进去
make venv                                    # Windows 手动建 venv 并激活
make SPHINXOPTS="-D language=zh_CN" html     # 看：python-theme + 目录 + 超链接
make SPHINXOPTS="-D language=zh_CN" latex    # 出 build/latex/*.tex（多册）
cd build/latex && make all-pdf               # 出分册 PDF（xelatex + latexmk）

# ── 路线 B：Texinfo（用本目录 Makefile，单体 PDF） ─────────────────────
export PATH="/f/texlive/2025/bin/windows:$PATH"
export TEXINPUTS=".../pdf-build/texmf;"
sed -e '1s|\\input texinfo|\\input texinfo-zh|' -e '4a @documentlanguage zh' python.texi > python-zh.texi
python pdf-build/tools/svg2pdf.py python-figures
xetex -interaction=nonstopmode python-zh.texi   # ×3
```
