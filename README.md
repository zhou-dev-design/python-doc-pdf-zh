# python-doc-pdf-zh

把 **CPython 官方文档** 与 **python-docs-zh-cn 中文译文** 编译成中文分册 PDF 的仓库。
**平时不需要你做什么**：GitHub Actions 每天北京时间 12:00 自动构建，产物发布到 **Releases**。

| | |
|-|-|
| 触发器 | 每天 `cron "0 4 * * *"`（UTC）= 北京时间 **12:00**；也可手动 Run workflow |
| 产物 | 3.13 → 37 册 / 3.14 → 38 册 / 3.15 → 39 册 PDF + 合并本 + 验收报告 |
| 落点 | **Releases**，tag = `v<完整版本>`（例如 `v3.15.2`），同版本重跑原地更新 |
| 入口 | 一个脚本：`ci/linux/pdf_builder_linux.py` |
| 运行环境 | `ubuntu-22.04`，TeX Live + 中文字体由 workflow 现装 |

> 想要图形界面、要在本地 Windows 上跑，见 [`sphinx-pdf/gui/README.md`](sphinx-pdf/gui/README.md)。
> 本文只讲**这个 GitHub 仓库怎么用**。

---

## 一、它每天做什么

```
GitHub Actions（03:00 UTC → 北京 12:00）
        │
   ┌────▼─────┐   prepare 读 versions → 拆成 matrix
   │ prepare  │   （默认 3.13,3.14,3.15 三个 job 并行）
   └────┬─────┘
        │  matrix: build ×3
   ┌────▼──────────────────────────────────────────────┐
   │ 1 装 TeX Live / poppler / 中文字体 / cairo         │
   │ 2 装该版本 Python（actions/setup-python）          │
   │ 3 --preflight  体检（缺工具立刻失败，不浪费 30 分钟）│
   │ 4 selftest.py  入口脚本自检（不需要联网）            │
   │ 5 构建：ci/linux/pdf_builder_linux.py --versions X  │
   │ 6 上传 artifact（保留 7 天）                        │
   │ 7 发布到 Releases（含 RAR 包；旧补丁版归档到 old）    │
   └────────────────────────────────────────────────────┘
```

三个版本**互不影响**（`fail-fast: false`）：3.15 失败不会拦住 3.13 出稿。

---

## 二、唯一入口：`ci/linux/pdf_builder_linux.py`

它**不复制**构建逻辑，只是把项目里那份实现（`sphinx-pdf/gui/pdf_builder_multi.py`）当库导入，
再覆盖 3 个平台相关的方法（locale、`python` 命令别名、venv 就绪后重建 PATH）。
所以「同一件事两份实现」的风险仍然为零。

```bash
# 最常用：构建一个版本，全套（含合并册）
python3 ci/linux/pdf_builder_linux.py --versions 3.15 --jobs 4

# 三版本并行（每个版本一个子进程）
python3 ci/linux/pdf_builder_linux.py --versions 3.13,3.14,3.15 --jobs 4 --merge

# 只重跑后半段（前面产物已在）
python3 ci/linux/pdf_builder_linux.py --versions 3.15 --only 6,6b,7,7b,8,9

# 不动真格：只看环境能不能跑 / 只看解析出来的配置
python3 ci/linux/pdf_builder_linux.py --preflight --versions 3.15
python3 ci/linux/pdf_builder_linux.py --versions 3.15 --print-config
```

| 参数 | 说明 |
|-|-|
| `--versions` | 逗号分隔；多版本时内部按版本各起一个子进程 |
| `--jobs` | **同时**是步骤 6 的 sphinx `-j` 与步骤 7 的册级并发（Ubuntu runner 4 核，默认 4） |
| `--source` | `github`（默认）= 只从 github.com 直连抓源码与译文，**不碰镜像站**；`auto` = 镜像回退（国内本地用） |
| `--pip-index` | 默认 `https://pypi.org/simple` |
| `--python-map 3.13=/path` | 指定版本用哪个解释器；**PDF 里的完整版本号取自解释器** |
| `--only` / `--from` | 复用项目的步骤号解析（`--only 7` = 编译 PDF） |
| `--clean` | 步骤 10 清理范围，CI 默认 `none`（留日志给验收报告） |
| `--merge` / `--no-merge` | 是否生成合并本（默认生成） |

