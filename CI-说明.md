# 用 GitHub Actions 每天自动构建

## 一、分支模型：一个小版本一个分支，只留最新一次

```
main        ← 只有代码 + 这个 workflow（干净，不放 PDF）
v3.13.18    ← Python 3.13.18 的成品（永远是**最新那一天**的）
v3.14.10    ← Python 3.14.10 的成品
v3.15.2     ← Python 3.15.2 的成品
```

- 分支名 = `v` + **完整版本号**（`3.13.18`，不是 `3.13`），版本号由那个版本的
  解释器自己报（`sys.version_info`），不写死。
- 每次构建用 **孤儿提交 + 强推**（`git init` 一个临时仓库 → commit → `push --force`），
  所以：

  | 情况 | 结果 |
  |---|---|
  | 3.13.18 在 20261010 和 20261011 都跑过 | `v3.13.18` 分支里**只有 20261011 的产物**，旧的自动消失 |
  | 3.14.2 和 3.14.3 都跑过 | `v3.14.2`、`v3.14.3` **两个分支都在**，各自留最新日期 |

- 仓库体积 ≈ 版本数 × 单版本体积（~85 MB），不会随天数增长。

## 二、为什么必须是自托管 runner

| | 自托管 Windows（这台机器） | GitHub 托管 ubuntu | GitHub 托管 windows |
|---|---|---|---|
| 代码改动 | **0**（`CREATE_NO_WINDOW`、`taskkill /T`、`latexmk.exe`、Perl/GBK 补丁都是 Windows 专用） | 要移植 ~10 处 | 同左 + 缺 Python 3.14/3.15 |
| TeX Live 2025 | 现成（F:） | 要装（2~7 GB） | 要装 |
| 步骤 6（读入 553 篇） | 单核 **14~23 分钟**（Sphinx 在 Windows 上 `-j` 是空实现） | `-j 4` **生效 → 4~6 分钟** | 同 Windows（还是单核） |
| 步骤 7（39 册 xelatex） | 5 册并发 ≈ 9~10 分钟 | 3~4 册并发 ≈ 10~12 分钟 | 同左 |
| 单版本合计 | 25~35 分钟 | **18~22 分钟** | 25~35 分钟 |
| 三版本一起 | 同机并行，≈ 30~35 分钟 | 3 个 job 各自 4 核并行，≈ 20 分钟 | ≈ 30~35 分钟 |
| 计费 | **不消耗 Actions 分钟** | 公开仓库免费；私有 2000 分钟/月（3×20 分钟/天 ≈ 1800，勉强够） | 私有按 **2 倍**计费 → 会超 |
| 前置条件 | 那个时间点机器要开着 | 无 | 无 |

**结论**：想让步骤 6 吃到多核，只有 POSIX 环境能做到（Windows 上
`sphinx/util/parallel.py` 里 `parallel_available = HAS_MULTIPROCESSING and os.name == 'posix'`，
且 `ParallelTasks` 写死 `get_context('fork')`）。托管 ubuntu 确实能快 30% 左右，
但代价是先把 Windows 专用代码移植过去——那是另一个任务，不是加个 `runs-on` 就行。

所以现在这份 workflow 走 **self-hosted Windows**：零移植、零分钟数、可信。

## 三、一次性配置（按顺序做一遍）

### 1. 建仓库

在 GitHub 上新建一个仓库（建议 **私有**，名字随意，例如 `python-docs-zh-pdf`），
**不要**勾 README / .gitignore / license。

### 2. 把本地代码推上去

在本目录（`python-3.14-docs-texinfo`）里：

```bash
git init -b main
git add -A
git commit -m "init: 构建器 + GitHub Actions"
git remote add origin https://github.com/<你的账号>/python-docs-zh-pdf.git
git push -u origin main          # 首次会弹一次浏览器授权（Git Credential Manager）
```

`.gitignore` 已经把 `gui/dist/`、`sphinx-pdf/pdf/`、`__pycache__`、调试日志排除，
所以推上去只有源码（~2 MB），不含 74 MB 的 exe 和 79 MB 的成品快照。

### 3. 在这台机器上装 self-hosted runner

仓库 → Settings → Actions → Runners → **New self-hosted runner** → Windows x64，
照着页面上的命令做（大致是）：

```powershell
mkdir C:\actions-runner; cd C:\actions-runner
# 下载并解压 actions-runner-win-x64-*.zip（页面给了链接）
./config.cmd --url https://github.com/<账号>/<仓库> --token <页面给的 token>
./run.cmd            # 前台试跑；能看到 "Listening for Jobs" 就成了
```

想让它开机自启、后台常驻：

```powershell
./svc.sh install     # 或在 Windows 上用 `./config.cmd --runasservice`
./svc.sh start
```

标签用默认的 `self-hosted, Windows, X64` 即可（workflow 就按这三个标签找人）。

### 4. 手动跑一次验证

仓库 → Actions → 「构建 Python 中文文档 PDF」→ **Run workflow**
（`versions` 可填 `3.15` 先只跑一个，`fresh` 填 `true` 做一次从零构建）。

跑完检查：仓库的 Branches 里应该出现 `v3.15.2`，点进去只有一个提交、一个 `pdf/` 目录。

## 四、日常

- **定时**：`cron: "0 19 * * *"`（UTC）= 北京时间**每天 03:00**。
  改时间就改这一行（cron 用 UTC，北京时间减 8 小时）。
- **手动**：Actions 页面 → Run workflow。
- **只跑某个版本**：`versions` 填 `3.13`。
- **某天想从零重建**：`fresh` 填 `true`（否则会复用 `%RUNNER_TEMP%\pdf-<版本>`
  里已克隆的源码和 venv，省 3~5 分钟）。

## 五、已知限制

1. **一台 runner 同时只跑一个 job**，所以 workflow 用「一个 job 里三个进程并行」
   而不是 matrix——这样才吃得满 18 核。
2. 构建根留在 `%RUNNER_TEMP%\pdf-<版本>`，跨天复用。想彻底清就 `fresh=true`。
3. 若某版本构建失败：**成功的照常推分支**，失败的版本不推、job 最后标红，
   你原来的成品不会被破坏。
4. `python` 必须在 runner 的 PATH 里且 ≥3.10（脚本只用标准库）；
   workflow 第一步会自检，5 秒内报错而不是等 40 分钟。
