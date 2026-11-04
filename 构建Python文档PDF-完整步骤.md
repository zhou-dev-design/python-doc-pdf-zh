# 构建 Python 中文文档 PDF 的完整步骤

> 把 **CPython 官方 reST 文档** + **python-docs-zh-cn 中文译文** 编译成**中文分册 PDF**。
>
> 本文讲**手工命令**（想自己跑一遍、或排查 CI 时对照）。
> 日常构建走 GitHub Actions（计划北京 11:47，实测约 19:4x 出稿）或图形界面 ——
> 见 [`README.md`](README.md) 与 [`sphinx-pdf/gui/README.md`](sphinx-pdf/gui/README.md)。

---

## 0. 一句话流程

```
CPython 的 Doc/（reST 源）
        +  python-docs-zh-cn 的 *.po（译文）
        ↓  按 Doc/locales/zh_CN/LC_MESSAGES/<同路径>.po 铺好
   sphinx -b latex -D language=zh_CN
        ↓  build/latex/*.tex（conf.py 的 latex_documents 决定分成几册）
   latexmk -pdf（xelatex）
        ↓  每册一个 PDF，再合并成一册
```

**只 clone 翻译仓库是构建不了的**：它只有 `.po`，没有文档正文。
两边必须配套，分支号要一致（3.14 的 `Doc` 配 3.14 的 `.po`）。

---

## 1. 依赖

| 类别 | 要求 |
|-|-|
| Python | ≥ 3.11（Sphinx 用哪个版本编都行，但要能建 venv） |
| git | 要克隆两个仓库 |
| TeX 发行版 | 需含 `xelatex`、`latexmk`、`makeindex`、`pdfinfo`/`pdffonts`；**TeX Live 2022 以上** |
| 中文字体 | Windows 自带宋体/黑体即可；Linux 需 Noto CJK 或思源 |
| 网络 | 装 Sphinx、`python-docs-theme`，以及克隆仓库 |

TeX Live 必须能让 `latexmk` 找到，Windows 上建议把它的 bin 目录加进 PATH，
或在程序里直接填 bin 目录的绝对路径。

---

## 2. 取两份源码

```bash
# 1) CPython（稀疏克隆，只拿 Doc 和 Doc 引用的那几处）
git clone --depth 1 --branch 3.14 --filter=blob:none --sparse \
  https://github.com/python/cpython.git
cd cpython
git sparse-checkout set Doc Misc/NEWS.d Include Grammar Parser Lib/profiling/sampling

# 2) 中文译文
cd ..
git clone --depth 1 --branch 3.14 \
  https://github.com/python/python-docs-zh-cn.git zh-cn
```

稀疏检出的那几个路径**一个都不能少**，缺了会静默出问题：

| 路径 | 缺了会怎样 |
|-|-|
| `Misc/NEWS.d` | `Doc/Makefile` 直接 `exit 1`（`Neither Misc/NEWS.d nor Misc/NEWS found`） |
| `Include` | Sphinx 第一秒就崩（`patchlevel.h` 找不到） |
| `Grammar` | 《语言参考手册》第 10 章「完整的语法规范」**整章空白**，零报错 |
| `Parser` | `library/ast` 里的 `literalinclude` 取不到，内容静默缺失 |
| `Lib/profiling/sampling` | 3.15 起 `whatsnew` 引用了它下面的 PNG，缺了图片 → latexmk 退出码 12 |

目录型（`Grammar`）用 `sparse-checkout add` 追加即可；**大目录里的单个文件**
（如 `Lib/test/exception_hierarchy.txt`、`Modules/expat/COPYING`）cone 模式取不到，
要用 `git show HEAD:<路径>` 单独拉那一个 blob。

---

## 3. 铺译文

`.po` 必须**按源文件的相对路径**铺到 `Doc/locales/zh_CN/LC_MESSAGES/` 下：

```
Doc/locales/zh_CN/LC_MESSAGES/library/array.po   ← 对应 Doc/library/array.rst
Doc/locales/zh_CN/LC_MESSAGES/tutorial/index.po  ← 对应 Doc/tutorial/index.rst
```

```bash
cd zh-cn
find . -name '*.po' -exec sh -c '
  d="../cpython/Doc/locales/zh_CN/LC_MESSAGES/$(dirname "{}")"
  mkdir -p "$d" && cp "{}" "$d"' \;
```

> ⚠️ 别用 `cp "$ZH"/library/*.po …` 这种 glob —— 目录多了会静默漏掉一部分，
> 表现是「少部分页面是英文」，而且没有任何报错。

---

## 4. venv + 依赖（**版本差异最大的一步**）

