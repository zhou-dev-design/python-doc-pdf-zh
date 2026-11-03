# Python 中文文档分册 PDF 构建器（PyQt6 图形界面）

把 **CPython 官方 reST 文档** + **python-docs-zh-cn 中文译文** 编译成中文分册 PDF。

本程序是仓库里**唯一**的实现：图形界面、命令行（`--cli`）、内置工具（`--tool`）
走的是同一套代码，没有第二份需要手工同步。

| | |
|-|-|
| 支持版本 | **3.11 / 3.12 / 3.13 / 3.14 / 3.15**（册数 29 / 32 / 37 / 38 / 39，各不相同） |
| 产物 | 分册 PDF + 合并册（带完整书签树）+ `验收报告.md` |
| 排版 | A4、Fandol 字体、目录带点线页码、索引可点、无非法 UTF-8 |

![界面预览](界面预览.png)

> 截图为早期版本，左侧配置面板后来精简成 **5 个可折叠区块**（见 §三），未重拍。

---

## 一、怎么启动

| 方式 | 命令 |
|-|-|
| Windows 双击 | `启动PDF构建器.bat`（首次会自动建隔离 venv 并装 PyQt6 + pypdf） |
| Git Bash / Linux / macOS | `bash 启动PDF构建器.sh` |
| 直接跑 | `python pdf_builder_multi.py` |
| 命令行（不开界面） | `python pdf_builder_multi.py --cli`（**不需要 PyQt6**，只要 pypdf） |
| 单个内置工具 | `python pdf_builder_multi.py --tool <名字> [参数…]` |

`--cli` / `--check` / `--tool` 都是无头路径，与 Qt 无关，没装 PyQt6 也能跑。

```bash
python pdf_builder_multi.py --check                  # 步骤 0 的工具链自检 + 打印解析后的配置
python pdf_builder_multi.py --cli --version 3.13     # 全流程（两个仓库都切到 3.13 分支）
python pdf_builder_multi.py --cli --from 7           # 从第 7 行（= 步骤 6b）接着跑
python pdf_builder_multi.py --cli --only 7,8,9       # 只跑 封面中文化 / 编译 / 索引自检
python pdf_builder_multi.py --cli --merge            # 步骤 9：合并成一册
python pdf_builder_multi.py --cli --only 12 --clean all   # 步骤 10：清理（none/build/all）
python pdf_builder_multi.py --cli --verbose          # 显示 LaTeX 的每一行输出
python pdf_builder_multi.py --config my.json         # 用另一份配置
```

**默认配置直接可用**：版本默认 3.14，源码与译文默认从网站实时克隆/更新，
语言默认 `zh_CN`，构建根目录按版本自动推算。想离线就把「② 下载源 → 本地翻译源目录」
填上（同时确保 `<构建根>/cpython` 已存在），此时不再联网。

---

## 二、内置工具（17 个）

```bash
python pdf_builder_multi.py --tool                  # 列出全部
python pdf_builder_multi.py --tool name-map --check # 参数就是该工具自己的
```

| 工具 | 干什么 |
|-|-|
| `name-map` | 分册映射自检（编号撞车 / 重名 / slug 拼错 / 版本区间悬空）；`--dump` 导出 `volumes.json` |
| `volumes` | 各版本册数；`--verify` 联网对着官方 `Doc/conf.py` + `Doc/howto` 逐条核对 |
| `titles` | 完整版本号口径（官方文档站 h1）；`--write` 更新 `version-titles.json` |
| `check-doc-refs` | 查「Doc 引用了 Doc/ 之外的文件」缺哪些，`MISSINGKIND` 问 git 得类型 |
| `alias-po` | 接回「上游搬了目录」的译文 + 大小写漂移 + 补「上游没译」的页 |
| `localize-titles` | 把封面/页眉的英文标题换成中文（步骤 6b） |
| `fix-index` | 就地修 `.ind`（非字母在前 / 页码可点 / 断行 / 非法字节）；`--check` 只检不写 |
| `emit-makeindex-fix` | 往 latex 目录释放 `makeindex-fix.py`（给 latexmk 的 `$makeindex`） |
| `rename-pdf` | 英文名 → 中文分册名；末几行给程序看的 ASCII 标记 |
| `merge-pdf` | 合并成一册（完整书签树 + 书内跳转重映射） |
| `report` | 生成 `验收报告.md` |
| `check-pdf-gaps` | 靠「页面内容流字节数」抓 PDF 里静默缺失的章节 |
| `fix-md-escapes` | 修 Markdown 转义 |
| `verify-pdf` | 逐册打印 页数 / 书签 / 前 40 页链接数 |
| `extra-dump` / `extra-fetch` | 导出 / 更新「补充译文」（上游根本没译的那几页） |
| `emit-shims` | 重新生成 `tools/*.py` 转发器（该目录已删，一般不用） |

