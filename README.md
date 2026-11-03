# ci-logs —— 构建失败时的诊断证据

这个分支**不是代码**，只为一件事存在：让「CI 失败时的日志」能被**不登录的人**读到。
公开仓库的 Actions 日志同样要 token 才能下载，而 `raw.githubusercontent.com` 谁都能读。

## 它什么时候有内容

- **平时是空的**：只有构建**失败**时才会被写入。
- **每次失败都整体覆盖**（不追加）：CI 里是 `git init` + `git push --force HEAD:ci-logs`，
  所以这里永远只有**最近一次**失败的证据，不会越堆越大。
- 构建成功时它不会被碰。

## 里面有什么

| 文件 | 内容 |
|-|-|
| `probe.txt` | 「🔬 显微镜」探针的完整输出（.tex 体积、每册行数/页数、xelatex 与 latexmk 原话） |
| `texlog-<册>.log` | 每册 LaTeX 日志的**尾部 40 KB**（完整日志动辄几 MB） |
| `latexmk-pdf-build-<册>.log` | latexmk 自己的转录 —— **真话在这里**，不在 `<册>.log` 里 |
| `latex-build.log` / `gui-build.log` | 主程序日志的尾部 300 KB |
| `tex-sample.txt` | 最小那册 `.tex` 的头 80 行 + 尾 40 行（判断是"只写了壳"还是"编译挂了"） |

## 怎么读

```bash
git fetch origin ci-logs
git show origin/ci-logs:probe.txt
```

或者不克隆：

```bash
curl -s https://raw.githubusercontent.com/<owner>/<repo>/ci-logs/probe.txt
```

## 历史

- 2026-11-02：`run 41464434557`（3.15 那次的 makeindex 崩）留下 82 个文件。
- 2026-11-03：**手动清空**，只留这份说明。分支保留 —— 它是排错时唯一的免登录通道。
