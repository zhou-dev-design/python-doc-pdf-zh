# Python 中文文档 PDF 构建器

把 **CPython 官方 reST 文档** 和 **python-docs-zh-cn 的中文译文**，编译成一套可分册阅读的
中文 PDF（3.13 → 37 册 / 3.14 → 38 册 / 3.15 → 39 册），外加一册带完整书签的**合并本**。

> 它不是「一条 sphinx 命令」：真正的难点在于 LaTeX 编译、索引页码、译文缺失、封面标题
> 这些地方**出错时不报错**。本项目一半的代码是用来把这类静默失败变成可判定的事实。

| 项目 | 说明 |
|-|-|
| 输入 | CPython `Doc/`（稀疏克隆）+ `python-docs-zh-cn` 的 `.po` |
| 输出 | `Python 3.15.1 PDF 文档 20261102/` 下 39 册 PDF + 验收报告 + 合并册 |
| 平台 | Windows（图形界面，主力）/ Linux·WSL（命令行，读入快 3~7 倍） |
| 自动化 | GitHub Actions 每天北京时间 12:00 构建，产物推到 `v<完整版本>` 分支 |
| 依赖 | Python 3.10+、Sphinx 8、TeX Live（xelatex）、git、poppler |

---

## 一、先看效果与代价

| 阶段 | Windows（单核） | Linux（`-j 4`） |
|-|-|-|
| 步骤 6 读入 553 篇 + 套 9.3 万条译文 | **22~29 分钟** | **7.5~8.5 分钟**（推算） |
| 步骤 7 编译 39 册 | 12~15 分钟 | 10~15 分钟 |
| 单版本合计 | 41~52 分钟 | 25~32 分钟 |

两句话解释差距的来源：

1. **Sphinx 的并行只支持 POSIX**（`parallel_available = HAS_MULTIPROCESSING and os.name == 'posix'`，
   且 `ParallelTasks` 硬编码 `get_context('fork')`）——Windows 上 `-j 5` 只是安慰剂，
   实测每个 sphinx 进程只占 **0.95 个核**，三版本合计 2.87 / 18 核；
2. 这一步 99.5% 的时间花在**读入**（写出 `.tex` 只要 16 秒），而读入的大头是
   **把 9 万条中文译文套进 doctree**（同一份文档：无译文 194 s → 有译文 1361 s，7 倍）。

---

## 二、三种用法

### 1. Windows 图形界面（日常最省事）

```text
双击 sphinx-pdf/gui/启动PDF构建器.bat
或   直接运行打包好的 PDF构建器-多版本.exe
```

- 勾选 3.13 / 3.14 / 3.15 → 每个版本一个独立子进程、独立日志面板；
- 可以只跑某几步（`起始步骤` / 只跑 `6b,7,7b,8`）；
- 打包成单文件 exe：`python sphinx-pdf/gui/build_exe.py --entry pdf_builder_multi.py --name PDF构建器-多版本`

### 2. Linux / WSL 命令行（跑得最快）

```bash
# 依赖（Ubuntu / Debian）
sudo apt-get install -y git latexmk texlive-xetex texlive-latex-extra texlive-binaries \
     texlive-lang-chinese fonts-noto-cjk poppler-utils libcairo2

# 体检 → 自检 → 构建
python3 ci/linux/pdf_builder_linux.py --preflight --versions 3.13,3.14,3.15
python3 ci/linux/selftest.py
python3 ci/linux/pdf_builder_linux.py --versions 3.13,3.14,3.15 --jobs 4 --merge
```

> 国内机器直连 `github.com` 不通时加 `--source auto`，会走内置的 7 个镜像自动回退。

### 3. GitHub Actions（每天自动出稿）

`.github/workflows/build-pdf-linux.yml`：每天 UTC 04:00（北京 12:00）跑，也可在 Actions 页手动触发。

```
main          ← 只有代码
v3.13.18      ← 3.13.18 的成品，永远只保留**最新那一天**
v3.14.10
v3.15.1
```

产物分支用「临时仓库孤子提交 + `git push --force`」写成，所以：同一小版本反复跑**只留最新**，
不同补丁版**各占一个分支**，仓库体积不随天数增长。

---

## 三、流水线：13 个步骤