**补充译文**内嵌在程序里：步骤 3 每次把结果整份重写到 `<构建根>/i18n-extra/`，
再铺进 locale（只补缺口）。配「补充译文地址」就能每次取最新版：

- `http(s)://…/manifest.json` → 清单 `{"builtins/index.po": "<文本>", …}`
- `http(s)://…/dir` → 目录前缀，按内置那份的相对路径逐个 GET
- `file://…` 或**本机目录路径** → 直接读同名文件（没有服务器时用它）

**留空 = 只用内置那份，断网也能跑**；取不到只警告，不影响构建。

---

## 三、界面

### 左侧：5 个可折叠区块（默认只展开 ① 和 ④）

| 区块 | 内容 |
|-|-|
| **① 版本与目录** | Python 版本（可多选，每版一行解释器）、基准目录、构建根目录、PDF 输出目录 |
| **② 下载源** | 是否实时下载/更新、GitHub 代理前缀、两个仓库地址、本地翻译源、分支覆盖、pip 源、补充译文地址 |
| **③ 本地环境** | TeX Live bin、构建 venv（通常自动探测，不用改） |
| **④ 运行参数** | 语言（默认 `中文 zh_CN`）、sphinx 并行度、**起始步骤**、**只跑这些步**（填行号如 `7,8,9`） |
| **⑤ 执行开关** | 跳过已有克隆、依赖就绪跳过 pip、保留 `build/`、构建 HTML、封面中文化、索引自检、生成报告、**步骤 9 合并**、显示完整输出、完成后打开目录；另有合并册名与清理范围 |

- **解释器是每个版本一份**（① 那几行），没有全局「Python 解释器」字段。
  3.11 / 3.12 的路径要自己填（内置默认表只有 3.13 / 3.14 / 3.15）。
- 勾 **2 个及以上**版本时，「构建根目录 / PDF 输出目录 / 合并册名」自动置灰 ——
  每版各用各自的文件夹 + 各自的合并册名（`Python <完整版本> 文档 <日期>.pdf`）。
- **日期标签**写进文件夹名与合并册名，默认今天。续跑同一轮时**保持不变**；
  改了日期等于换文件夹，会重新克隆源码、重装依赖。
- 右下三个按钮：**保存配置** / **恢复默认** / **校验路径**（不跑构建，只逐项检查
  解释器、TeX Live、翻译源、venv、内置工具与补充译文在不在）。

### 右侧：进度

- **步骤表**：13 行，逐行显示 `状态 / 用时 / 摘要`；摘要列在编译阶段会实时变成
  `29/38 · library` 这种。
- **运行日志**：按级别着色。默认只显示关键行（LaTeX 输出动辄几万行）；
  勾「显示完整输出」才全打出来。**无论哪种模式，完整输出都写进
  `<构建根>/gui-build.log` 与各分节日志**（`html-build.log`、`latex-build.log`、
  `pdf-build.log`、`index-fix.log` …）。
- **按钮**：开始处理 / 停止（连子进程一起杀）/ 打开输出目录 / 打开完整日志。

### 多版本并行

