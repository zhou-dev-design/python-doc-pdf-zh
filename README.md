# python-doc-pdf-zh

把 **CPython 官方 reST 文档** 与 **python-docs-zh-cn 中文译文** 编译成**中文分册 PDF**。

> **为什么需要它**：官方 2025-09 决定停止发布文档 PDF——理由是使用率低，而 PDF 这类非 HTML
> 构建却占掉文档构建的大部分算力（2025 年 5–7 月这批构建意外停了三个月，**没有人发现**）。
> 所以 **3.14 起不再提供预构建 PDF**，3.13 及更早的仍挂在 CDN 上、但不再更新。详见
> [官方讨论](https://discuss.python.org/t/101343)。
>
> 中文读者因此同时失去两样东西：官方 PDF 和中文 PDF。本项目补的就是这个位——沿用官方推荐的
> Sphinx + LaTeX 流程（主题、字体、分册结构与官方 3.13 那份 PDF 一致），接上译文产出**中文分册**，
> 并额外合成一册，每天自动发布到 Releases。

| | |
|-|-|
| 构建版本 | **3.11 / 3.12 / 3.13 / 3.14 / 3.15**（3.10 已于 2026-10-31 EOL） |
| 出稿 | **每天北京时间 14:30–15:30**（11-07 实测 14:37，见下） |
| 产物 | 每版本 **2 个附件**：合并册 PDF + 全部分册的 RAR |
| 落点 | **Releases**，tag = `v<完整版本>`（如 `v3.15.2`），同版本重跑原地更新 |
| 历史 | **`old` 分支**：EOL 版本、被新补丁版顶下来的旧版，按 tag 存目录 |
| 入口 | CI：`ci/linux/pdf_builder_linux.py`；本机：`sphinx-pdf/gui/pdf_builder_multi.py` |

> 要图形界面、要在本机 Windows 上跑，见 [`sphinx-pdf/gui/README.md`](sphinx-pdf/gui/README.md)。
> 要逐步操作与排错清单，见 [`构建Python文档PDF-完整步骤.md`](构建Python文档PDF-完整步骤.md)。

---

## 各版本现状（构建时间 / 译文更新时间）

<!-- BUILD-TABLE:BEGIN -->
| 版本 | 小版本号 | PDF 构建时间（北京时间） | 译文最后更新（北京时间） |
|-|-|-|-|
| 3.10 | 3.10.22 | 2026-11-03 19:48 | 2026-10-19 14:32 |
| 3.11 | 3.11.18 | 2026-11-08 14:46 | 2026-11-08 12:38 |
| 3.12 | 3.12.16 | 2026-11-08 14:45 | 2026-11-08 12:45 |
| 3.13 | 3.13.18 | 2026-11-08 14:46 | 2026-11-08 12:57 |
| 3.14 | 3.14.10 | 2026-11-08 14:46 | 2026-11-08 13:20 |
| 3.15 | 3.15.2 | 2026-11-08 14:46 | 2026-11-08 13:23 |
<!-- BUILD-TABLE:END -->

一个版本线一行，小版本号**就地覆盖**：3.15.2 → 3.15.3 那天第二列变成 3.15.3，**不会多出一行**；
旧补丁版产物在 `old` 分支（`old/v3.15.2/`），历史不在这张表里堆积。
**3.10 已 EOL**，那一行是它**最后一次构建**的定格数据，不再更新。

口径：

- **PDF 构建时间** = 拉取 `.po` 的时刻（步骤 3），不是开始构建、也不是上传 Release 的时间。
- **译文最后更新** = `python-docs-zh-cn` 对应分支最后一次提交（`git log -1 --format=%cI`），不是 .po 的修改时间。
- 两者都已换算成北京时间，读者不用再 +8。
- 表格由 CI 自动改写（`summary` 只替换两个标记之间的内容，README 其余部分不动），手改会被下次构建覆盖；
  某版本这轮没构建成功时**保留它上一行**，不会变成 `?`。

---

## 一、每天做什么

```
GitHub Actions（每天自动一次）
        │
   ┌────▼─────┐  prepare：① 刷 version-titles.json（变了就提交）
   │ prepare  │           ② 读 versions → 拆 matrix（3.11~3.15，五个 job 并行）
   └──┬────┬──┘
      │    └──► archive-eol：把 EOL 版本的 release 挪进 old 分支后删除（幂等）
      │
   ┌──▼────────────────────────────────────────────────┐
   │ 1 装 TeX Live / poppler / 中文字体 / cairo         │
   │ 2 装该版本 Python（actions/setup-python）          │
   │ 3 --preflight 体检 → selftest.py 自检              │
   │ 4 构建：pdf_builder_linux.py --versions X          │
   │ 5 上传 artifact（保留 7 天，排错用）                │
   │ 6 发布到 Releases（先清后传，核对恰好 2 个附件）      │
   └───────────────────────────────────────────────────┘
```

五个版本**互不影响**（`fail-fast: false`）：3.15 失败不会拦住 3.11 出稿。

### 出稿时间：每天下午 14:30–15:30

**只管「每天跑一次」，具体时刻由 GitHub 的排队决定**，别按分钟等。排队偏移不是固定值：
实测它跟着计划时刻走，本仓库从 7h50 降到 6h39、再降到 5h51。计划时刻 UTC 00:47（北京 08:47），出稿落在下午两点半到三点半之间。

| 日期 | 计划(UTC) | 延迟 | 开始 | 五个版本全部发布完 |
|-|-|-|-|-|
| 2026-11-03 | 04:00 | 7h46 | 19:46 | 20:04 |
| 2026-11-04 | 03:47 | 7h49 | 19:36 | 19:54 |
| 2026-11-05 | 03:47 | 7h43 | 19:30 | 19:47 |
| 2026-11-06 | 00:47 | 6h39 | 15:26 | 15:42 |
| 2026-11-07 | 00:47 | **5h51** | **14:37** | 14:52 |

⇒ 按「**北京时间 15:30 之后来取**」稳拿到（最晚一次 15:26 出稿）；想早点试就 14:45 之后来刷。
想立刻要：Actions 页 → Run workflow（同参数、同结果，只跳过排队）。

> 2026-11-06 起计划时刻前移 3 小时（03:47 → 00:47），出稿从 19:30 挪到 14:37，提前近 5 小时。
> **不能再往前挪**：00:47 已经是「即使排队延迟变成 0 也不跨 UTC 日期」的最早时刻，再早文件名就会和北京日期差一天。
> 表里的时间都是**实际**时刻，不是计划时刻。

---

## 二、产物：Releases 模型

```
Releases
├── v3.15.2   合并册 PDF + 全册 RAR      ← 同版本重跑原地更新
├── v3.14.10
├── v3.13.18
├── v3.12.16
└── v3.11.18
old 分支
└── v3.10.22/  ← EOL 归档：Python-3.10.22-docs-20261103.pdf + .rar
```

| 情况 | 结果 |
|-|-|
| 同一版本连跑两天 | 该 release **原地更新**（同名附件 `--clobber` 覆盖），不会一天一个 |
| 3.15.2 → 3.15.3 | 旧版附件搬进 `old` 分支、**推成功之后**才删它的 release ⇒ 每条线只有一个 release |
| 版本 EOL（如 3.10） | `archive-eol` 把它整条 release 搬进 `old/v3.10.22/`，再删 release 和 tag |
| 跑一年 | Releases 数量 = 版本线条数（5 条），体积不随天数增长 |

- **tag 不带日期**（`v<完整版本>`）。日期写在 release 标题「Python 3.15.2 文档（20261103）」、
  正文和压缩包名里——既带日期，又不会一天一个 release。
- **完整版本号的口径是官方文档站标题**（`docs.python.org/zh-cn/3.15/` 的 h1），缓存在
  `sphinx-pdf/version-titles.json`。**不用解释器报告**：CI 的 `setup-python` 补丁版常落后于文档站，
  跟着它走会「内容新、文件名旧」。
- **每次构建都刷新这个缓存**（`prepare` 第一件事，`--tool titles --write`），有变化就自动
  commit + push，build job 显式拉新值。缓存停在旧值时，新内容会被原地覆盖成旧名字、旧 release
  也不会归档，**而且全程零报错**——所以 build job 里再核一次，与官方不一致硬失败。
- **附件恰好 2 个**：

  ```
  Python-3.15.2-docs-20261103.pdf   合并册（单本，直接下）
  Python-3.15.2-docs-20261103.rar   39 个分册 + 合并册 + 验收报告（包内中文原名）
  ```

  单册不逐个挂：GitHub 附件名只接受 ASCII，中文会被换成 `.`，还得额外维护映射表。**要单册就解压。**
- **先清后传**：发布前先删「不在本轮名单里」的旧附件，再统一上传，最后核对数量**恰好 2 个**。
- **压缩包打不出来就不发布**（`::error` 让 job 红）——只发单个 PDF 等于丢掉全部分册。
- **只有三根分支**：`main`（代码）、`ci-logs`（失败诊断证据，强推、永远 1 个提交）、`old`（历史产物）。
  分支里不放 PDF。

### EOL 机制

1. `archive-eol` job 的 `EOL_TAGS` 里加一个 tag（目前 `v3.10.22`）；
2. 该 job 把 release 附件下载 → 推进 `old/<tag>/` → 删 release 和 tag；
3. 从 `KNOWN_VERSIONS` 和 workflow 默认 `versions` 里删掉该版本。

它是**幂等**的（release 已不在就跳过），每次运行都无条件过一遍。只想归档、不构建：手跑时
`archive_only=true`。代码对 3.10 的支持**没有删**，把 `"3.10"` 加回 `KNOWN_VERSIONS` 即可重建。

---

## 三、每版几册（不是猜的，是官方的）

册数依据是各分支 `Doc/conf.py` 的 `latex_documents` + `Doc/howto/*.rst` 的文件数
（`--tool volumes --verify` 可联网逐条核对官方）：

| 版本 | 静态册 | howto | 合计 | 差异 |
|-|-|-|-|-|
| 3.11 | 9 | 20 | **29** | `distributing` 被上游并进 `installing` |
| 3.12 | 9 | 23 | **32** | |
| 3.13 | 10 | 27 | **37** | 拆出《内置参考手册》（builtins） |
| 3.14 | 10 | 28 | **38** | 新增远程调试附加协议 |
| 3.15 | 10 | 29 | **39** | 新增 abi3t 迁移 |
| ~~3.10~~ | 10 | 17 | ~~27~~ | **已 EOL**：多 `09分发 Python 模块`，无 builtins；产物在 `old` |

真源是 **`sphinx-pdf/volumes.json`**（分册名 / 编号 / 书签标题 / 版本区间 / 合并顺序）。三种改法：

1. **界面**：「① 版本与目录」→「分册配置…」，表格可视化编辑（行序 = 合并册一级顺序，带册数预览与自检）；
2. **导出再改**：`--tool name-map --dump volumes.json`；
3. **直接改文件**，改完 `--tool name-map --check` 自检。

版本区间是**闭区间**：`distributing` 填 `max=3.10`、`builtins` 填 `min=3.13`，
上游将来再删哪册，加一个 `max` 就行，不用改代码。

---

## 四、本地怎么跑

三条路，**同一份实现**（`pdf_builder_multi.py`），不会出现两套逻辑。

### A. 图形界面（推荐，Windows）

```bat
cd sphinx-pdf\gui
启动PDF构建器.bat          :: 或 python pdf_builder_multi.py
```

版本可多选、每版本一个独立日志面板、可只重跑某几步。
打包成 exe：`python build_exe.py`（onefile → `dist/PDF构建器-多版本.exe`）。
exe 只省「装 PyQt6 / 带一堆 .py」；`git`、TeX Live、一个 Python 解释器、网络一条都省不掉，
验收要在「拷进空目录」里做。

### B. 纯 bash 一键（无界面环境）

```bash
cd sphinx-pdf
./build-sphinx-pdf.sh            # 跑步骤 0~10
```

### C. CI 同款脚本（Linux）

```bash
python3 ci/linux/pdf_builder_linux.py --versions 3.15 --jobs 4      # 单版本全套
python3 ci/linux/pdf_builder_linux.py --versions 3.11,3.12,3.13,3.14,3.15 --jobs 4 --merge
python3 ci/linux/pdf_builder_linux.py --versions 3.15 --only 6,6b,7,7b,8,9   # 只跑后半段
python3 ci/linux/pdf_builder_linux.py --preflight --versions 3.15            # 只体检
```

它**不复制**构建逻辑，只是把主程序当库导入、覆盖少量平台相关方法（locale、`python` 别名、venv 重建 PATH）。

| 参数 | 说明 |
|-|-|
| `--versions` | 逗号分隔；多版本时内部按版本各起一个子进程 |
| `--jobs` | 同时是步骤 6 的 sphinx `-j` 与步骤 7 的册级并发 |
| `--source` | `github`（默认，直连）/ `auto`（镜像回退，国内本地用） |
| `--python-map 3.13=/path` | 指定版本用哪个解释器 |
| `--only` / `--from` | 按**步骤号**（不是行号）挑步骤 |
| `--clean` | 步骤 10 清理范围，CI 默认 `none`（留日志给验收报告） |

**产物目录**：`<base>/Python <完整版本> PDF 文档 <YYYYMMDD>/`；
**合并册**：同目录下 `Python <完整版本> 文档 <YYYYMMDD>.pdf`。

---

## 五、目录结构

```
.github/workflows/build-pdf-linux.yml   # 唯一流水线（prepare / archive-eol / build）
ci/linux/
  pdf_builder_linux.py                  # CI 入口：导入主程序 + 覆盖平台差异
  selftest.py                           # 平台胶水层自检（不联网）
  update_readme_table.py                # 汇总各版本构建信息，改写 README 表格
  README.md                             # CI 侧细节与排错
sphinx-pdf/
  gui/pdf_builder_multi.py              # ★ 唯一主程序：步骤 0~10 + PyQt6 界面 + 17 个内置工具
  gui/build_exe.py / *.spec             # PyInstaller 打包（--entry 选入口）
  gui/README.md                         # 界面说明
  build-sphinx-pdf.sh                   # 纯 bash 一键（步骤 0~10，全走 --tool）
  rename-pdf.sh                         # 英文 PDF → 中文名
  volumes.json                          # ★ 分册真源（可外置覆盖，读坏退回内置表）
  version-titles.json                   # 完整版本号缓存（来自官方文档站标题）
构建Python文档PDF-完整步骤.md             # 逐步操作 + 故障排查表
```

内置 17 个工具，用 `--tool` 调用（不带参数会列出全部）：

```bash
python sphinx-pdf/gui/pdf_builder_multi.py --tool name-map --check
python sphinx-pdf/gui/pdf_builder_multi.py --tool volumes --verify
python sphinx-pdf/gui/pdf_builder_multi.py --tool titles --write
python sphinx-pdf/gui/pdf_builder_multi.py --tool check-pdf-gaps <某册.pdf>
```

---

## 六、workflow 怎么配的

`.github/workflows/build-pdf-linux.yml`

| 项 | 值 | 为什么 |
|-|-|-|
| 触发 | 每天自动 1 次 + 手动 Run workflow | 具体时刻由 GitHub 排队，实际出稿见上文 |
| `on.workflow_dispatch` | 6 个输入 | `versions` / `jobs` / `merge` / `clean` / `push_branch` / `archive_only` |
| `runs-on` | `ubuntu-22.04` | 需要系统 TeX Live；Ubuntu 上 sphinx 的 `-j` 才真正生效 |
| `permissions` | `contents: write` | 建 Release、传附件、维护 `old` 分支 |
| `concurrency` | `build-pdf-linux-<ref>` | 上一轮没跑完时排队，不并行堆叠 |
| `max-parallel` | 5 | 五个版本同时起跑 |

手动触发（手机也行）：`Actions → 构建 Python 中文文档 PDF（Linux）→ Run workflow`。

> 定时触发时 `github.event.inputs.*` 全是空串，所以每个输入都写了兜底（`|| '4'`、`|| 'none'`、
> `!= 'false'`）。漏一处就会出现「每天跑完但不发布」。

---

## 七、常见问题

<details>
<summary><b>某个版本红了，其它还绿，正常吗？</b></summary>

正常，这是刻意的（`fail-fast: false`）。每个版本独立 job，失败的产物不会发布 ——
所以「有没有对应 Release」就是最干净的判据。
</details>

<details>
<summary><b>到点了却没看到新产物</b></summary>

先看 Actions 里有没有一条 `schedule` 运行：**有**，就是还在排队或还在构建（见过晚一两个小时的）；
**始终没有**，才是被丢弃。两种情况都可以手动 Run workflow 立刻补一次，产物与自动跑完全一样。
</details>

<details>
<summary><b>PDF 里正文是英文（封面却是中文）</b></summary>

最隐蔽的一类失败：**0 条 warning、页数书签索引全正常、验收报告全绿**。
老版本（3.10/3.11）的 `conf.py` 缺 `gettext_compact = False`，Sphinx 默认按「每个顶层目录一份 .mo」
找，而译文是每页一份（`library/array.mo`），一个都匹配不上。步骤 6 现在会自动补这一行；
`step6b` 也会在「整批汉字 < 2000 且过半册子无中文」时直接 `raise Fail`，不会再绿着发出去。
</details>

<details>
<summary><b>job 跑了不到 1 分钟就红，构建根都没有</b></summary>

死在「构建」之前：装依赖 / 装 Python / 体检 / 自检。workflow 里有「失败诊断」（`if: failure()`），
会把 `pip.log`、`clone.log`、`latex-build.log` 的末 60 行打到日志里。
</details>

<details>
<summary><b>Release 里的 PDF 是半成品 / 没有索引</b></summary>

看验收报告的「每步耗时」：步骤 7 异常短多半是 `makeindex` 没跑成。「构建全绿」≠「内容齐全」，用工具复核：

```bash
python3 sphinx-pdf/gui/pdf_builder_multi.py --tool check-pdf-gaps <合并册.pdf>
```

判据是**页面内容流字节数**，不能用 `extract_text()`（这套 PDF 是字体子集 + 自定义编码）。
</details>

<details>
<summary><b>Actions 分钟数会不会不够</b></summary>

本仓库是**公开**仓库 ⇒ 免费且不限分钟数。改私有才需要算：5 版本 × 约 20 分钟 × 每天 ≈ 3000 分钟/月，
会超 2000 的额度。
</details>

<details>
<summary><b>为什么不做 doctree 缓存来提速</b></summary>

`environment.pickle` 不会因为 `.po` 更新而失效。复用缓存会出现「译文更新了、PDF 还是旧中文」的
静默失败 —— 正是这个项目最忌讳的失败类型。所以每轮从零读入。
</details>

---

## 八、已知限制

1. **按册拆成 39 个独立工程并不会更快**：工作量约 61% 集中在「标准库」那一册，墙钟下限仍是它
   自己的耗时；按篇并行的 `-j` 才是对的切法。
2. **跨册 `:ref:` 引用本来就是断的**（`LaTeX Warning: Reference ... undefined`），分册编译的固有限制。
3. **自动构建不保证准点**：GitHub 的定时只是「尽力而为」，见过晚一两个小时的。
4. **旧版本要用它自己的工具链**：3.10 需要 `sphinx==3.4.3`、3.11 是 `7.2`、3.12 是 `8.2`；
   ≤3.12 一律读该分支自己的 `Doc/requirements.txt`，一刀切装最新版必失败。

---

## 附：官方 PDF 下载（3.6 – 3.13）

官方 2025-09 停止发布后，**旧文件仍挂在 CDN 上**（官方承诺不删），可作版式参照——
本项目的中文分册与它们同源（同一套 Sphinx + LaTeX + `python-docs-theme`）。

**三个坑**（都实测过）：

1. **3.6 ~ 3.11 的文件名带补丁号，但多数不是该版本最后一个补丁版**——停发之后的新补丁版都没有 PDF。
   下载页上写的版本号会 404（例如 3.11 页面写 `3.11.18`，实际只有 `3.11.14`；3.9 页面写 `3.9.25`，实际只有 `3.9.24`）。
2. **3.12 / 3.13 的文件名不带补丁号**（`python-3.13-docs-pdf-a4.zip`），看着像「滚动的、永远最新」，
   其实是**固定快照**——实际版本见下表「包内实际版本」列。
3. **中文站 3.7 的标题比实际落后 4 个补丁版**：`zh-cn/3.7/` 至今写 `3.7.13`（页脚「最后更新于 2022-03-16」），
   而英文站 `3.7/` 已经是 `3.7.17`——中文 3.7 分支 2022 年之后就没再重建过。
   **查版本要认英文站标题或 [endoflife.date](https://endoflife.date/python)，别认中文站标题。**

| 版本 | 中文版 A4 | 大小 | **出包时间** | **包内实际版本** | **官方最新** | 距官方最新 |
|-|-|-|-|-|-|-|
| 3.6 | [3.6.15](https://docs.python.org/zh-cn/3.6/archives/python-3.6.15-docs-pdf-a4.zip) | 22.9 MB | 2021-09-06 04:37 | 3.6.15 | 3.6.15 | ✅ **已是最新** |
| 3.7 | [3.7.13](https://docs.python.org/zh-cn/3.7/archives/python-3.7.13-docs-pdf-a4.zip) | 23.6 MB | 2022-03-17 03:28 | 3.7.13 | **3.7.17** | 落后 **4** 个补丁版 |
| 3.8 | [3.8.20](https://docs.python.org/zh-cn/3.8/archives/python-3.8.20-docs-pdf-a4.zip) | 24.7 MB | 2024-12-10 00:45 | 3.8.20 | 3.8.20 | ✅ **已是最新** |
| 3.9 | [3.9.24](https://docs.python.org/zh-cn/3.9/archives/python-3.9.24-docs-pdf-a4.zip) | 25.4 MB | 2025-10-17 11:25 | 3.9.24 | **3.9.25** | 落后 **1** 个补丁版 |
| 3.10 | [3.10.19](https://docs.python.org/zh-cn/3.10/archives/python-3.10.19-docs-pdf-a4.zip) | 26.5 MB | 2025-10-16 22:18 | 3.10.19 | **3.10.22**（已 EOL） | 落后 **3** 个补丁版 |
| 3.11 | [3.11.14](https://docs.python.org/zh-cn/3.11/archives/python-3.11.14-docs-pdf-a4.zip) | 27.1 MB | 2025-10-16 08:44 | 3.11.14 | **3.11.18** | 落后 **4** 个补丁版 |
| 3.12 | [3.12](https://docs.python.org/zh-cn/3.12/archives/python-3.12-docs-pdf-a4.zip) | 29.8 MB | 2025-09-30 04:44 | **3.12.11** | **3.12.16** | 落后 **5** 个补丁版 |
| 3.13 | [3.13](https://docs.python.org/zh-cn/3.13/archives/python-3.13-docs-pdf-a4.zip) | 32.9 MB | 2025-10-02 08:55 | **3.13.7** | **3.13.18** | 落后 **11** 个补丁版 |

> ⚠️ **8 份里只有 3.6 和 3.8 是"该版本线的最后一版"**，其余 6 份都停在半路：
>
> - **3.7 停在 3.7.13**，最后一版是 **3.7.17**（2023-06-06，EOL 前最后一个安全版）—— 差 4 个；
> - **3.9 停在 3.9.24**，最后一版是 **3.9.25**（2025-10-31，3.9 当天 EOL）—— 差 1 个；
> - 3.10 / 3.11 / 3.12 / 3.13 之后官方还各发了 3 / 4 / 5 / 11 个补丁版（3.13 那份 2025-10 出的，差一年多）。
>
> 3.6 / 3.8 之所以"恰好"是最新，只是因为停发那一刻它们的文档站正好停在最后一个补丁版上。
> 所以这些包只能当**版式参照**（看排版长什么样），要看**最新内容**得用本仓库 Releases 里的。

> **「出包时间」怎么来的**：读文件在 `docs.python.org` 上的 `Last-Modified`（已换算北京时间），
> 即官方最后一次构建/替换该包的时刻，与该补丁版的正式发布日期可能差 0~3 天。
> 按这列排开就能看到停发分界：最晚一份是 **3.9 的 2025-10-17 11:25**，此后 CDN 上再无新文件；
> 也就是说官方最后一批 PDF 出在 2025-10 的安全版构建，之后 3.10~3.13 的新补丁版**从来没有 PDF**。

> 以上 8 个链接在 2026-11-05 全部实测 HTTP 200 并读取过 `Last-Modified`。
> 英文版把路径里的 `zh-cn/` 去掉即可（体积约小 1/3）；3.6 ~ 3.11 另有 `-pdf-letter.zip`（Letter 纸），
> 3.12 起官方把 letter 版一并移除了。**英文版与 letter 版是同一批构建，出包时间与本表完全相同。**

---

## 九、许可与致谢

文档内容来自 [CPython](https://github.com/python/cpython) 与
[python-docs-zh-cn](https://github.com/python/python-docs-zh-cn)（均为 PSF License），
本仓库只做构建与排版，不改变原文授权。构建依赖 Sphinx、python-docs-theme、TeX Live、poppler。