```
0  前置检查        git / python / xelatex / latexmk / makeindex
1  取 CPython 源码  稀疏克隆：Doc + Include + Grammar + Parser + 少量单文件
2  取中文译文       python-docs-zh-cn 对应版本分支
3  铺 locales       按目录层级把 .po 放进 Doc/locales/zh_CN/LC_MESSAGES
4  venv 与依赖      sphinx / python-docs-theme / svg2pdfconverter / pypdf
5  构建 HTML        （可选，用于验证主题与站内链接）
6  构建 LaTeX 源    sphinx -b latex —— 99.5% 的时间花在这一步的「读入」阶段
6b 封面标题中文化   11 册的封面/页眉一起换掉（TITLES 表）
7  编译 PDF        逐册 latexmk；$makeindex 换成修索引的脚本
7b 索引自检        分组标题、\hyperpage 页码超链接、长条目断点，逐册核对
8  收集/验收/改名   复制产物 + 生成验收报告 + 中文文件名
9  合并成一册       39 册 → 一本带完整书签的总册（一级 11 个节点）
10 清理过程文件     可选：不清理 / 只删 build / 全删
```

**每一步的耗时都会写进 `验收报告.md`**（数据来自构建根的 `gui-build.log`），
失败时不会瞎编数字。

---

## 四、目录结构

```
.
├── sphinx-pdf/
│   ├── gui/
│   │   ├── pdf_builder_multi.py     ★ 唯一实现：11 个内置工具 + 流水线 + PyQt6 界面 + --cli
│   │   ├── pdf_builder_gui.py       单版本版（逻辑同步，命名规则略不同）
│   │   ├── build_exe.py             打包成单个 exe（PyInstaller onefile）
│   │   └── config*.json             界面配置（镜像、解释器、并发等）
│   ├── tools/*.py                   18 行转发器 → 都转到主程序的 --tool
│   ├── verify-pdf.py                产物验收（字体/书签/超链接）
│   └── 构建Python文档PDF-完整步骤.md  手改时的步骤手册 + 故障排查表
├── ci/linux/
│   ├── pdf_builder_linux.py         Linux/WSL 入口（不改主程序一行，只覆盖 3 个平台胶水方法）
│   ├── selftest.py                  逻辑自检，任何系统可跑
│   ├── setup-github.ps1             没有连接器/主站打不开时的建仓+推送脚本
│   └── README.md                    移植说明、apt 依赖、已知限制
└── .github/workflows/build-pdf-linux.yml
```

**内置工具**（`--tool <名字>`，不需要 GUI，也不需要装 PyQt6）：

```
name-map  check-doc-refs  alias-po  localize-titles  fix-index  fix-md-escapes
rename-pdf  merge-pdf  report  check-pdf-gaps  verify-pdf
extra-dump  extra-fetch  emit-makeindex-fix  emit-shims
```

---

## 五、命名规则（唯一真源在主程序 `name_map` 段）

| 对象 | 规则 | 例子 |
|-|-|-|
| 构建根 | `<基准目录>/Python <完整版本> PDF 文档 <YYYYMMDD>` | `Python 3.15.1 PDF 文档 20261102/` |
| 分册 | `NN主题.pdf`（编号按主题固定，缺主题留空号） | `05Python 标准库.pdf`、`0925远程调试附加协议.pdf` |
| 合并册 | `Python <完整版本> 文档 <YYYYMMDD>.pdf` | `Python 3.15.1 文档 20261102.pdf` |
| CI 分支 | `v<完整版本>` | `v3.15.1` |

**完整版本号一律问解释器**（`sys.version_info`），不写死 —— 换个小版本，名字会自动跟上。

```bash
# 自检映射表：编号撞车 / 文件名重复 / slug 拼错 / 合并顺序对不上
python sphinx-pdf/gui/pdf_builder_multi.py --tool name-map --check
```

---

## 六、几个值得单独说的设计

### 1. 只有一份实现

历史上映射表、译文接回、补件类型各存两三份，靠手工同步，**漏同步过两次且都是静默的**。
现在全部内联进 `pdf_builder_multi.py`，磁盘上的 `tools/*.py` 只是 18 行转发器。

> 加/改分册**只改 `name_map` 段一处**；`--tool name-map --check` 会拦住绝大部分手误。

### 2. 索引页码：makeindex 的产物必须再修一次

默认 `makeindex` 出来的 `.ind` 有几个坑：分组标题带非字母、页码不是超链接、长条目不断行。
步骤 7 把 latexmk 的 `$makeindex` 换成本项目的修复脚本，步骤 7b 再逐册核对
（判据：`\hyperpage` 出现次数、`\bigletter` 是否干净）。

### 3. 译文：三级兜底，且默认「只用上游」

| 来源 | 何时生效 |
|-|-|
| 上游 `.po` | 永远的第一选择（每次运行都 clone/fetch 到最新） |
| `alias-po` | 上游搬了目录、译文还留在旧路径时自动接回（3.14 命中 5 处） |
| `--i18n-extra-url` | 想给个别页面打补丁时，每次运行实时抓取；**留空 = 不打补丁** |