勾 ≥2 个版本时，每版各起一个子进程（`本程序 --cli --json-log --config <临时配置>`），
venv、PATH、LC_ALL、工作目录天然隔离；一个版本一个独立日志面板，并排显示。

子进程的每条日志是一行 JSON，父进程按级别上色、按事件画进度 ——
**不解析彩色文本**：`==> 步骤 7` 这类文本在中文 + GBK + ANSI 夹击下极脆
（实测 `↳` 在 GBK 控制台里能把整个步骤崩成退出码 127）。

---

## 四、步骤对照表

程序里的每一步都对应 bash 脚本的一步，编号沿用脚本写法（行号 ≠ 步骤号）：

| 行号 | 脚本步骤 | 内容 | 要命的坑 |
|-:|-|-|-|
| 0 | `0/10` | 前置检查 git / Python / xelatex / latexmk / **makeindex / python** | 步骤 7 的索引修复要靠 `python`，这里也要查 |
| 1 | `1/10` | 稀疏克隆 `Doc` + `Misc/NEWS.d` + `Include` + …；已有克隆则 fetch | Include 漏了 Sphinx 第一秒就崩 |
| 2 | `2/10` | 准备中文翻译 `.po`（默认联网克隆对应分支） | 关掉联网又没填本地源 → 直接报错 |
| 3 | `3/10` | 把 `.po` 按目录层级铺进 `Doc/locales/zh_CN/LC_MESSAGES`，并跑 `alias-po` | 不能写 `cp "$ZH"/library/*.po`（glob 会静默失败）；路径对不上时**整册英文且零报错** |
| 4 | `4/10` | venv + 依赖；**≤3.12 用该分支自己的 `Doc/requirements.txt`** | 一刀切 `sphinx<9` 会让 3.10 装上 8.1.3（官方 pin 的是 3.4.3） |
| 5 | `5/10` | 构建 HTML（验证主题/目录树/站内链接） | 别用 `make latex`（带 `--fail-on-warning`）；PDF 不依赖这步，关掉省 ~11 分钟 |
| 6 | `6/10` | `sphinx -b latex`；按需补 SVG 转换器与 `gettext_compact` | 见「版本天花板」一节 |
| 7 | `6b/10` | 封面标题中文化（`localize-titles`） | `--only 6b` 才跑；写 `--only 7` 其实是这一步 |
| 8 | `7/10` | **并发**逐册 `latexmk`，`-e` 把 `$makeindex` 换成 `python makeindex-fix.py`；失败册自动串行重试 2 轮 | 别用 `make -j`（MSYS fork 崩）；不覆盖 `$makeindex` 会退出码 12、目录空白满屏 `??` |
| 9 | `7b/10` | **索引自检**：核对分组标题 + 页码超链接 + 断点 | 异常才重排；重排**绝不能再跑 makeindex**；xelatex 必须走绝对路径 |
| 10 | `8/10` | 收集 → 验收（页数/纸型/字体）→ 中文名重命名 → 验收报告 | 名字没登记的册会静默留下且不进合并册 |
| 11 | `9/10` | **合并成一册**（`merge-pdf`）：一级书签 = 有独立 PDF 的册子，顺序由 `volumes.json` 的 `merge_order` 定 | 册内跳转必须自己重映射（各册锚点重名，pypdf 自带配对会全指到第 1 册） |
| 12 | `10/10` | 清理过程文件（只删中间件 / 全删） | 有安全闸：要删的路径含成品 PDF 目录就直接拒绝；**成品永远不删** |

步骤 3 会清空 `Doc/locales` 重铺，步骤 4 默认清空 `Doc/build`（想增量就勾「保留已有 build/」）。

---

## 五、索引（关键判据）

索引有三个必须满足的特征：**非字母条目排最前**（带「非字母」「数字」分组标题）、
**每个页码都能点**、**长条目不压到隔壁栏**。`makeindex` 天然做不到，程序在
`fix-index` 段里就地修 `.ind`：

