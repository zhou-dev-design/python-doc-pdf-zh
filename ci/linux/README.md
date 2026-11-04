# Linux / WSL 构建入口

主程序（`sphinx-pdf/gui/pdf_builder_multi.py`）是按 Windows 写的：清 locale、
`python`/`python3` 别名、venv 目录布局、控制台窗口这些假设在 Linux 上都不成立。
本目录只**替换掉这几处**，其余（步骤 0~10、分册命名、索引修复、合并书签、
验收报告）全部复用原实现 —— **主程序一行不改**。

顺带一个事实：Sphinx 的 `-j` 并行只对 POSIX 生效（内部是
`os.name == 'posix'` + `fork`），Windows 上 `-j 5` 是安慰剂。所以把构建放到
Linux 上跑，步骤 6 才能真的按核数提速。

---

## 1. 覆盖了哪些地方

| 覆盖点 | 原因 |
|-|-|
| `_make_env()` | Linux 要**保留并钉死 UTF-8 locale**（Windows 那份是清掉 `LC_*`）；再把 `TEXMFVAR` 指到构建根（CI 的 `$HOME` 可能不可写） |
| `step0()` | Ubuntu 24.04 起系统只有 `python3`，而步骤 7 的 latexmk 执行的是 `python makeindex-fix.py` → 先在 `<根>/.pyshim/` 放个软链，再走原检查 |
| `step4()` / `need_venv()` | 父类的 `self.env` 在 `__init__` 时算好，那时 venv 还没建，PATH 里没有 `venv/bin` → 建完必须重建一次 |
| `step4()` 里的 site-packages 登记 | POSIX 的 venv 是 `venv/lib/python3.x/site-packages`，不是 Windows 的 `venv/Lib/site-packages`。登记错目录会让 `report` / `merge-pdf` 报「没有 pypdf」 |
| `step8()` / `step9()` | 这两个入口不经过 `need_venv()`，得各自再登记一次 |
| `_emit_makeindex_fix()` | 它生成的脚本写死 `CREATE_NO_WINDOW = 0x08000000`，而 `subprocess(creationflags=…)` 在 POSIX 上直接抛 `ValueError` → latexmk 在 makeindex 规则处中止，**每册只留第一遍**（目录空白、满屏 `??`、无索引），而 `<册>.log` 里一条错误都没有 |

这三处平台差异的共同点：**按 Windows 的形状写死**。凡是「路径拼成 `Lib/`」
「常量只在一个平台存在」「可执行文件叫 `python`」，换平台就静默失效。

## 2. 本目录有什么

| 文件 | 作用 |
|-|-|
| `pdf_builder_linux.py` | Linux / WSL 入口：导入主程序，只覆盖上面那几处 |
| `selftest.py` | 逻辑自检，**任何系统都能跑**（用「临时把 `IS_POSIX` 置真」的办法验证 Linux 分支） |
| `update_readme_table.py` | summary job 用：把各版本的构建/译文时间写回 README 的表格 |

## 3. 用法

```bash
# ① 体检（不联网、不建大目录）
python3 ci/linux/pdf_builder_linux.py --preflight --versions 3.11,3.12,3.13,3.14,3.15

# ② 逻辑自检（验证平台胶水层）
python3 ci/linux/selftest.py

# ③ 单版本全套
python3 ci/linux/pdf_builder_linux.py --versions 3.15 --jobs 4 --merge

# ④ 多版本并行（按版本各起一个子进程，共用 --jobs 个核）
python3 ci/linux/pdf_builder_linux.py --versions 3.11,3.12,3.13,3.14,3.15 --jobs 4 --merge

# ⑤ 只重跑后半段（前面的产物已在）
python3 ci/linux/pdf_builder_linux.py --versions 3.15 --only 6,6b,7,7b,8,9

# ⑥ 看解析后的配置
python3 ci/linux/pdf_builder_linux.py --versions 3.15 --print-config
```

产物仍在 `--base` 下的 `Python <完整版本> PDF 文档 <YYYYMMDD>/`，
命名规则来自主程序的 `name_map`，这里不另立一套。

### 关键参数

| 参数 | 说明 |
|-|-|
| `--jobs` | **同时**是步骤 6 的 sphinx `-j` 与步骤 7 的册级并发数（主程序只有一个 `jobs` 字段） |
| `--python-map 3.13=/path` | 指定某版本用哪个解释器；不指定就找 `python3.13` |
| `--source` | `github`（默认）= 只从 github.com 直连抓源码与译文；`auto` = 主程序那套镜像自动回退（本地直连不通时才用） |
| `--pip-index` | 默认 `https://pypi.org/simple`；本地可传镜像加速 |
| `--only` / `--from` | 复用主程序的步骤号解析（`--only 7` = 编译 PDF = 行 8） |
| `--clean` | 步骤 10 的清理范围，默认 `none`（留着日志，验收报告的「每步耗时」才有数据） |