**产物目录**：`<base>/Python <完整版本> PDF 文档 <YYYYMMDD>/`
**合并本**：同目录下 `Python <完整版本> 文档 <YYYYMMDD>.pdf`

---

## 三、workflow 怎么配的

`.github/workflows/build-pdf-linux.yml`

| 项 | 值 | 为什么 |
|-|-|-|
| `on.schedule` | `0 4 * * *` | GitHub cron 一律按 **UTC**，减 8 小时才是北京 12:00 |
| `on.workflow_dispatch` | 5 个输入 | `versions` / `jobs` / `merge` / `clean` / `push_branch` |
| `runs-on` | `ubuntu-22.04` | 需要系统 TeX Live；Ubuntu 上 sphinx 的 `-j` 才真正生效 |
| `permissions` | `contents: write` | 要建 Release、上传附件、维护 `old` 分支 |
| `concurrency` | `build-pdf-linux-<ref>` | 上一轮没跑完时排队，不并行堆叠 |
| `timeout-minutes` | 360 | 三个 job 各自计时 |

**手动触发时**（手机也行）：
`Actions → 构建 Python 中文文档 PDF（Linux）→ Run workflow → versions 填 3.15 → Run`

> 定时触发下 `github.event.inputs.*` 全是空串，所以 workflow 里所有输入都写了兜底
> （`|| '4'`、`|| 'none'`、`!= 'false'`）。这不是洁癖：漏一处就会「每天跑完但不发布」。

---

## 四、产物：Releases 模型

```
Releases
├── v3.15.2    39 册 + 合并册 + 报告 + RAR   ← 同版本重跑原地更新
├── v3.14.10   38 册 + …
└── v3.13.18   37 册 + …
old 分支        ← 被新补丁版顶下来的旧版本，按 tag 建目录存档
```

| 情况 | 结果 |
|-|-|
| 3.15.2 连跑两天 | `v3.15.2` 这个 release **原地更新**（附件 `--clobber` 覆盖），不会多出来一个 |
| 3.15.2 → 3.15.3 | 先把 `v3.15.2` 的全部附件搬进 `old` 分支，**推成功之后**才删它的 release ⇒ 每条线永远只有一个 release |
| 跑一年 | Releases 数量 = 版本线条数（3 个），体积不随天数增长 |

几个要点：

- **tag 不带日期**：`v<完整版本>`（如 `v3.15.2`）。日期写在 release 标题
  「Python 3.15.2 文档（20261102）」、正文和压缩包名里 —— 既带日期，
  又不会一天一个 release。
- **附件命名必须是 ASCII**：GitHub 的 release 附件名只接受 ASCII，中文与空格会被
  服务端换成 `.`（`01Python 3.15 有什么新变化.pdf` → `01Python.3.15.pdf`，
  `验收报告.md` → `default.md`）。所以单个附件统一用 **`册号-英文标识.pdf`**：

  ```
  00-Python-3.15.2-docs-20261102.pdf   合并册
  01-whatsnew.pdf  …  08-installing.pdf
  0901-asyncio.pdf … 0929-abi3t-migration.pdf
  10-faq.pdf  11-builtins.pdf          REPORT.md
  ```

  映射表在 `ci/linux/asset-names.tsv`（由主程序 `name_map` 生成）。
  **中文文件名保留在压缩包内部**——压缩包是二进制，包内名不受此限。
- **附件**：40 个 PDF（39 分册 + 合并册）+ `REPORT.md` + `Python-3.15.2-docs-20261102.rar`
  （包内是中文原名，约 50 MB）。
- **先清后传**：每次发布前先删掉"不在本轮名单里"的旧附件，再统一上传。
  顺序不能反 —— 先传后清那版把刚传上去的 41 个附件全删了（拿中文名去比对
  ASCII 化的服务端名，一个都匹配不上）。
