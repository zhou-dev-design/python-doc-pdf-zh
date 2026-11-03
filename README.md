# python-doc-pdf-zh

把 **CPython 官方 reST 文档** 与 **python-docs-zh-cn 中文译文** 编译成**中文分册 PDF**。

**平时不需要你做什么**：GitHub Actions 每天自动构建，产物发布到 **Releases**。

| | |
|-|-|
| 构建版本 | **3.11 / 3.12 / 3.13 / 3.14 / 3.15**（3.10 已于 2026-10-31 EOL，见下） |
| 触发 | 每天 `cron "47 3 * * *"`（UTC）= 北京时间 **11:47**；也可在 Actions 页手动 Run workflow |
| 产物 | 每个版本 **2 个附件**：合并册 PDF + 全部分册的 RAR |
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
| 3.11 | ? | — | — |
| 3.12 | ? | — | — |
| 3.13 | ? | — | — |
| 3.14 | ? | — | — |
| 3.15 | 3.15.2 | 2026-11-03 21:26 | 2026-11-03 16:29 |
<!-- BUILD-TABLE:END -->

**这张表永远只有上面这 6 行**，一个版本线一行。小版本号是**就地覆盖**的：
3.15.2 → 3.15.3 那天，`3.15` 那行的第二列变成 3.15.3，**不会多出 3.15.2 一行**。
旧补丁版的产物在 `old` 分支（`old/v3.15.2/`），历史不在这张表里堆积。

**3.10 已 EOL**（2026-10-31 停止支持）：那一行是它**最后一次构建**的定格数据，
不再更新；产物在 `old` 分支的 `v3.10.22/`。

口径（三个都容易搞错，写清楚）：

- **PDF 构建时间** = **拉取 `.po` 的时刻**，即步骤 3 把译文铺进 `Doc/locales` 的时间。
  不是开始构建的时间，也不是上传 Release 的时间。
- **译文最后更新** = `python-docs-zh-cn` 对应分支的**最后一次提交时间**
  （`git log -1 --format=%cI`），不是 .po 文件的修改时间。
- 两者都换算成**北京时间（UTC+8）**。CI runner 是 UTC，换算在
  `build-info` 生成时完成，所以这里不需要读者自己加 8 小时。

这张表**每次构建自动更新**：每个 build job 产出 `build-info-<版本>.json`，
`summary` job 汇总后只替换两个标记之间的内容（README 其余部分不动）。
某个版本这轮没构建成功时，**保留它上一行**，不会变成 `?`。
手工改这张表没有意义——下次构建会被覆盖；要改口径请改
`ci/linux/update_readme_table.py`。

---

## 一、每天做什么