> 为什么默认直连：这套流程跑在 GitHub 的 runner 上，到 `github.com` 走机房内网，
> 比任何第三方加速镜像都快，而且内容最可信（镜像可能滞后）。镜像回退是给
> 本地机器准备的，不是给 CI 的。

## 4. 系统依赖（Ubuntu / Debian）

```bash
sudo apt-get install -y \
  git curl ca-certificates \
  latexmk texlive-xetex texlive-latex-extra texlive-binaries \
  texlive-lang-chinese fonts-noto-cjk \
  poppler-utils libcairo2
```

- `texlive-lang-chinese` + `fonts-noto-cjk`：中文排版（xelatex 的字体）
- `poppler-utils`：`pdfinfo` / `pdffonts`（步骤 7b/8 核对要用）
- `libcairo2`：3.13 起 Doc 里的 `.svg` 插图（cairosvg）

需要 3.11 ~ 3.15 任意一个版本的解释器（Sphinx 用哪个版本编都行）。

**完整版本号不靠解释器**：口径是官方文档站标题（`docs.python.org/zh-cn/3.13/` 的 h1
= `Python 3.13.18 文档`），存在 `sphinx-pdf/version-titles.json`，由
`--tool titles --write` 生成；解释器只在没有缓存时兜底。
各版本册数不同（3.11 29 册 … 3.15 39 册），真源是 `sphinx-pdf/volumes.json`。

## 5. CI

`.github/workflows/build-pdf-linux.yml`（仓库里**唯一**的流水线）：

- **每天 UTC 19:47（北京时间次日 03:47）自动跑**，实测约北京 11:35 出稿（延迟稳定在 7h48m 左右），也可在 Actions 页面手动触发。
  取 03:47 而不是整点 04:00：整点是 cron 洪峰，GitHub 高负载时 scheduled run
  会被延迟甚至**丢弃**；
- `versions` 拆成 matrix，**五个版本同时起跑**（`max-parallel: 5`，每版一个独立 runner）；
- 每步：装依赖 → `--preflight` → `selftest.py` → 构建 → 上传 artifact → 发布到 Releases；
- 托管 runner 装 TeX Live 约 3~5 分钟，单版本整轮约 25~35 分钟。

### 5.1 落点：产物进 Releases，分支只留三根

```
main      ← 代码 + 文档（唯一开发线）
ci-logs   ← 只在构建失败时被强推一次，存「显微镜」证据；永远 1 个提交
old       ← EOL 版本 / 被新补丁版顶下来的旧版，按 tag 建目录归档
```

tag = `v<完整版本>`（不带日期），于是：

| 情况 | 结果 |
|-|-|
| 3.15.2 连跑两天 | `v3.15.2` **原地更新**，不会多出一个 |
| 3.15.2 → 3.15.3 | 旧附件搬进 `old/v3.15.2/`，**推成功之后**才删旧 release ⇒ 每条线只有 1 个 release |
| 跑一年 | 分支数恒定 3 根，仓库体积**不随天数增长** |

**Release 附件固定 2 个**：合并册 `Python-<完整版本>-docs-<日期>.pdf` +
全部分册的压缩包（包内是中文原名 + 验收报告）。

单册不单独挂：GitHub 附件名只接受 ASCII，中文会被服务端换成 `.`，挂上去反而认不出
是哪一册。发布步骤会核对「**恰好 2 个**」—— 少一个报错，多一个（旧分册没清干净）也报错。

> 页面底部的 `Source code (zip/tar.gz)` 是 GitHub 按 tag 自动生成的仓库源码归档，
> 不是本项目的附件，**删不掉**，与本项目产物无关。

### 5.2 首次配置

```bash
# 1) GitHub 上新建空仓库（公开仓库的 Actions 分钟数不限）
# 2) 推送
git remote add origin <你的仓库地址>
git push -u origin main
# 3) Actions 页 → Run workflow → versions 先填一个版本试跑
```

成功的标志：Releases 里出现 `v<完整版本>`，附件**恰好 2 个**；
Branches 里**不该**多出任何 `v*` 分支。

## 6. 已知限制

1. **没有 doctree 缓存**：`environment.pickle` 不会因为 `.po` 更新而失效，
   复用 doctree 会出现「译文更新了、PDF 还是旧中文」的**静默失败**。
   所以 CI 每次从零读入（好在 Linux 上这一步只要几分钟）。
2. **`--root` 只能配单版本**：多版本必须各占一个目录，否则互相覆盖（已拦）。
3. **`python` 别名只影响本程序的子进程**（`<根>/.pyshim/`），不动系统。
4. 判据仍只看 ASCII 标记（`MISSING n` / `UNPRODUCED n` / `OK`），别匹配中文 ——
   非 UTF-8 locale 下中文匹配会静默失配。
