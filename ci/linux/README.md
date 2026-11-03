# Linux / WSL 构建入口

> 目标：把「读入 + 套译文」这一段从 **20~29 分钟压到 4~8 分钟**（取决于 `--jobs`）。
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
（写出 `.tex` 只要 16 秒）。

| 环境 | 步骤 6（553 篇 + 9.3 万条译文） |
|-|-|
| Windows 单核（现状） | **22~29 分钟**（3.15 实测 27m17s） |
| Linux `-j 2` | 15~17 分钟 |
| Linux `-j 4` | 7.5~8.5 分钟 |
| Linux `-j 6` | 5.0~5.6 分钟 |
| Linux `-j 8` | 3.7~4.2 分钟 |

算法（可复核）：3.15 那轮读入 1637 秒 × 0.95 核 ≈ **1555 核·秒**；除以 worker 数
得理想墙钟，再乘 1.15~1.3 的 fork + doctree 回传开销。

⚠️ 这是**推算，不是 Linux 实测量**。本机 `wsl.exe` 被安全策略禁用、也没有 docker，
所以这里给的是「代码级事实（Windows 上 `-j` 必然无效）+ 实测 CPU 用量」的换算。
真值最省事的确认办法：在 Actions 里跑一次，验收报告的「每步耗时」会直接打出
`读入 Xm Ys（553 篇，-j 4，约 N 篇/分）`，那一段就是答案。

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
python3 ci/linux/pdf_builder_linux.py --preflight --versions 3.11,3.12,3.13,3.14,3.15

# ② 物理自检（验证平台胶水层）
python3 ci/linux/selftest.py

# ③ 单版本全套
python3 ci/linux/pdf_builder_linux.py --versions 3.15 --jobs 4 --merge

# ④ 六版本并行（按版本各起一个子进程，共用 --jobs 个核）
python3 ci/linux/pdf_builder_linux.py --versions 3.11,3.12,3.13,3.14,3.15 --jobs 4 --merge

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
| `--source` | `github`（默认）= **只从 github.com 直连**抓源码与译文，绝不落到镜像站；`auto` = 主程序那套 7 个镜像自动回退（国内本地直连不通时才用） |
| `--gh` | 只在 `--source auto` 下有意义；`github` 模式下固定走 `https://github.com` |
| `--pip-index` | 默认 `https://pypi.org/simple`（不用国内镜像）；本地如需加速可传清华源 |
| `--only` / `--from` | 复用主程序的步骤号解析（`--only 7` = 编译 PDF = 行 8） |
| `--clean` | 步骤 10 的清理范围，默认 `none`（留着日志，验收报告的「每步耗时」才有数据） |

### 3.1 取源：一律直连 GitHub，不用镜像站

这套流程跑在 GitHub 自己的 runner 上，到 `github.com` 走机房内网——比任何第三方
加速镜像都快，而且**内容最可信**（镜像可能滞后、极端情况下可能被篡改）。

所以 `--source github`（默认）会把主程序的 `GH_MIRRORS` 整张表**绕过**，
`git_urls()` 只返回一条 `https://github.com/...`：

| | `--source github`（CI 默认） | `--source auto`（国内本地） |
|-|-|-|
| 克隆 CPython / 译文 | 直连，一次成功 | 7 个镜像按序回退，每次失败等 300 s 看门狗 |
| pip | `https://pypi.org/simple` | 默认清华源 |
| 适用 | GitHub Actions / 境外机器 | 国内工作站（直连 github.com 不通时） |

实测依据：2026-11-02 在用户机器上 `github.com:443` 全 IP 超时，而 GitHub runner
是内网直连——所以「CI 里配镜像」纯属给自己加超时。


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

需要 3.11 ~ 3.15 任意一个版本的解释器（Sphinx 用哪个版本编都行）。
**完整版本号不靠解释器**：口径是官方文档站标题（`docs.python.org/zh-cn/3.13/` 的 h1
= `Python 3.13.18 文档`），存在 `sphinx-pdf/version-titles.json`，由
`sphinx-pdf/gui/pdf_builder_multi.py --tool titles --write` 生成；解释器只在没有缓存时兜底。
各版本册数不同（3.11 29 册 … 3.15 39 册），映射表见 `sphinx-pdf/volumes.json`。

## 5. CI

`.github/workflows/build-pdf-linux.yml`（仓库里**唯一**的流水线）：

- **每天 UTC 03:47（北京时间 11:47）自动跑**，也可在 Actions 页面手动触发；
  取 03:47 而不是整点 04:00：整点是 cron 洪峰，GitHub 官方说明高负载时
  scheduled run 会被延迟甚至**丢弃**（2026-11-03 的 12:00 那轮就这么没了）；
- `versions` 拆成 matrix，**六个版本同时起跑**（`max-parallel: 6`，每个 job 一个独立 runner）；
- 每步：装依赖 → `--preflight` → `selftest.py` → 构建 → 上传 artifact → **发布到 Releases**；
- 产物**不进分支**：一个版本一个 release，同版本重跑原地更新（附件 `--clobber`）。

```yaml
on:
  schedule:
    - cron: "47 3 * * *"        # UTC 03:47 = 北京时间 11:47（UTC+8）
  workflow_dispatch:            # 手动触发（可改 versions / jobs / merge / clean）
```

托管 runner 装 TeX Live 约 3~5 分钟，整轮单版本大约 25~35 分钟；
自托管 Linux（`runs-on: [self-hosted, linux]`）可以省掉装依赖那一段。