```bash
cd cpython/Doc
python -m venv venv
# Windows: venv\Scripts\activate  /  Unix: source venv/bin/activate
```

装什么**取决于版本**：

| 版本 | 依赖来源 | 说明 |
|-|-|-|
| **3.10 / 3.11 / 3.12** | 用该分支自己的 `Doc/requirements.txt`（含 `-c constraints.txt`） | 官方 pin 得很死：3.10 = `sphinx==3.4.3`、3.11 = `~=7.2`、3.12 = `~=8.2` |
| 3.13 及以上 | 内置清单 `sphinx<9` + `python-docs-theme` + `pypdf` + `sphinxcontrib-svg2pdfconverter[CairoSVG]` | |

**不要对所有版本一刀切装最新 Sphinx**：拿 Sphinx 8 去编 3.10 的 `Doc/tools/extensions/*.py`
必然报错（那是五年前的代码）。反过来，老版本的 `python-docs-theme` 也要用分支自己 pin 的
（最新主题要求 `sphinx>=7.3`，老 Sphinx 装不上）。

---

## 5. 构建 LaTeX 源

```bash
python -m sphinx -b latex . build/latex -D language=zh_CN
```

产物 `build/latex/*.tex` 是**多册**——分几册由 `conf.py` 的 `latex_documents` 决定，
各版本册数不同（见 §7）。

### 构建前的三个必查项

**① `gettext_compact = False`**

Sphinx 这个选项默认是 `True`，含义是「同一顶层目录共用一份 `.mo`」：`library/*` 全去找
`locales/zh_CN/LC_MESSAGES/library.mo`。而译文是**每页一个** `.po`（`library/array.po`），
按默认规则**一个都匹配不上** → **整册英文，零 warning**。

- 3.12 起 `conf.py` 自带这行（注释写着 `Split pot files one per reST file`）
- **3.10 / 3.11 没有** → 必须手工追加 `gettext_compact = False`

**② SVG 转换器**

3.13 起 Doc 里有 SVG 插图，`conf.py` 才注册 `sphinxcontrib.rsvgconverter`。
它要调外部程序 `rsvg-convert`（Windows 上没有），所以换成 `cairosvgconverter`：

```python
# 仅当 conf.py 里出现 sphinxcontrib.rsvgconverter 时
'sphinxcontrib.rsvgconverter' → 'sphinxcontrib.cairosvgconverter'
```

3.10~3.12 的 Doc **压根没有 SVG**，也没有这个扩展 —— 不要以为「没找到就是失败」。

**③ Sphinx 3.x 的 `.mo` 陷阱**

Sphinx 主版本 < 4 时，它把编译好的 `.mo` 写进 **输出目录**（`build/latex/locales/…`），
而读翻译是从**源码目录** `Doc/locales/` 找；加上「先加载翻译、后编译 .po」的顺序，
第一次构建永远读不到译文。解法：构建前用 babel 把 `.po` 预编译到源目录旁
（`pybabel compile -D <域> -d Doc/locales/zh_CN/LC_MESSAGES`）。

---

## 6. 编译 PDF

```bash
cd build/latex
latexmk -pdf -gg -file-line-error -r latexmkrc *.tex
```

Sphinx 生成的 `build/latex/Makefile` 里 `all-pdf` 目标也是跑 latexmk，等价。

**索引必须接管 `$makeindex`**，否则目录空白、满屏 `??`、索引页码点不动：

```bash
latexmk -pdf -gg -file-line-error -r latexmkrc \
  -e '$makeindex = q{python makeindex-fix.py %O -s python.ist -o %D %S};' *.tex
```

`makeindex-fix.py` 是我们自己的包装：先跑真的 `makeindex`，再就地修 `.ind`
（分组标题、`\hyperpage`、长条目断点）。latexmk 的次序是
`xelatex → makeindex → xelatex → xelatex`，所以第 2 遍就读到修好的 `.ind`。

> ⚠️ `latexmk -e` 的命令里**只能出现 ASCII**：它按 UTF-8 解析 `-e`，
> 路径带中文会报 `Malformed UTF-8 character (fatal)`。所以先把脚本拷到
> latex 目录并改成纯 ASCII 名（`makeindex-fix.py`），再用 PATH 里的 `python` 启动。

> ⚠️ 在 Windows 上跑 `latexmk` 前要清掉 `LC_ALL` / `LANG` / `LC_CTYPE`：
> TeX Live 自带的 perl 一看到非 C 的 locale，就按那个编码处理文件名，
> 而 Windows 文件 API 走 ANSI 代码页 → **凡是路径带中文的都打不开**。

---

## 7. 各版本的「天花板」（一换版本就中招）

