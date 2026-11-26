# python-doc-pdf-zh

把 **CPython 官方 reST 文档** 与 **python-docs-zh-cn 中文译文** 编译成**中文分册 PDF**，每天自动发布。

官方 2025-09 起停发文档 PDF（[讨论](https://discuss.python.org/t/101343)：用得少、构建吃算力），中文读者手里只剩 2025-10 的旧快照 —— **3.14.0 之后的所有修订与整个 3.15 都没有官方中文 PDF**。本项目沿用官方那套 Sphinx + LaTeX 流程（主题、字体、分册结构与官方 3.13 一致），接最新译文产出分册，再合成一册。

| | |
|-|-|
| 构建版本 | **3.11 / 3.12 / 3.13 / 3.14 / 3.15**（3.10 已于 2026-10-31 EOL） |
| 出稿 | **每天北京时间 14:50–19:00**，中位 16:03（近 19 次；63% 落在 15:30–16:30） |
| 单版本耗时 | **约 18 分钟**（近 19 次 10m18–23m42，不含排队） |
| 产物 | 每版本 **2 个附件**：合并册 PDF + 全部分册 RAR |
| 落点 | **[Releases](https://github.com/zhou-dev-design/python-doc-pdf-zh/releases)**，tag = `v<完整版本>`，同版本重跑原地更新 |
| 历史 | **`old` 分支**：EOL 版本与被补丁版顶下来的旧版，按 tag 存目录 |
| 入口 | CI `ci/linux/pdf_builder_linux.py`；本机 `sphinx-pdf/gui/pdf_builder_multi.py` |

纸张统一 **A4**（3.11 上游写成 `'a4'`，不是 LaTeX 纸张选项、会被静默忽略并按 Letter 排，构建时自动纠正）。

> 图形界面 [`sphinx-pdf/gui/README.md`](sphinx-pdf/gui/README.md) · 逐步操作 [`构建Python文档PDF-完整步骤.md`](构建Python文档PDF-完整步骤.md) · CI 细节 [`ci/linux/README.md`](ci/linux/README.md) · 更新日志 [`ci/changelogs/README.md`](ci/changelogs/README.md)

---

## 各版本现状与下载

<!-- BUILD-TABLE:BEGIN -->
| 版本 | 小版本号 | PDF 构建时间 | 译文最后更新 | 合并册 PDF | 全部分册包 |
|-|-|-|-|-|-|
| 3.10 | 3.10.22 | 2026-11-03 19:48 | 2026-10-19 14:32 | [PDF · 36.9 MB](https://github.com/zhou-dev-design/python-doc-pdf-zh/blob/old/v3.10.22/Python-3.10.22-docs-20261103.pdf?raw=true) | [RAR · 49.8 MB](https://github.com/zhou-dev-design/python-doc-pdf-zh/blob/old/v3.10.22/Python-3.10.22-docs-20261103.rar?raw=true) |
| 3.11 | 3.11.18 | 2026-11-26 16:57 | 2026-11-08 20:37 | [PDF · 38.6 MB](https://github.com/zhou-dev-design/python-doc-pdf-zh/releases/download/v3.11.18/Python-3.11.18-docs-20261126.pdf) | [RAR · 51.3 MB](https://github.com/zhou-dev-design/python-doc-pdf-zh/releases/download/v3.11.18/Python-3.11.18-docs-20261126.rar) |
| 3.12 | 3.12.16 | 2026-11-26 16:57 | 2026-11-08 12:45 | [PDF · 41.6 MB](https://github.com/zhou-dev-design/python-doc-pdf-zh/releases/download/v3.12.16/Python-3.12.16-docs-20261126.pdf) | [RAR · 56.4 MB](https://github.com/zhou-dev-design/python-doc-pdf-zh/releases/download/v3.12.16/Python-3.12.16-docs-20261126.rar) |
| 3.13 | 3.13.18 | 2026-11-26 16:57 | 2026-11-08 12:57 | [PDF · 47.2 MB](https://github.com/zhou-dev-design/python-doc-pdf-zh/releases/download/v3.13.18/Python-3.13.18-docs-20261126.pdf) | [RAR · 65.7 MB](https://github.com/zhou-dev-design/python-doc-pdf-zh/releases/download/v3.13.18/Python-3.13.18-docs-20261126.rar) |
| 3.14 | 3.14.10 | 2026-11-26 16:57 | 2026-11-26 08:40 | [PDF · 50.0 MB](https://github.com/zhou-dev-design/python-doc-pdf-zh/releases/download/v3.14.10/Python-3.14.10-docs-20261126.pdf) | [RAR · 69.3 MB](https://github.com/zhou-dev-design/python-doc-pdf-zh/releases/download/v3.14.10/Python-3.14.10-docs-20261126.rar) |
| 3.15 | 3.15.2 | 2026-11-26 16:57 | 2026-11-26 08:47 | [PDF · 52.2 MB](https://github.com/zhou-dev-design/python-doc-pdf-zh/releases/download/v3.15.2/Python-3.15.2-docs-20261126.pdf) | [RAR · 72.6 MB](https://github.com/zhou-dev-design/python-doc-pdf-zh/releases/download/v3.15.2/Python-3.15.2-docs-20261126.rar) |
<!-- BUILD-TABLE:END -->

表中时间均为**北京时间**。一个版本线一行、小版本号**就地覆盖**（3.15.2 → 3.15.3 改第二列，不多一行），旧补丁版进 `old`（3.10 已 EOL，附件也在那里、链接直接下）。**构建时间** = 拉取 `.po` 的时刻，**译文时间** = 译文分支最后一次提交。整张表由 CI 每天改写（手改会被覆盖）：本轮没构建成功的版本保留上一行（含直链）。

---

## 每天怎么跑

`prepare` 刷版本号缓存并拆 matrix → `build 3.11…3.15` 五版并行（`fail-fast: false`）、`changelogs` 出五本更新日志、`archive-eol` 归档 EOL release（幂等）。每个 build job：装 TeX / 字体 → 装该版本 Python → 体检 + 自检 → 构建 → 传 artifact（留 7 天）→ 发布（先清后传，核对恰好 2 个附件）。

**出稿**：计划 UTC 00:47，实际由 GitHub 排队决定（近 19 次排队 5h51–9h40、均值 6h55；出稿 14:52–18:51、中位 16:03），**别按分钟等**。00:47 已是最早能设的时刻 —— 再早，一旦延迟变小，构建目录名里的 UTC 日期就会比北京日期早一天。急用 → Actions → Run workflow（不走队列）。

## 产物模型

| 情况 | 结果 |
|-|-|
| 同一版本连跑两天 | 该 release **原地更新**（同名附件 `--clobber`），不会一天一个 |
| 3.15.2 → 3.15.3 | 旧附件先归档到 `old/v3.15.2/`，**推成功之后**才删旧 release ⇒ 每条线只有 1 个 |
| 版本 EOL | `archive-eol` 整条搬进 `old/`，再删 release 和 tag |
| 跑一年 | Releases 数量 = 版本线条数，体积不随天数增长 |

- **附件恰好 2 个**：合并册（单本）+ `.rar`（全部分册 + 合并册 + 验收报告）。单册不逐个挂 —— GitHub 附件名只接受 ASCII，中文会被换成点号，**要单册就解压**。
- **先清后传**：删掉不在本轮名单里的旧附件 → 上传 → 核对恰好 2 个；压缩包打不出来就报错、不发布。
- **版本号取官方文档站 h1**（中/英站取较新者），缓存在 `sphinx-pdf/version-titles.json`，每轮刷新并自动 commit。用解释器自报的版本会「内容新、文件名旧」，而且**零报错**。
- 三根分支：`main`（代码）、`ci-logs`（失败诊断证据）、`old`（历史产物），都不放 PDF。

## 更新日志（tag = `changelogs`）

每天另出「完整更新日志」，一个大版本一本，单独 release、单独 job：内容是该版本 `changelog.rst` 的中文译文 + `Misc/NEWS.d` 的补丁记录；3.11–3.15 每天重建，**3.9 / 3.10 已冻结**（随仓库带）。某版失败只保留上一版并告警。实现、失败语义、回退方法见 **[`ci/changelogs/README.md`](ci/changelogs/README.md)**。

## 每版几册（官方的，不是猜的）

真源是 `sphinx-pdf/volumes.json`（依据各分支 `Doc/conf.py` 的 `latex_documents` + `howto/*.rst`，`--tool volumes --verify` 可联网逐条核对）：

| 版本 | 静态册 | howto | 合计 | 差异 |
|-|-|-|-|-|
| 3.11 | 9 | 20 | **29** | `distributing` 被上游并进 `installing` |
| 3.12 | 9 | 23 | **32** | |
| 3.13 | 10 | 27 | **37** | 拆出《内置参考手册》 |
| 3.14 | 10 | 28 | **38** | 新增远程调试附加协议 |
| 3.15 | 10 | 29 | **39** | 新增 abi3t 迁移 |
| ~~3.10~~ | 10 | 17 | ~~27~~ | 已 EOL，产物在 `old` |

版本区间是**闭区间**（`distributing` 填 `max=3.10`、`builtins` 填 `min=3.13`），上游再删哪册只加一个 `max`。改法：界面「分册配置…」可视化编辑，或改 `volumes.json` 后 `--tool name-map --check` 自检。

## 本地怎么跑

三条路，**同一份实现**（`pdf_builder_multi.py`），不会出现两套逻辑。

| 场景 | 命令 |
|-|-|
| 图形界面（Windows） | `cd sphinx-pdf\gui` → `启动PDF构建器.bat`（多选版本、每版独立日志、可只重跑某几步） |
| 纯 bash 一键 | `cd sphinx-pdf && ./build-sphinx-pdf.sh`（步骤 0~10） |
| 与 CI 同款（Linux） | `python3 ci/linux/pdf_builder_linux.py --versions 3.15 --jobs 4 --merge` |

CI 脚本**不复制**构建逻辑，只把主程序当库导入、覆盖少量平台相关方法。常用参数：`--only/--from <步骤号>`、`--preflight` 只体检、`--source auto` 镜像回退（国内本地用，CI 门禁只用官网直连）。

## 目录结构

```
.github/workflows/build-pdf-linux.yml   # 唯一流水线
ci/linux/pdf_builder_linux.py           # CI 入口：导入主程序 + 覆盖平台差异
ci/linux/update_readme_table.py         # 把构建时间与下载直链写回 README 表格
ci/changelogs/                          # 更新日志（tag=changelogs），见其 README
sphinx-pdf/
  gui/pdf_builder_multi.py              # ★ 唯一主程序：步骤 0~10 + PyQt6 界面 + 17 个内置工具
  build-sphinx-pdf.sh                   # 纯 bash 一键（步骤 0~10）
  volumes.json / version-titles.json    # 分册真源 / 完整版本号缓存
构建Python文档PDF-完整步骤.md           # 逐步操作 + 故障排查表
```

## 常见问题

<details>
<summary><b>到点了却没看到新产物</b></summary>

先看 Actions 里有没有一条 `schedule` 运行：**有** → 还在排队或构建（见过晚 9 小时的）；**始终没有** → 被丢弃。两种情况都可以手动 Run workflow 补一次，产物与自动跑完全一样。
</details>

<details>
<summary><b>某个版本红了，其它还绿，正常吗？</b></summary>

正常，这是刻意的（`fail-fast: false`）：每版独立 job，失败的那版不发布。所以「有没有对应 Release」就是最干净的判据。
</details>

<details>
<summary><b>PDF 正文是英文，封面却是中文</b></summary>

最隐蔽的失败：**0 warning、页数书签全正常**。老版本（3.10/3.11）`conf.py` 缺 `gettext_compact = False`，Sphinx 按「每目录一份 .mo」找，而译文是每页一份 ⇒ 全不匹配。步骤 6 自动补这行，`step6b` 再兜底（整批汉字 < 2000 且过半册无中文就 `raise Fail`）。排查同类问题要拿**上一版同一册**逐条对照，别只看 translation progress。
</details>

<details>
<summary><b>Release 里的 PDF 是半成品 / 没有索引</b></summary>

「构建全绿」≠「内容齐全」。用 `--tool check-pdf-gaps <合并册.pdf>` 复核（判据是页面内容流字节数，不能用 `extract_text()` —— 这套 PDF 是字体子集 + 自定义编码）。步骤 7 异常短，多半 `makeindex` 没跑成。
</details>

## 已知限制

1. **按册拆成三四十个独立工程并不会更快**：约 61% 的工作量集中在「标准库」那一册，墙钟下限由它决定；按篇并行的 `-j` 才是对的切法。
2. **跨册 `:ref:` 引用本来就是断的**（`Reference ... undefined`），分册编译的固有限制；合并册里 9~12 处 `??` 属正常，不是回归。
3. **旧版本要用它自己的工具链**：3.11 是 Sphinx 7.2、3.12 是 8.2，≤3.12 一律读该分支的 `Doc/requirements.txt`，一刀切装最新版必失败。
4. **官方与本项目 CI 用同一套 TeX**：官方 PDF 的 Producer 是 `xdvipdfmx (20220710)`＝TL2023（戳里是编译日期，不是发行年），来自 PSF 规范机 Ubuntu 24.04 的 apt 包；本项目 CI 同样跑 24.04，引擎与字体同源。版式看 xdvipdfmx，不看 `xelatex --version` 自报的发行版标签。
5. **不做 doctree 缓存**：`environment.pickle` 不会因 `.po` 更新而失效，复用就会出现「译文更新了、PDF 还是旧中文」的静默失败。

---

<details>
<summary><b>附：官方 PDF（3.6 – 3.14，全部停在 2025-10，仅作版式参照）</b></summary>

3.15 没有官方 PDF；3.13 / 3.14 停在 2025-10-02，3.14 那份是 rc3 到 final 之间的快照（[PEP 745](https://peps.python.org/pep-0745/)）。**文件名里的版本号别信**：3.6~3.11 带补丁号但多数不是最后一版，以「包内实际版本」为准。

| 版本 | 中文版 A4 | 大小 | 出包日期 | TeX | 包内实际版本 | 官方最新 | 落后 |
|-|-|-|-|-|-|-|-|
| 3.6 | [3.6.15](https://docs.python.org/zh-cn/3.6/archives/python-3.6.15-docs-pdf-a4.zip) | 22.9 MB | 2021-09-06 | 2020 | 3.6.15 | 3.6.15 | — |
| 3.7 | [3.7.13](https://docs.python.org/zh-cn/3.7/archives/python-3.7.13-docs-pdf-a4.zip) | 23.6 MB | 2022-03-17 | 2020 | 3.7.13 | 3.7.17 | 4 版 |
| 3.8 | [3.8.20](https://docs.python.org/zh-cn/3.8/archives/python-3.8.20-docs-pdf-a4.zip) | 24.7 MB | 2024-12-10 | 2023 | 3.8.20 | 3.8.20 | — |
| 3.9 | [3.9.24](https://docs.python.org/zh-cn/3.9/archives/python-3.9.24-docs-pdf-a4.zip) | 25.4 MB | 2025-10-17 | 2023 | 3.9.24 | 3.9.25 | 1 版 |
| 3.10 | [3.10.19](https://docs.python.org/zh-cn/3.10/archives/python-3.10.19-docs-pdf-a4.zip) | 26.5 MB | 2025-10-16 | 2023 | 3.10.19 | 3.10.22 | 3 版 |
| 3.11 | [3.11.14](https://docs.python.org/zh-cn/3.11/archives/python-3.11.14-docs-pdf-a4.zip) | 27.1 MB | 2025-10-16 | 2023 | 3.11.14 | 3.11.18 | 4 版 |
| 3.12 | [3.12](https://docs.python.org/zh-cn/3.12/archives/python-3.12-docs-pdf-a4.zip) | 29.8 MB | 2025-09-30 | 2023 | 3.12.11 | 3.12.16 | 5 版 |
| 3.13 | [3.13](https://docs.python.org/zh-cn/3.13/archives/python-3.13-docs-pdf-a4.zip) | 32.9 MB | 2025-10-02 | 2023 | 3.13.7 | 3.13.18 | 11 版 |
| 3.14 | [3.14](https://docs.python.org/zh-cn/3.14/archives/python-3.14-docs-pdf-a4.zip) | 34.2 MB | 2025-10-02 | 2023 | 3.14.0rc3 | 3.14.10 | 11 版 |

出包日期取自 CDN 的 `Last-Modified`（UTC，表内已换算）；「TeX」= `Producer` 的引擎所属发行版：3.6/3.7 是 `XeTeX 0.99998`，3.8 起 276 册全是 `xdvipdfmx (20220710)` = TL2023。查补丁版号认英文站（去掉路径里的 `zh-cn/`）或 [endoflife.date](https://endoflife.date/python)。
</details>

## 许可与致谢

内容来自 [CPython](https://github.com/python/cpython) 与 [python-docs-zh-cn](https://github.com/python/python-docs-zh-cn)（均为 PSF License），本仓库只做构建与排版。构建：[Sphinx](https://www.sphinx-doc.org/) + [python-docs-theme](https://github.com/python/python-docs-theme) + [TeX Live](https://www.tug.org/texlive/)；验收：[poppler](https://poppler.freedesktop.org/)。