```
GitHub Actions（UTC 03:47 → 北京 11:47）
        │
   ┌────▼─────┐  prepare：① 对着官方文档站刷新 version-titles.json（变了就提交）
   │ prepare  │           ② 读 versions → 拆 matrix（默认 3.11~3.15，五个 job 并行）
   └──┬────┬──┘
      │    │
      │    └──► archive-eol：把已 EOL 版本的 release 挪进 old 分支后删除（幂等）
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

**定时为什么要避开整点**：GitHub 文档明确说高负载时 scheduled run 会「delayed or
dropped」，而 `:00` 是全世界 cron 的洪峰（所有写 `0 X * * *` 的都挤同一分钟）。
2026-11-03 的 12:00 那轮就晚了 7 小时 46 分才启动。挪到 `03:47` 只是降低概率，
**不保证准点** —— 要立刻出稿就手动触发，同参数同结果。

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

几个要点：

- **tag 不带日期**：`v<完整版本>`。日期写在 release 标题「Python 3.15.2 文档（20261103）」、
  正文和压缩包名里 —— 既带日期，又不会一天一个 release。
- **完整版本号的口径是官方文档站标题**（`docs.python.org/zh-cn/3.15/` 的 h1 =
  `Python 3.15.2 文档`），缓存在 `sphinx-pdf/version-titles.json`。**不用解释器报告**：
  CI 的 `setup-python` 补丁版常常落后于文档站，跟着它走会「内容新、文件名旧」。
- **每次构建都会自动刷新这个缓存**（`prepare` job 第一件事）：
  `--tool titles --write` 对着官方文档站抓一遍，**有变化就自动 commit + push 到 main**，
  后面的 build job 显式 `ref: main` 拉到新值。所以上游发了 3.15.3 的当天，
  构建就会产出 `v3.15.3` 这个新 tag，`v3.15.2` 随即被归档进 `old` —— 不需要人工改文件。
  这是**必须成功的前置步骤**，不是提醒：缓存停在旧值时，新内容会被原地覆盖成旧名字，
  旧 release 也不会归档，而且全程零报错。
  两道保险：build job 里再核一次，**与官方不一致硬失败**（`rc=2` 即官方站点取不到才降级为警告）；
  `--write` 是**合并写回**，网络部分失败不会把取不到的版本从缓存里删掉。
- **附件恰好 2 个**：

  ```
  Python-3.15.2-docs-20261103.pdf   合并册（单本，直接下）
  Python-3.15.2-docs-20261103.rar   39 个分册 + 合并册 + 验收报告（包内中文原名）
  ```

  单册不逐个挂：GitHub 附件名只接受 ASCII，中文会被服务端换成 `.`
  （`01Python 3.15 有什么新变化.pdf` → `01Python.3.15.pdf`），既认不出是哪册，
  还得额外维护一张映射表。**要单册就下压缩包解压**。
- **先清后传**：发布前先删「不在本轮名单里」的旧附件，再统一上传；上传后核对
  附件数**恰好 2 个**，多一个（旧分册没清净）少一个都报错。
- **压缩包打不出来就不发布**（`::error` 让 job 红）。早期版本会「只发单个 PDF」，
  那等于丢掉全部分册，现在宁可失败。
- **分支只有三根**：`main`（代码）、`ci-logs`（失败诊断证据，强推、永远 1 个提交，
  平时只有一份说明 README）、`old`（历史产物）。**分支里不放 PDF**。

### EOL 机制

Python 官方停止维护的版本会被摘出构建清单，走归档：

1. `archive-eol` job 的 `EOL_TAGS` 里加一个 tag（目前是 `v3.10.22`）；
2. 该 job 把 release 附件下载 → 推进 `old/<tag>/` → `gh release delete --cleanup-tag`；
3. 从 `KNOWN_VERSIONS`（主程序）和 workflow 默认 `versions` 里删掉该版本。

它是**幂等**的：release 已不在就跳过，所以每次运行都会无条件过一遍。
手动只想归档、不构建：Run workflow 时把 **`archive_only` 选 `true`**。

> 代码层面对 3.10 的支持**没有删**（`distributing` 册、`sphinx 3.4.3` 依赖、
> `gettext_compact` 补丁全在）。要重建就把 `"3.10"` 加回 `KNOWN_VERSIONS`。

---

## 三、每版几册（不是猜的，是官方的）

册数依据是各分支 `Doc/conf.py` 的 `latex_documents` + `Doc/howto/*.rst`
的文件数（`--tool volumes --verify` 可联网逐条核对官方）：

| 版本 | 静态册 | howto | 合计 | 差异 |
|-|-|-|-|-|
| 3.11 | 9 | 20 | **29** | `distributing` 被上游并进 `installing` |
| 3.12 | 9 | 23 | **32** | |
| 3.13 | 10 | 27 | **37** | 拆出《内置参考手册》（builtins） |
| 3.14 | 10 | 28 | **38** | 新增远程调试附加协议 |
| 3.15 | 10 | 29 | **39** | 新增 abi3t 迁移 |
| ~~3.10~~ | 10 | 17 | ~~27~~ | **已 EOL**：多 `09分发 Python 模块`，无 builtins；产物在 `old` |

真源是 **`sphinx-pdf/volumes.json`**（分册名 / 编号 / 书签标题 / 版本区间 / 合并顺序）。
三种改法：

1. **界面**：主界面「① 版本与目录」→「分册配置…」，表格可视化编辑，
   行顺序 = 合并册一级顺序，带各版本册数实时预览与自检；
2. **导出再改**：`--tool name-map --dump volumes.json`；
3. **直接改文件**：改完 `--tool name-map --check` 自检。

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
打包成 exe：`python build_exe.py`（默认 onefile → `dist/PDF构建器-多版本.exe`）

> **exe 只省「装 PyQt6 / 带一堆 .py」**。`git`、TeX Live、一个 Python 解释器、网络，
> 一条都省不掉。打包必须 **onefile**，验收要在「拷进空目录」里做。

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

它**不复制**构建逻辑，只是把主程序当库导入，覆盖少量平台相关方法
（locale、`python` 别名、venv 就绪后重建 PATH）。

| 参数 | 说明 |
|-|-|
| `--versions` | 逗号分隔；多版本时内部按版本各起一个子进程 |
| `--jobs` | 同时是步骤 6 的 sphinx `-j` 与步骤 7 的册级并发 |
| `--source` | `github`（默认，直连）/ `auto`（镜像回退，国内本地用） |
| `--python-map 3.13=/path` | 指定版本用哪个解释器 |
| `--only` / `--from` | 按**步骤号**（不是行号）挑步骤 |
| `--clean` | 步骤 10 清理范围，CI 默认 `none`（留日志给验收报告） |

**产物目录**：`<base>/Python <完整版本> PDF 文档 <YYYYMMDD>/`
**合并册**：同目录下 `Python <完整版本> 文档 <YYYYMMDD>.pdf`

---

## 五、目录结构

```
.github/workflows/build-pdf-linux.yml   # 唯一流水线（prepare / archive-eol / build）
ci/linux/
  pdf_builder_linux.py                  # CI 入口：导入主程序 + 覆盖平台差异
  selftest.py                           # 平台胶水层自检（不联网）
  setup-github.ps1                      # 首次配置仓库（SSH 443 通道等）
  README.md                             # CI 侧细节与排错
sphinx-pdf/
  gui/pdf_builder_multi.py              # ★ 唯一主程序：步骤 0~10 + PyQt6 界面 + 17 个内置工具
  gui/build_exe.py / *.spec             # PyInstaller 打包（--entry 选入口）
  gui/README.md                         # 界面说明
  build-sphinx-pdf.sh                   # 纯 bash 一键（步骤 0~10，全走 --tool）
  rename-pdf.sh                         # 英文 PDF → 中文名
  volumes.json                          # ★ 分册真源（可外置覆盖，读坏退回内置表）
  version-titles.json                   # 完整版本号缓存（来自官方文档站标题）
  命名.txt                              # 参考样张的命名表（外部参考，不改）
构建Python文档PDF-完整步骤.md             # 逐步操作 + 故障排查表
```

主程序内置 17 个工具，用 `--tool` 调用（不带参数会列出全部）：

```bash
python sphinx-pdf/gui/pdf_builder_multi.py --tool                 # 列出所有工具
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
| `on.schedule` | `47 3 * * *` | GitHub cron 按 **UTC**，减 8 小时是北京 11:47。**别写整点** |
| `on.workflow_dispatch` | 6 个输入 | `versions` / `jobs` / `merge` / `clean` / `push_branch` / `archive_only` |
| `runs-on` | `ubuntu-22.04` | 需要系统 TeX Live；Ubuntu 上 sphinx 的 `-j` 才真正生效 |
| `permissions` | `contents: write` | 建 Release、传附件、维护 `old` 分支 |
| `concurrency` | `build-pdf-linux-<ref>` | 上一轮没跑完时排队，不并行堆叠 |
| `max-parallel` | 5 | 五个版本同时起跑 |

手动触发（手机也行）：`Actions → 构建 Python 中文文档 PDF（Linux）→ Run workflow`。

> 定时触发时 `github.event.inputs.*` 全是空串，所以 workflow 里每个输入都写了兜底
> （`|| '4'`、`|| 'none'`、`!= 'false'`）。漏一处就会出现「每天跑完但不发布」。

---

## 七、常见问题

<details>
<summary><b>某个版本红了，其它还绿，正常吗？</b></summary>

正常，这是刻意的（`fail-fast: false`）。每个版本独立 job，失败的产物不会发布 ——
所以「有没有对应 Release」就是最干净的判据。
</details>

<details>
<summary><b>定时到点了却没跑</b></summary>

先分清「延迟」和「丢弃」，两者都是 GitHub 的机制，不是配置错：

```bash
gh run list --limit 5      # 看 event 列：schedule 才说明是定时
```

如果隔了几小时才出现一条 `schedule`，那是**延迟**（2026-11-03 晚过 7h46m）；
彻底不出现才是丢弃。要立刻出稿就手动 Run workflow。
</details>

<details>
<summary><b>PDF 里正文是英文（封面却是中文）</b></summary>

最隐蔽的一类失败：**0 条 warning、页数书签索引全正常、验收报告全绿**。
老版本（3.10/3.11）的 `conf.py` 缺 `gettext_compact = False`，
Sphinx 默认按「每个顶层目录一份 .mo」找，而译文是每页一份（`library/array.mo`），
一个都匹配不上。步骤 6 现在会自动补这一行；`step6b` 也会在「整批汉字 < 2000 且
过半册子无中文」时直接 `raise Fail`，不会再绿着发出去。
</details>

<details>
<summary><b>job 跑了不到 1 分钟就红，构建根都没有</b></summary>

死在「构建」之前：装依赖 / 装 Python / 体检 / 自检。workflow 里有「失败诊断」
（`if: failure()`），会把 `pip.log`、`clone.log`、`latex-build.log` 的末 60 行打到日志里。
</details>

<details>
<summary><b>Release 里的 PDF 是半成品 / 没有索引</b></summary>

看验收报告的「每步耗时」：步骤 7 异常短多半是 `makeindex` 没跑成。
「构建全绿」≠「内容齐全」，用工具复核：

```bash
python3 sphinx-pdf/gui/pdf_builder_multi.py --tool check-pdf-gaps <合并册.pdf>
```

判据是**页面内容流字节数**，不能用 `extract_text()`（这套 PDF 是字体子集 + 自定义编码）。
</details>

<details>
<summary><b>Actions 分钟数会不会不够</b></summary>

本仓库是**公开**仓库 ⇒ 免费且不限分钟数。改私有才需要算：5 版本 × 约 20 分钟 × 每天
≈ 3000 分钟/月，会超 2000 的额度。
</details>

<details>
<summary><b>为什么不做 doctree 缓存来提速</b></summary>

`environment.pickle` 不会因为 `.po` 更新而失效。复用缓存会出现「译文更新了、
PDF 还是旧中文」的静默失败 —— 正是这个项目最忌讳的失败类型。所以每轮从零读入。
</details>

---

## 八、已知限制

1. **按册拆成 39 个独立工程并不会更快**：工作量约 61% 集中在「标准库」那一册，
   墙钟下限仍是它自己的耗时；按篇并行的 `-j` 才是对的切法。
2. **跨册 `:ref:` 引用本来就是断的**（`LaTeX Warning: Reference ... undefined`），
   这是分册编译的固有限制。
3. **定时不保证准点**（见上），最长见过数小时延迟。
4. **旧版本要用它自己的工具链**：3.10 需要 `sphinx==3.4.3`、3.12 需要 `8.2`，
   ≤3.12 一律读该分支自己的 `Doc/requirements.txt`；一刀切装最新版必失败。

---

## 九、许可与致谢

文档内容来自 [CPython](https://github.com/python/cpython) 与
[python-docs-zh-cn](https://github.com/python/python-docs-zh-cn)（均为 PSF License），
本仓库只做构建与排版，不改变原文授权。构建依赖 Sphinx、python-docs-theme、TeX Live、poppler。