- **下载**：进 Releases → 选版本 → 要单册就点文件名；要一次全拿走就下压缩包。
- **`old` 分支只存历史**：`old/v3.15.2/...`。它不会自动瘦身，嫌大可以手动删目录。
- RAR 由 Ubuntu multiverse 里的 `rar`（RARLAB 免费 CLI）生成，压缩包注释里会有一行
  `evaluation copy`，不影响解压；装不上时会退回 `zip`，两者都失败才只发单个 PDF。

---

## 五、首次配置（只需一次）

```bash
git clone git@github.com:<你>/python-doc-pdf-zh.git
cd python-doc-pdf-zh
# main 已在，什么都不用改；要改构建参数就编辑 workflow 的 defaults 或手动触发的输入
```

想加/减版本，改一处即可：workflow 里 `versions` 的默认值（Releases 会按版本自动多一个）。

如果所在网络打不开 `github.com`（常见：`api.github.com` 通、主站不通），
推送与授权都会失败，走 SSH 443 通道，步骤见 [`ci/linux/README.md`](ci/linux/README.md) 第 7 节。

---

## 六、常见问题（只讲 CI 侧）

<details>
<summary><b>某个版本红了，另外两个还绿，正常吗？</b></summary>

正常，这是刻意的（`fail-fast: false`）。每个版本独立 job，一个失败不影响别人，
失败的产物不会发布 —— 所以「有没有对应 Release」就是最干净的判据：

```bash
gh release list                   # 看到 v3.15.2 = 成功
```
</details>

<details>
<summary><b>job 跑了不到 1 分钟就红，构建根都没有</b></summary>

说明死在「构建」之前的步骤：装依赖 / 装 Python / 体检 / 自检。
workflow 里有一段「失败诊断」（`if: failure()`），会把 `pip.log`、`clone.log`、
`latex-build.log`、`gui-build.log` 的末 60 行直接打到日志里，先看它。

历史上真实踩过：`selftest.py` 把版本写死成 3.13，于是 3.15 的 job 必红
（`find_interpreter("3.13")` 会正确退回 3.15，断言就不成立了）。
</details>

<details>
<summary><b>Release 里的 PDF 是半成品 / 没有索引</b></summary>

看验收报告里的「每步耗时」：如果步骤 7 用时异常短，多半是 `makeindex` 没跑成。
另外「构建全绿」不等于「内容齐全」，可以用项目的检查工具复核：

```bash
python3 sphinx-pdf/gui/pdf_builder_multi.py --tool check-pdf-gaps <合并册.pdf>
```

判据是页面内容流字节数（正文页 15000~25000），不能用 `extract_text()`。
</details>

<details>
<summary><b>Actions 分钟数会不会不够</b></summary>

本仓库是**公开**仓库 ⇒ Actions 免费且不限分钟数。
若哪天改成私有：额度 2000 分钟/月，而 3 版本 × 约 30 分钟 × 每天 ≈ 2700，会超。
</details>

<details>
<summary><b>为什么不做 doctree 缓存来提速</b></summary>

`environment.pickle` 不会因为 `.po` 更新而失效。复用缓存会出现
「译文更新了、PDF 还是旧中文」的**静默失败** —— 正是这个项目最忌讳的失败类型。
所以 CI 每次从零读入；代价是每轮多几分钟，换来的是「产物一定对」。
</details>

---

## 七、已知限制

1. **按册拆成 39 个独立工程并不能更快**：工作量 61% 集中在「标准库」那一册，
   拆完墙钟下限仍是它自己的耗时（约 17~18 分钟）；按篇并行的 `-j` 才是对的切法。
2. **步骤 7 不会因为 Linux 而更快**：那是册级多进程，本来就吃满；受惠的只有步骤 6 的读入。
3. **跨册 `:ref:` 引用本来就是断的**（`LaTeX Warning: Reference ... undefined`），
   这是分册编译的固有限制。
4. **定时不是秒级准时**：GitHub 在高峰期可能延迟十几分钟到一小时。

---

## 八、许可与致谢

文档内容来自 [CPython](https://github.com/python/cpython) 与
[python-docs-zh-cn](https://github.com/python/python-docs-zh-cn)（均为 PSF License），
本仓库只做构建与排版，不改变原文授权。构建依赖 Sphinx、python-docs-theme、TeX Live、poppler。
