# ci-logs —— 构建失败时的诊断证据

本分支**只在构建失败时**被写入，每次**整体覆盖**（CI 里是 `git init` +
`git push --force`），所以永远只有最近一次的诊断，不会越堆越大。
平时为空是正常的。这个分支不是代码，删掉不影响任何东西。

| 文件 | 内容 |
|-|-|
| `probe.txt` | 「🔬 显微镜」探针的完整输出 |
| `texlog-<册>.log` | 每册 LaTeX 日志的**尾部 40 KB** |
| `latexmk-pdf-build-<册>.log` | latexmk 自己的转录 —— **真话在这里** |
| `latex-build.log` / `gui-build.log` | 主程序日志尾部 300 KB |
| `tex-sample.txt` | 最小那册 .tex 的头 80 行 + 尾 40 行 |

读法：

```bash
git fetch origin ci-logs && git show origin/ci-logs:probe.txt
```