程序里**不再内置正文译文**（只内置封面/书签标题表），避免「内置副本越放越旧、还跟上游打架」。

### 4. 调度：大册先编（LPT）

步骤 7 从「小册先出」改成「按体积降序提交」——原来最大那册（`05Python 标准库`，2434 页，
占全部页数 56%）被排到最后，等它开工时另外 4 个 slot 全空，实测 **47% 的时间在空转**。

### 5. 平台差异

| 能力 | Windows | Linux |
|-|-|-|
| sphinx `-j` | 无效（上游只支持 POSIX） | 有效 |
| 并行 | 版本级（每版一个进程）+ 步骤 7 册级 | 同上 + 读入阶段 |
| 控制台窗口 | `CREATE_NO_WINDOW` 全兜住 | 不适用 |
| `python` 命令 | 通常有 | Ubuntu 24.04 起只有 `python3`，入口脚本会补一个软链 |

---

## 七、常见问题

<details>
<summary><b>构建很慢，而且看起来「只有一个版本在动」</b></summary>

三个版本一直在并行（用 `build/doctrees` 的写入时间能证明）。看起来只有一个在动，是因为
先跑完的那个进入了步骤 7（日志密集），其余的还在读入阶段（只有稀疏的进度行）。

真正的瓶颈是**单核 + 译文查表**，不是并发不够。想快就上 Linux（见第二节）。
</details>

<details>
<summary><b>某些页面还是英文</b></summary>

先分清两种情况，判据是**和上一版同一册逐条对比**：

- 「两版都英文」= 上游压根没译（正常，提 issue 给 python-docs-zh-cn）；
- 「上一版中文、这一版英文」= 才是回归，通常是改了点小写或措辞导致 `msgid` 失配，
  跑 `--tool alias-po` 能把一部分接回。

**不要只看 `translation progress` 或日志里有没有 warning** —— 这几类问题都是零报错的。
</details>

<details>
<summary><b>怎么确认「构建全绿」不等于「内容齐全」</b></summary>

```bash
python sphinx-pdf/gui/pdf_builder_multi.py --tool check-pdf-gaps <合并册.pdf>
```

判据是**页面内容流的字节数**（正文页 15000~25000，空白页 < 1000）。
不能用 `extract_text()`：这套 PDF 是字体子集 + 自定义编码，它返回空串。
</details>

<details>
<summary><b>exe 双击没反应 / 被杀软报毒</b></summary>

onefile 打包会自解压到 `%TEMP%\_MEIxxxx`，容易被误报。加白名单即可。
另外**不要单独拷 `dist/PDF构建器/` 里的 exe** —— onedir 形态的 exe 只是引导壳，
必须连带旁边的 `_internal/`。
</details>

<details>
<summary><b><code>github.com</code> 打不开，怎么推代码 / 授权失败</b></summary>

国内网络常见：`github.com:443` 的多数 IP 不可达，但 `api.github.com` 与
`ssh.github.com:443` 仍然可用。所以 GitHub 连接器授权会稳定失败（它要访问
`github.com/login/oauth/*`），这不是账号问题。

走 SSH 443 通道即可，细节见 [`ci/linux/README.md`](ci/linux/README.md) 第 7 节。
</details>

---

## 八、已知限制

1. **不做 doctree 缓存**：`environment.pickle` 不会因为 `.po` 更新而失效，复用缓存会出现
   「译文更新了、PDF 还是旧中文」的静默失败。宁可从零读入。
2. **按册拆成 39 个独立工程并不能提速**：工作量 61% 集中在「标准库」那一册，拆完墙钟下限仍是
   它自己的耗时（约 17~18 分钟）；按篇并行的 `-j` 才是对的切法。
3. **跨册 `:ref:` 本来就是断的**（`LaTeX Warning: Reference ... undefined`），这是分册编译的
   固有限制，与拆分无关。
4. Windows 上无法使用 sphinx 的并行，这是上游实现决定的，本项目只能绕（Linux）不能改。

---

## 九、许可与致谢

- 文档内容来自 [CPython](https://github.com/python/cpython)（PSF License）与
  [python-docs-zh-cn](https://github.com/python/python-docs-zh-cn)（同一许可）；
  本项目只做构建与排版，不改变原文授权。
- 排版依赖 [Sphinx](https://www.sphinx-doc.org/)、[python-docs-theme](https://github.com/python/python-docs-theme)、
  TeX Live、poppler。
- 本项目自身的脚本与流程：随文档一起分发，署名即可。
