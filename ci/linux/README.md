# Linux / WSL 构建入口

> 目标：把「读入 + 套译文」这一段从 **20~29 分钟压到 4~6 分钟**。
> 前提：`pdf_builder_multi.py` **一行都不改** —— 它仍是唯一实现。

## 1. 为什么 Linux 能快、Windows 不能

Sphinx 的并行是硬编码的 POSIX 专用：

```python
# sphinx/util/parallel.py
parallel_available = HAS_MULTIPROCESSING and os.name == 'posix'
...
context = multiprocessing.get_context('fork')      # Windows 没有 fork
```

实测（Windows 11 / 18 核 / 三版本并行，`-j 5`）：

| 指标 | 实测值 |
|-|-|
| 每个 sphinx 进程的线程数 | 1 |
| worker 子进程 | 0 |
| 15 秒内 CPU 时间 | 14.2 / 14.3 / 14.5 秒（≈ 0.95 核/进程） |
| 三版合计 | **2.87 / 18 核** |

也就是说 `-j 5` 在 Windows 上只是**安慰剂**，而这一步 99.5% 的时间花在读入
（写出 `.tex` 只要 16 秒）。所以：

| 环境 | 步骤 6（553 篇 + 9.3 万条译文） |
|-|-|
| Windows 单核 | 22~29 分钟 |
| Linux `-j 4` | 约 4~6 分钟（估算，按 4 进程线性折算） |

## 2. 本目录有什么

| 文件 | 作用 |
|-|-|
| `pdf_builder_linux.py` | Linux/WSL 入口：导入主程序，只覆盖 3 个平台胶水方法 |
| `selftest.py` | 逻辑自检，**任何系统都能跑**（用「临时把 IS_POSIX 置真」的办法验证 Linux 分支） |

覆盖清单只有三个方法，其余（步骤 1~10、39 册命名、索引修复、合并书签、验收报告）
全部复用原实现：

| 覆盖点 | 原因 |
|-|-|
| `_make_env()` | Linux 要**保留并钉死 UTF-8 locale**（Windows 那份是清掉 `LC_*`）；再把 TeX 的 `TEXMFVAR` 指到构建根（CI 的 `$HOME` 可能不可写） |
| `step0()` | Ubuntu 24.04 起系统只有 `python3`、没有 `python`，而步骤 7 的 latexmk 执行的是 `python makeindex-fix.py`。先在 `<根>/.pyshim/` 放个软链，再走原检查 |
| `step4()` | 父类的 `self.env` 是 `__init__` 时算的，那时 venv 还没建，PATH 里没有 `venv/bin` → 建完 venv 必须重建一次 |

## 3. 用法

```bash
# ① 体检（不联网、不建大目录）
python3 ci/linux/pdf_builder_linux.py --preflight --versions 3.13,3.14,3.15

# ② 物理自检（验证平台胶水层）
python3 ci/linux/selftest.py

# ③ 单版本全套
python3 ci/linux/pdf_builder_linux.py --versions 3.15 --jobs 4 --merge

# ④ 三版本并行（按版本各起一个子进程，共用 --jobs 个核）
python3 ci/linux/pdf_builder_linux.py --versions 3.13,3.14,3.15 --jobs 4 --merge

# ⑤ 只重跑后半段（前面产物已在）
python3 ci/linux/pdf_builder_linux.py --versions 3.15 --only 6,6b,7,7b,8,9

# ⑥ 想看解析后的配置
python3 ci/linux/pdf_builder_linux.py --versions 3.15 --print-config
```

产物仍在 `--base` 下的 `Python <完整版本> PDF 文档 <YYYYMMDD>/`，
命名规则来自主程序的 `name_map`，这里不另立一套。

### 关键参数

| 参数 | 说明 |
|-|-|
| `--jobs` | **同时**是步骤 6 的 sphinx `-j` 与步骤 7 的册级并发数（主程序就一个 `jobs` 字段） |
| `--python-map 3.13=/path` | 指定某版本用哪个解释器；不指定就找 `python3.13`。**完整版本号（3.13.18）取自解释器**，找不到会退成 `3.13.0` |
| `--gh` | 留空 = 内置 7 个镜像自动回退（国内）；CI 建议填 `https://github.com` 直连，省掉 6 次超时 |
| `--only` / `--from` | 复用主程序的步骤号解析（`--only 7` = 编译 PDF = 行 8） |
| `--clean` | 步骤 10 的清理范围，默认 `none`（留着日志，验收报告的「每步耗时」才有数据） |

## 4. 系统依赖（Ubuntu / Debian）

```bash
sudo apt-get install -y \
  git curl ca-certificates \
  latexmk texlive-xetex texlive-latex-extra texlive-binaries \
  texlive-lang-chinese fonts-noto-cjk \
  poppler-utils libcairo2
```

- `texlive-lang-chinese` + `fonts-noto-cjk`：中文排版（xelatex 的字体）
- `poppler-utils`：`pdfinfo` / `pdffonts`（步骤 7b/8 的核对要用）
- `libcairo2`：3.14 / 3.15 的 `.svg` 插图（cairosvg）

需要 3.13/3.14/3.15 三个解释器中的一个（Sphinx 用哪个版本编都行，
但**完整版本号是由该版本解释器报出来的**）。

## 5. CI

`.github/workflows/build-pdf-linux.yml`（**新增**，与 `build-pdf.yml` 互不影响）：

- 手动触发，`versions` 拆成 matrix，每个版本一个 job（Ubuntu 上 4 核/job）；
- 每步：装依赖 → `--preflight` → `selftest.py` → 构建 → 上传 artifact → 推 `v<完整版本>` 分支；
- 分支仍是「孤儿提交 + 强推」，只留最新日期；不同补丁版各占一个分支。

⚠️ 定时触发默认是注释掉的：两条流水线同日跑会重复构建。验证通过后
把 `build-pdf-linux.yml` 的 `schedule` 打开、并把 `build-pdf.yml` 的关掉。

托管 runner 装 TeX Live 约 3~5 分钟，整轮单版本大约 25~35 分钟；
自托管 Linux（`runs-on: [self-hosted, linux]`）可以省掉装依赖那一段。

## 6. 已知限制

1. **没有 doctree 缓存**：`environment.pickle` 不会因为 `.po` 更新而失效，
   复用 doctree 会出现「译文更新了、PDF 还是旧中文」的**静默失败**。
   所以 CI 每次都是从零读入（好在 Linux 上这一步只要几分钟）。
2. **`--root` 只能配单版本**：多版本必须各占一个目录，否则互相覆盖（已拦）。
3. **`python` 别名只影响本程序的子进程**（`<根>/.pyshim/`），不动系统。
4. 判据仍只看 ASCII 标记（`MISSING n` / `UNPRODUCED n` / `OK`），别匹配中文。
