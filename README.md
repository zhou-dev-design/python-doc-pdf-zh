# python-doc-pdf-zh

把 **CPython 官方 reST 文档** 与 **python-docs-zh-cn 中文译文** 编译成**中文分册 PDF**。

> **为什么需要它**：官方 2025-09 起停止发布文档 PDF——使用率低，而 PDF 构建却占掉大部分算力
> （[官方讨论](https://discuss.python.org/t/101343)）。3.14 的下载页现在明确写着
> “我们不再提供文档的预构建 PDF”
> （[docs.python.org/zh-cn/3.14/download.html](https://docs.python.org/zh-cn/3.14/download.html)）。
>
> 所以中文读者手里只剩一份 2025-10 的旧快照：**3.14.0 正式版之后的所有 3.14.x 修订、
> 以及整个 3.15，都没有官方中文 PDF**。本项目沿用官方那套 Sphinx + LaTeX 流程
> （主题、字体、分册结构与官方 3.13 一致），接上最新译文产出**中文分册**，并合成一册，
> 每天自动发布。
>
> 官方各版 PDF 的下载链接、大小与冻结日期，见文末「附：官方 PDF 下载」。

| | |
|-|-|
| 构建版本 | **3.11 / 3.12 / 3.13 / 3.14 / 3.15**（3.10 已于 2026-10-31 EOL） |
| 出稿 | **每天北京时间 14:50–17:00**（近 16 次 14:52–16:50，均值 15:47；密集段 15:10–16:10） |
| 耗时 | **约 17 分钟**（近 16 次 10m49s–24m01s，不含排队） |
| 产物 | 每版本 **2 个附件**：合并册 PDF + 全部分册的 RAR |
| 落点 | **Releases**，tag = `v<完整版本>`（如 `v3.15.2`），同版本重跑原地更新 |
| 历史 | **`old` 分支**：EOL 版本、被新补丁版顶下来的旧版，按 tag 存目录 |
| 入口 | CI：`ci/linux/pdf_builder_linux.py`；本机：`sphinx-pdf/gui/pdf_builder_multi.py` |

> 纸张统一 **A4（595×842pt）**。3.11 的上游 `Doc/conf.py` 把 `papersize` 写成 `'a4'`——
> 那不是 LaTeX 的纸张选项，会被静默忽略、整册按默认的 Letter（612×792pt）排；构建时
> 已自动纠正为 `a4paper`（3.12 起上游自己写对了）。
>
> 要图形界面、要在本机 Windows 上跑，见 [`sphinx-pdf/gui/README.md`](sphinx-pdf/gui/README.md)。
> 要逐步操作与排错清单，见 [`构建Python文档PDF-完整步骤.md`](构建Python文档PDF-完整步骤.md)。

---

## 各版本现状（构建时间 / 译文更新时间）

<!-- BUILD-TABLE:BEGIN -->
| 版本 | 小版本号 | PDF 构建时间（北京时间） | 译文最后更新（北京时间） |
|-|-|-|-|
| 3.10 | 3.10.22 | 2026-11-03 19:48 | 2026-10-19 14:32 |
| 3.11 | 3.11.18 | 2026-11-21 15:45 | 2026-11-08 20:37 |
| 3.12 | 3.12.16 | 2026-11-21 15:45 | 2026-11-08 12:45 |
| 3.13 | 3.13.18 | 2026-11-21 15:45 | 2026-11-08 12:57 |
| 3.14 | 3.14.10 | 2026-11-21 15:45 | 2026-11-20 14:31 |
| 3.15 | 3.15.2 | 2026-11-21 15:45 | 2026-11-20 14:34 |
<!-- BUILD-TABLE:END -->

一个版本线一行，小版本号**就地覆盖**：3.15.2 → 3.15.3 那天第二列变成 3.15.3，**不会多出一行**；
旧补丁版产物在 `old` 分支（`old/v3.15.2/`），历史不在这张表里堆积。
**3.10 已 EOL**，那一行是它**最后一次构建**的定格数据，不再更新。

口径：**PDF 构建时间** = 拉取 `.po` 的时刻（步骤 3），不是开始构建或上传 Release 的时间；
**译文最后更新** = `python-docs-zh-cn` 对应分支最后一次提交（`git log -1 --format=%cI`），不是 `.po` 的 mtime。
两者均已换算北京时间。表格由 CI 自动改写（只替换两个标记之间的内容），手改会被覆盖；
某版本这轮没构建成功时**保留上一行**，不会变成 `?`。

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

### 出稿时间：每天下午 14:50–17:00

**只管「每天跑一次」，具体时刻由 GitHub 的排队决定**，别按分钟等。

计划 UTC 00:47（北京 08:47）。排队平均 **6h42**（5h51–7h45），构建平均 **17m10s**（10m49s–24m01s），
**平均 15:47 出稿**，实测 14:52–16:50；对外给 14:50–17:00，不写单日时刻。

**最密集时段**：15:10–16:10（12/16）。逐次记录见 workflow 头部注释。

> 计划时刻不会再往前挪：00:47 已经是最早能设的时刻，再早的话，一旦某天延迟变小，
> 构建目录名里的日期就会比北京日期早一天。想立刻拿：Actions 页 → Run workflow（不走队列）。

---

## 二、产物：Releases 模型

```
Releases
├── v3.15.2   合并册 PDF + 全册 RAR      ← 同版本重跑原地更新
├── v3.14.10 / v3.13.18 / v3.12.16
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

- **tag 不带日期**（`v<完整版本>`），日期只写进标题、正文和包名 —— 既带日期，又不一天一个 release。
- **版本号取官方文档站标题**（`zh-cn/3.15/` 和 `3.15/` 的 h1，**取较新者**），缓存在
  `sphinx-pdf/version-titles.json`；不用解释器报告（CI 的 `setup-python` 补丁版常落后，会「内容新、
  文件名旧」）。只认中文站也不行——那边等翻译分支重建，历史上滞后过（3.7 差 4 个补丁版）。
- **每轮构建都刷新该缓存**并自动 commit，build job 拉新值后再核一次 —— 缓存停在旧值会让新内容
  被覆盖成旧名字、旧 release 不归档，而且**零报错**。
- **附件恰好 2 个**：

  ```
  Python-3.15.2-docs-20261103.pdf   合并册（单本，直接下）
  Python-3.15.2-docs-20261103.rar   39 个分册 + 合并册 + 验收报告（包内中文原名）
  ```

  单册不逐个挂：GitHub 附件名只接受 ASCII，中文会被换成 `.`，还得额外维护映射表。**要单册就解压。**
- **先清后传**：发布前删掉不在本轮名单里的旧附件，再统一上传，最后核对**恰好 2 个**；
  压缩包打不出来就不发布（`::error` 让 job 红）——只发单个 PDF 等于丢掉全部分册。
- **三根分支**：`main`（代码）、`ci-logs`（失败诊断证据，强推、永远 1 个提交）、`old`（历史产物），都不放 PDF。

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
界面「① 版本与目录」→「分册配置…」可视化编辑（行序 = 合并册一级顺序，带册数预览与自检）；
`--tool name-map --dump volumes.json` 导出再改；或直接改文件后跑 `--tool name-map --check` 自检。

版本区间是**闭区间**（`distributing` 填 `max=3.10`、`builtins` 填 `min=3.13`），
上游将来再删哪册，加一个 `max` 就行，不用改代码。

---

## 四、本地怎么跑

三条路，**同一份实现**（`pdf_builder_multi.py`），不会出现两套逻辑。

### A. 图形界面（推荐，Windows）

```bat
cd sphinx-pdf\gui
启动PDF构建器.bat          :: 或 python pdf_builder_multi.py
```

版本可多选、每版独立日志面板、可只重跑某几步。打包 exe：`python build_exe.py`
（onefile → `dist/PDF构建器-多版本.exe`）。exe 只省「装 PyQt6 / 带一堆 .py」——
`git`、TeX Live、Python 解释器、网络一条都省不掉，验收要在「拷进空目录」里做。

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
  selftest.py / update_readme_table.py  # 胶水层自检 / 改写本文表格
  README.md                             # CI 侧细节与排错
sphinx-pdf/
  gui/pdf_builder_multi.py              # ★ 唯一主程序：步骤 0~10 + PyQt6 界面 + 17 个内置工具
  gui/build_exe.py / *.spec / README.md # 打包脚本（--entry 选入口）/ 界面说明
  build-sphinx-pdf.sh / rename-pdf.sh   # 纯 bash 一键（步骤 0~10）/ 英文 PDF 改名
  volumes.json                          # ★ 分册真源（可外置覆盖，读坏退回内置表）
  version-titles.json                   # 完整版本号缓存（中英文站 h1 取较新）
构建Python文档PDF-完整步骤.md             # 逐步操作 + 故障排查表
```

内置 17 个工具，`--tool` 调用（不带参数列出全部）：

```bash
python sphinx-pdf/gui/pdf_builder_multi.py --tool name-map --check        # 分册表自检
python sphinx-pdf/gui/pdf_builder_multi.py --tool volumes --verify       # 联网核对官方册数
python sphinx-pdf/gui/pdf_builder_multi.py --tool check-pdf-gaps <册.pdf> # 查成品缺页
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

最隐蔽的失败：**0 条 warning、页数书签索引全正常、验收报告全绿**。老版本（3.10/3.11）的 `conf.py`
缺 `gettext_compact = False`，Sphinx 按「每个顶层目录一份 .mo」找，而译文是每页一份（`library/array.mo`），
一个都匹配不上。步骤 6 会自动补这行，`step6b` 再兜底（整批汉字 < 2000 且过半册子无中文就 `raise Fail`）。
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

本仓库是**公开**仓库 ⇒ 免费且不限分钟数。改私有才要算：5 版本 × 约 20 分钟 × 30 天 ≈ 3000 分钟/月，会超 2000 的额度。
</details>

<details>
<summary><b>为什么不做 doctree 缓存来提速</b></summary>

`environment.pickle` 不会因为 `.po` 更新而失效，复用缓存就会出现「译文更新了、PDF 还是旧中文」的
静默失败 —— 正是这个项目最忌讳的失败类型，所以每轮从零读入。
</details>

---

## 八、已知限制

1. **按册拆成三四十个独立工程并不会更快**：工作量约 61% 集中在「标准库」那一册，墙钟下限仍是它
   自己的耗时；按篇并行的 `-j` 才是对的切法。
2. **跨册 `:ref:` 引用本来就是断的**（`LaTeX Warning: Reference ... undefined`），分册编译的固有限制。
3. **旧版本要用它自己的工具链**：3.10 需要 `sphinx==3.4.3`、3.11 是 `7.2`、3.12 是 `8.2`；
   ≤3.12 一律读该分支自己的 `Doc/requirements.txt`，一刀切装最新版必失败。
4. **排版引擎锁定 TeX Live 2022**：CI 是 Ubuntu 22.04 自带的 2022（`xelatex` 自报
   `XeTeX 0.999993 (TeX Live 2022/dev/Debian)`），与官方 PDF 的构建机（Debian 12 的
   `xdvipdfmx (20220710)`）同代 —— 版式因此对得上，换成别的 TeX Live 版本会有毫米级页数差异。

---

## 附：官方 PDF 下载（3.6 – 3.14，全部停在 2025-10）

官方 2025-09 停发 PDF 后，旧文件仍挂在 CDN 上，可作**版式参照**（与本项目同源，3.8 起同为
TeX Live 2022；包内也是分册，3.14 共 37 个 PDF）。

**3.15 没有官方 PDF**；3.13 / 3.14 都停在 2025-10-02——3.14 那份是 rc3（2025-09-18）到
final（2025-10-07）之间的快照（[PEP 745](https://peps.python.org/pep-0745/)）。

**文件名里的版本号别信**：3.6~3.11 带补丁号但多数不是最后一版，3.12/3.13 不带号（固定快照）。
以表内「包内实际版本」为准。

| 版本 | 中文版 A4 | 大小 | 出包日期 | TeX | 包内实际版本 | 官方最新 | 落后 |
|-|-|-|-|-|-|-|-|
| 3.6 | [3.6.15](https://docs.python.org/zh-cn/3.6/archives/python-3.6.15-docs-pdf-a4.zip) | 22.9 MB | 2021-09-06 | 2020 | 3.6.15 | 3.6.15 | — |
| 3.7 | [3.7.13](https://docs.python.org/zh-cn/3.7/archives/python-3.7.13-docs-pdf-a4.zip) | 23.6 MB | 2022-03-17 | 2020 | 3.7.13 | 3.7.17 | 4 版 |
| 3.8 | [3.8.20](https://docs.python.org/zh-cn/3.8/archives/python-3.8.20-docs-pdf-a4.zip) | 24.7 MB | 2024-12-10 | 2022 | 3.8.20 | 3.8.20 | — |
| 3.9 | [3.9.24](https://docs.python.org/zh-cn/3.9/archives/python-3.9.24-docs-pdf-a4.zip) | 25.4 MB | 2025-10-17 | 2022 | 3.9.24 | 3.9.25 | 1 版 |
| 3.10 | [3.10.19](https://docs.python.org/zh-cn/3.10/archives/python-3.10.19-docs-pdf-a4.zip) | 26.5 MB | 2025-10-16 | 2022 | 3.10.19 | 3.10.22 | 3 版 |
| 3.11 | [3.11.14](https://docs.python.org/zh-cn/3.11/archives/python-3.11.14-docs-pdf-a4.zip) | 27.1 MB | 2025-10-16 | 2022 | 3.11.14 | 3.11.18 | 4 版 |
| 3.12 | [3.12](https://docs.python.org/zh-cn/3.12/archives/python-3.12-docs-pdf-a4.zip) | 29.8 MB | 2025-09-30 | 2022 | 3.12.11 | 3.12.16 | 5 版 |
| 3.13 | [3.13](https://docs.python.org/zh-cn/3.13/archives/python-3.13-docs-pdf-a4.zip) | 32.9 MB | 2025-10-02 | 2022 | 3.13.7 | 3.13.18 | 11 版 |
| 3.14 | [3.14](https://docs.python.org/zh-cn/3.14/archives/python-3.14-docs-pdf-a4.zip) | 34.2 MB | 2025-10-02 | 2022 | 3.14.0rc3 | 3.14.10 | 11 版 |

⇒ **9 份里只有 3.6、3.8 是该版本线的最后一版**，其余看版式可以，看内容不行——要最新内容用本仓库 Releases。

> 「TeX」列读自 PDF 元数据的 `Producer`：3.6/3.7 是 `XeTeX 0.99998`，3.8 起是 `xdvipdfmx (20220710)`
> = TeX Live 2022。出包日期取自 CDN 的 `Last-Modified`；该列表按 **UTC** 显示，表内已换算成北京时间。
> 英文版去掉路径里的 `zh-cn/` 即可（体积小约 1/3）；查补丁版号认英文站或 [endoflife.date](https://endoflife.date/python)，中文站 3.7 还停在 `3.7.13`。

---

## 九、许可与致谢

文档内容来自 [CPython](https://github.com/python/cpython) 与
[python-docs-zh-cn](https://github.com/python/python-docs-zh-cn)（均为 PSF License），
本仓库只做构建与排版，不改变原文授权。

**构建**：[Sphinx](https://www.sphinx-doc.org/) +
[python-docs-theme](https://github.com/python/python-docs-theme) +
[TeX Live](https://www.tug.org/texlive/)（CI 用 Ubuntu 22.04 自带的 2022，与官方 PDF 的构建机同代）。

**验收**：[poppler](https://poppler.freedesktop.org/) —— `pdfinfo` 查页数与残片、
`pdffonts` 查中文字体有没有真嵌进去、`pdftotext` 取封面标题。