| 毛病 | 根因 | 修法 |
|-|-|-|
| 分组标题显示成 `□` | `makeindex` 按**字节**处理，中文组标题只写了 UTF-8 首字节 → 非法字节 | 删掉这类坏标题，中文条目本身已按码位排序 |
| 「非字母」「数字」标题是空的 | Sphinx 的 `python.ist` 写的是宏 `\sphinxsymbolsname`，而样式文件里该宏初始值为空 | 把宏名换成字面文字 |
| 页码点不动 | `sphinxlatexindbibtoc.sty` 里的 `\RequirePackage{makeidx}` 把 `\@wrindex` 覆盖掉，`\|hyperpage` 被剥 | 给每条页码包一层 `\hyperpage{…}` |
| **只有一部分**页码点不动 | `python.ist` 的 `line_max 100` 会把超长条目的页码**折到下一行**，而修法是逐行处理「行尾页码段」的 | 先把「纯页码续行」并回逻辑行再包链接（中文 3 字节/字，越长的条目越容易折行） |
| 双栏叠字 | `\spxentry` 用 `\texttt{}` 关掉了断词，长模块路径在窄栏里溢出 | 在 `.` `_` `/` `-` 与驼峰边界补 `\allowbreak{}`（`{}` 不能省，否则紧跟字母会被吞成未定义控制序列） |

**怎么接进流程**：步骤 8 把 `latexmk` 的 `$makeindex` 换成 `python makeindex-fix.py`
（参数与 makeindex 一致）。latexmk 的次序是 `xelatex → makeindex → xelatex → xelatex`，
所以第 2 遍直接读到修好的 `.ind`，**一遍编译同时拿到分组标题和可点页码**。

> ⚠️ `latexmk -e` 的命令里只能出现 ASCII：它按 UTF-8 解析 `-e`，路径带中文会报
> `Malformed UTF-8 character (fatal)`。所以程序先把脚本拷到 latex 目录改名
> `makeindex-fix.py`（纯 ASCII），再用 PATH 里的 `python` 启动。

> ⚠️ 重排（步骤 9）必须用**配置里那个 TeX Live** 的 xelatex 绝对路径，不能靠 PATH：
> Windows 的 `CreateProcess` 用父进程的 PATH，`subprocess(env=…)` 只对环境里的孙进程生效。
> 命中另一个 TeX 发行版（如 TinyTeX，没有 `cmap.sty`）时会 `No pages of output`，
> 而**上一遍的旧 PDF 还在**，于是白跑也报成功。判据必须是「退出码 + PDF mtime 真的变了 + 非法字节数」。

---

## 六、耗时预算（参考值）

以 3.14（38 册）为例（实测值）：

| 步骤 | 实测 | 说明 |
|-|-|-|
| 0 前置检查 | <1s | |
| 1 稀疏克隆 CPython | 37s | 走代理时；已有克隆只 fetch 几秒 |
| 2 准备中文翻译 | <1s ~ 几十秒 | 视网速 |
| 3 铺 locales | 1~2s | |
| 4 venv + 依赖 | 22s | 已勾「依赖就绪就跳过 pip」 |
| **5 构建 HTML** | **≈11~12 分钟** | 全量解析 500+ 篇源文档 |
| **6 构建 LaTeX 源** | **≈10~13 分钟**（重铺 `.po` 后首次 ~18 分钟） | 用另一个 doctree 目录，要再全量解析一遍；`.po` 全量编 catalog 时更慢 |
| 6b 封面中文化 | <1s | |
| **7 编译 PDF** | **≈5~8 分钟**（并发） | 串行要 35~40 分钟；索引修复已并进这步 |
| 7b 索引自检 | <2s | 只读 `.ind` 核对，异常才重排 |
| 8 收集 + 重命名 + 报告 | ≈1 分钟 | 要读 38 个 PDF 的书签与注解 |
| **9 合并成一册** | **≈1.3 分钟** | 主要花在把几万条册内链接重映射到页对象 |
| 10 清理 | 几秒 ~ 1 分钟 | 受磁盘速度影响 |
| **合计**（0→12，含合并） | **≈37~42 分钟** | 关掉步骤 5 省 ~11 分钟 |