上游每换一代工具链，就多一条写死的地方。凡是「某文件里必须有某字符串」的判据，
都要先问一句：**这是所有版本都有，还是某一版才引入的？**

| 写死的东西 | 后果 | 正确判据 |
|-|-|-|
| 依赖一刀切装最新 | 3.10 装上 Sphinx 8.1.3（官方 pin 的是 3.4.3） | ≤3.12 用分支自己的 `requirements.txt` |
| 「`conf.py` 里必须有 `rsvgconverter`」 | 该扩展 3.13 才引入，3.10~3.12 被误判为失败 | 看「Doc 里有没有 `.svg`」 |
| 主题不管版本 | 最新主题要 `sphinx>=7.3`，老 Sphinx 装不上 | 老版本用分支 pin 的主题 |
| 「`conf.py` 里必须有 `gettext_compact`」 | 3.10/3.11 没有 → 整册英文、零 warning | 没有就追加 `gettext_compact = False` |
| 硬编册数 / 册名 | 各版本册数不同：**3.11=29 / 3.12=32 / 3.13=37 / 3.14=38 / 3.15=39** | 从 `volumes.json` 读，`--tool volumes --verify` 联网核对 |

册数差异的根源是上游随版本增删 howto：
`0925 远程调试附加协议`（PEP 768）是 **3.14** 才有、`0929 迁移到自由线程的稳定 ABI`
是 **3.15** 才有 —— 3.13 里这两册不存在，编号 `0925` 就是**空号**（不是缺册）。

---

## 8. 故障排查

| 报错 / 现象 | 原因 | 解决 |
|-|-|-|
| `Neither Misc/NEWS.d nor Misc/NEWS found` | 稀疏克隆漏了 `Misc/` | `git sparse-checkout set … Misc/NEWS.d` |
| `FileNotFoundError: Include/patchlevel.h` | 漏了 `Include` | 同上，删 `cpython` 重跑步骤 1 |
| 目录空白、满屏 `??`，或 latexmk **退出码 12** | `$makeindex` 没接管 | 用 §6 的 `-e` 写法 |
| latexmk 报 `Missing character: There is no 安 (U+5B89)` | 语言不是 CJK，Sphinx 没加载 `xeCJK` | 加 `-D language=zh_CN` |
| **整册正文英文，但 `.po` 装够了、日志全绿** | 缺 `gettext_compact = False`（3.10/3.11）、或译文路径与源文件对不上 | 见 §5① |
| **某一章的 PDF 书签是英文**，其它章正常 | 原文改了一个字母的大小写，`msgid` 精确匹配失败 | 用 `--tool alias-po` 的漂移修补 |
| **整章内容消失，构建全绿零报错** | `literalinclude` 目标在 `Doc/` 之外而稀疏克隆没取到 | 补齐路径（§2），**从步骤 6 重跑** |
| 个别册 latexmk 退出码 12，`.log` 里无 LaTeX 错误，只有 `fwrite: Broken pipe` | 偶发（管道写失败），与内容无关 | 单独重编该册即可 |
| `Latexmk: I cannot read the rc-file` / `Cannot write file 'xxx.aux'` | perl 的 locale 问题（见 §6） | `unset LC_ALL LANG LC_CTYPE` |
| `RPC failed; curl 56` / `fatal: early EOF` | 代理断流 | 重跑（对象库已在，不会从零开始） |
| 索引页码点不动 / 双栏叠字 | `.ind` 没修 | 跑 `--tool fix-index <latex目录>`；`--check` 只检不写 |
| 想确认「某章真的在 PDF 里」 | 这类 PDF 是字体子集 + 自定义编码，`extract_text()` **取不到文字** | 用书签定位页号，再看该页内容流字节数（正常 ≈20000，空白 <1000） |

---

## 9. 别自己重写这些步骤

上面每一步在这个仓库里都已经实现好了，手工版只是用来对照：

| 场景 | 用什么 |
|-|-|
| 每天自动构建、发布到 Releases | `.github/workflows/build-pdf-linux.yml`（CI） |
| 本机图形界面，可多版本并行 | `sphinx-pdf/gui/pdf_builder_multi.py` |
| 纯 bash 一键 | `sphinx-pdf/build-sphinx-pdf.sh` |
| CI 同款脚本（Linux） | `ci/linux/pdf_builder_linux.py` |
| 只想跑某一步 / 某个工具 | `python sphinx-pdf/gui/pdf_builder_multi.py --tool <名字>` |

分册名、编号、书签标题、版本区间、合并顺序的真源是
**`sphinx-pdf/volumes.json`**（界面里「分册配置…」可视化编辑），
改完 `--tool name-map --check` 自检。