### 5.1 落点模型：产物进 Releases，分支只留三根

```
main      ← 代码 + 文档（唯一开发线）
ci-logs   ← 只在构建失败时被强推一次，存「显微镜」证据；永远 1 个提交
            平时只有一份说明 README（2026-11-03 清过历史诊断）
old       ← 补丁版被顶下来时，按 tag 建目录归档旧产物（首次升级才会出现）
```

产物落 **Releases**，tag = `v<完整版本>`（不带日期），于是：

| 情况 | 结果 |
|-|-|
| 3.15.2 连跑两天 | `v3.15.2` 这个 release **原地更新**，不会多出一个 |
| 3.15.2 → 3.15.3 | 旧 release 附件搬进 `old/v3.15.2/`，**推成功之后**才删旧 release ⇒ 每条线只有 1 个 release |
| 跑一年 | 分支数恒定 3 根，仓库体积**不随天数增长** |

> 2026-11-03 已删除历史上那批 `v3.13.18` / `v3.14.10` / `v3.15.2` **产物分支**
> （每个 80~90 MB 的孤儿提交，内容与 Releases 重复）。现在分支里不再有 PDF，
> 想看产物去 Releases。tag 仍保留 —— release 依附于 tag，与分支无关。

**Release 附件固定 2 个**：合并册 `Python-<完整版本>-docs-<日期>.pdf` +
全部分册的压缩包（包内是中文原名 + 验收报告）。单册不单独挂 —— GitHub 附件名
只接受 ASCII，中文会被服务端换成 `.`，挂上去反而认不出是哪一册。
发布步骤会核对「**恰好 2 个**」：少一个报错，多一个（旧分册没清干净）也报错。

### 5.2 首次配置（三步）

```bash
# 1) GitHub 上新建空仓库（私有/公开都行，别勾 README）
# 2) 本目录推送（首次会弹浏览器授权）
git remote add origin ssh://git@github.com/1721324295/python-doc-pdf-zh.git
git push -u origin main
# 3) Actions 页 → 构建 Python 中文文档 PDF（Linux）→ Run workflow
#    versions 先填 3.15 试一个
```

成功的标志：**Releases 里出现 `v3.15.2`**，附件**恰好 2 个** —— 合并册
`Python-3.15.2-docs-<日期>.pdf` 与 `Python-3.15.2-docs-<日期>.rar`（包内是 39 册的
中文原名 + 验收报告）；Branches 里**不该**多出任何 `v*` 分支。

✅ **本仓库是公开仓库** ⇒ Actions 分钟数不限（公开仓库免费、无额度上限），
每天六个版本也随便跑。

（若哪天改成私有：额度 2000 分钟/月、Ubuntu 按 1 倍计，而单版本约 30 分钟 ×
6 版本 × 每天 ≈ 5400 分钟/月，会超。那时三个选择：改回公开、改成每周跑、
或上自托管 runner。）


## 6. 已知限制

1. **没有 doctree 缓存**：`environment.pickle` 不会因为 `.po` 更新而失效，
   复用 doctree 会出现「译文更新了、PDF 还是旧中文」的**静默失败**。
   所以 CI 每次都是从零读入（好在 Linux 上这一步只要几分钟）。
2. **`--root` 只能配单版本**：多版本必须各占一个目录，否则互相覆盖（已拦）。
3. **`python` 别名只影响本程序的子进程**（`<根>/.pyshim/`），不动系统。
4. 判据仍只看 ASCII 标记（`MISSING n` / `UNPRODUCED n` / `OK`），别匹配中文。

## 7. `github.com` 打不开时怎么推代码

2026-11-02 在用户机器上实测（国内网络）：

| 端点 | 结果 |
|-|-|
| `https://github.com` | **TCP 443 全不通**（140.82.112.3 / .113.3 / .114.3 / 20.200.245.247 / 4.237.22.38 全超时） |
| `https://github.com/login/oauth/*` | 不通 → **WorkBuddy 的 GitHub 连接器必然授权失败**（跟账号设置无关） |
| `https://api.github.com` | 200，0.6 s ✔ |
| `https://codeload.github.com` | 301，1.0 s ✔ |
| `ssh.github.com:443` | SSH 握手成功 ✔ |

所以有一条**完全绕开 github.com 主站**的备用通道：

```powershell
# 1) 生成 SSH key（私钥留本机，不发给任何人）
ssh-keygen -t ed25519 -C "pdfbuild" -f $HOME/.ssh/id_ed25519 -N '""'

# 2) 在能上 github.com 的网络（手机热点即可）建一个 PAT：
#    Fine-grained → Contents: Read and write，Workflows: Read and write
#    （少了 Workflows 推不进 .github/workflows/）

# 3) 一条命令：建仓库 + 传公钥（都走 api.github.com）
#    + 写 ~/.ssh/config（github.com → ssh.github.com:443）+ push
$env:GH_TOKEN = "github_pat_xxx"
.\ci\linux\setup-github.ps1 -UploadKey -DryRun   # 先看计划，不动任何东西
.\ci\linux\setup-github.ps1 -UploadKey           # 真跑
```

`setup-github.ps1` 的约束：token **只从 `$env:GH_TOKEN` 读、只在内存里用**，
不写进 `.git/config`、不落盘；仓库已存在则跳过创建；公钥已注册则跳过上传；
`~/.ssh/config` 用 `# >>> pdfbuild` 标记包裹，重复跑不会叠加；
`-DryRun` 连 token 都不需要，只打印计划和连通性自查。