省时间三条：**关掉步骤 5**（PDF 不依赖它）；**勾住「依赖就绪跳过 pip」**；
**中途失败别从 0 重来**（把「起始步骤」选到失败那一步）。

> 版本越老越快：3.10 的整轮只要 4 分 20 秒（文档体量小得多）。

---

## 七、常见问题

| 现象 | 原因 / 处理 |
|-|-|
| 找不到 xelatex / latexmk | 「TeX Live bin」填错，要填 **bin 目录本身**，不要再套一层 |
| 找不到构建用的 venv | 跑一遍步骤 4，或在「构建 venv」里指定一个装了 sphinx 的 venv |
| 关掉联网又没填本地翻译源 | 点「开始处理」时会直接拦下 |
| 索引页码点不动 / 没有「非字母」标题 / 双栏叠字 | `$makeindex` 覆盖没生效（`latexmkrc` 被改过）。重跑步骤 8 |
| 目录空白、满屏 `??` | 同上，`$makeindex` 没换 |
| `FileNotFoundError: Include/patchlevel.h` | 稀疏克隆漏了 `Include`，删 `<root>/cpython` 重跑步骤 1 |
| latexmk 退出码 12、个别册不出 PDF、`.log` 里却无 LaTeX 错误，只有 `fwrite: Broken pipe` | **偶发，与内容无关**（管道写失败）。程序已自动串行重试 2 轮；手工兜底 `--books <册名>`。不要因此改 `.rst` |
| `Latexmk: I cannot read the rc-file` / `Cannot write file 'xxx.aux'` / perl 报 `No such file` | **locale 问题**，文件都在。Windows 版 perl 遇到非 C 的 `LC_ALL/LANG/LC_CTYPE` 就打不开中文路径。从 git-bash 启动会带上这些变量，双击启动则没有；程序已在 Windows 上直接清掉它们 |
| `RPC failed; curl 56` / `fatal: early EOF` | GitHub 代理断流，不是配置错。程序会自动重试一次，直接重跑即可 |
| **整章内容消失，但构建全绿零报错** | `literalinclude` 的目标在 `Doc/` 之外而稀疏克隆没取到 —— Sphinx 只留一条 warning 就整段跳过。程序在步骤 1 和 6 之前跑 `check-doc-refs` 并自动补齐（`REFMISSING 0` 才算齐），**必须从步骤 6 重跑** |
| **整册正文英文，`.po` 装够了、日志全绿** | 上游搬了目录 / 改了大小写，译文路径或 msgid 对不上，Sphinx 静默回退。`alias-po` 接回（`ALIASED` / `DRIFTED`），**必须从步骤 6 重跑** |
| 少数页面还是英文 | `.po` 覆盖率不满，正常；看步骤 3 日志的 `.po` 数量 |
| 某个版本册数就是比别的少 | **正常**。上游会随版本增删 howto：`0925 远程调试` 是 3.14 才有、`0929 abi3t` 是 3.15 才有，3.13 里这两个是**空号**（程序叫 `UNPRODUCED`，不算缺册） |
| 目录里留下 `howto-xxx.pdf` 这种英文名 | 该 slug 没在分册表里登记。步骤 8 会报 `UNKNOWN n`；在 `volumes.json`（或界面「分册配置…」）补一行即可 |
| 想查某次构建为什么停的 | 看 `<输出目录>/gui-build.log`：最后一段 `===== 步骤 N =====` 之后就是 `[错误] …`。开头还有「解析后的实际取值」块 |
| 编译日志刷 `Missing character: There is no 安 (U+5B89)` | 语言被改成了非 CJK。改回 `zh_CN` 后重跑 2→3 与 6→8（程序会弹窗拦） |
| 界面日志刷屏卡顿 | 关掉「显示完整输出」，完整日志仍在 `gui-build.log` |
| 清理后 `gui-build.log` 还在 | 日志正被本进程占用，Windows 不允许删打开的文件；关掉程序后手删 |

---

## 八、文件清单

```
sphinx-pdf/
├── build-sphinx-pdf.sh     一键 bash 脚本（步骤 0~10，全部走 --tool）
├── rename-pdf.sh           分册中文名映射（只转调 --tool rename-pdf）
├── volumes.json            分册真源（名称/编号/书签/版本区间/合并顺序）
├── version-titles.json     完整版本号口径（官方文档站标题）
├── 命名.txt                参考样张命名表
└── gui/
    ├── pdf_builder_multi.py  ★★ 唯一实现：流水线 + 17 个内置工具 + PyQt6 界面
    ├── 启动PDF构建器.bat / .sh
    ├── build_exe.py          打包成 exe
    ├── pdf_builder_multi.spec
    ├── 打包exe.bat
    ├── requirements.txt      GUI 依赖（PyQt6 / pypdf）
    ├── config-multi.json     运行时配置（含本机路径，已从 git 移除）
    ├── dist/                 打包产物
    ├── 界面预览.png
    └── README.md             本文件
```

程序会读写的外部路径（都可在界面里改）：

| 路径 | 用途 |
|-|-|
| `<构建根>/cpython/Doc` | CPython 源码与构建目录 |
| `<构建根>/zh-cn` | 联网克隆的译文仓库（用本地源时无此项） |
| `<构建根>/gui-build.log` 等 | 本次运行的完整日志 |
| `<输出目录>/*.pdf` | 各册最终 PDF |
| `<输出目录>/Python <完整版本> 文档 <日期>.pdf` | 合并册 |
| `<输出目录>/验收报告.md` | 逐册页数 / 体积 / 书签 / 链接 / 封面标题 |

**加/改分册只改一处**：`volumes.json`（或界面「分册配置…」），
自检 `--tool name-map --check`。程序在步骤 8、9 前各跑一次。

---

## 九、打包成单个 exe（可选）

```bash
python build_exe.py            # 默认 onefile：建/复用 venv → 装依赖 → 打包 → 冒烟
python build_exe.py --onedir   # 备选：打成目录（启动快，但要整目录分发）
python build_exe.py --clean    # 打包前先删 build/ 与 dist/
python build_exe.py --no-smoke # 只打包
python build_exe.py --console  # 保留控制台（排查打包问题用）
```

产物默认 `dist/PDF构建器-多版本.exe`，约 40 MB，**单个文件、旁边没有附带目录**。

| | |
|-|-|
| ✅ 省掉 | 装 PyQt6 / pypdf；带一堆 `.py`；首次那轮 pip |
| ❌ 仍然要 | **git**（克隆源码/译文）、**TeX Live**、**一个 Python 解释器**（步骤 4 要建独立 venv）、**网络** |

**「双击就能出 PDF」做不到** —— exe 只把「界面 + 17 个内置工具」合成了一个文件，
真正的构建链本来就在外部进程里跑。

打包后有三处路径变化（已在代码里处理）：`config.json` 与 `gui-startup-error.log`
落在 **exe 旁边**，无控制台时 `--tool`/`--cli` 的输出写 `tool-output.log`。
主程序统一走 `app_dir()`（取 `sys.executable` 的父目录），而不是 `__file__`
（onefile 下那是临时解压目录 `_MEIPASS`，退出即删）。

**onefile 的已知代价**（不是 bug）：每次启动多等几秒（要解压到 `%TEMP%`）；
步骤 7 会慢一些（`makeindex-fix.py` 要反复拉起 exe 自己解压）；可能被杀软误报。

exe 里工具照常可用：`"dist/PDF构建器-多版本.exe" --tool name-map --check`。
注意 `--tool` 不带工具名时**退出码是 2**（用法提示），不是出错。

> 打包的判据必须是「**把 exe 拷进一个空目录再跑一个真实步骤**」——
> 在 `dist/` 原地跑通过证明不了什么。唯一的验收方式就是这个。
