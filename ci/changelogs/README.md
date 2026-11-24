# 更新日志（tag = `changelogs`）

每天随主流水线另出一套「Python 完整更新日志」，与文档册**完全解耦**：单独 job、单独 release（tag 固定 `changelogs`）、单独失败域 —— 更新日志挂了不影响五个版本出稿。

## 产物

```
changelogs    Python 完整更新日志（3.9–3.15，固定 7 个附件）
├── Python-3.9-changelog.pdf              冻结件，随仓库带（frozen/）
├── Python-3.10-changelog.pdf             同上
├── Python-3.11-changelog-20261124.pdf    每天重建，文件名带北京时间日期
└── … 3.12 / 3.13 / 3.14 / 3.15
```

- **内容** = 该版本 `Doc/whatsnew/changelog.rst` 中属于它的部分 + `Misc/NEWS.d` 里它的补丁记录（blurb 汇总）。
- **附件名用 ASCII**：GitHub 会把中文附件名换成点号，挂上去认不出是哪一版；中文原名在 PDF 标题里（`Python 3.11 完整更新日志`）。
- 每天同名附件原地替换、旧日期自动清掉 ⇒ 每版只有一本，release 不随天数膨胀。

## 流水线

| job | 干什么 |
|-|-|
| `changelogs`（matrix 3.11–3.15） | 每版一个 runner：装 TeX + 中文字体 → 跑 `builder.py` → 传 artifact |
| `changelogs-publish` | `needs: [changelogs]` + `always()`：取回全部 artifact，收口建/改 release |

**为什么发布要单独一个 job**：五个 job 并发写同一个 release 必然打架（附件互相覆盖、API 限流）。构建 job 只传 artifact，由一个 job 统一 `gh release upload --clobber`。

`changelogs-publish` 只有 checkout + download，**没有 build job 那串 apt 安装**，所以缺什么都要自己装：`poppler-utils`（说明里的页数靠 `pdfinfo`）。2026-11-24 首次真正跑到发布分支就栽在这里——`FileNotFoundError: pdfinfo`，连 release 都没建。现在显式装包，且 `sh()` 兜住 `FileNotFoundError`（返回 127、打 warning），读不到页数只显示 `—`，绝不会因此发布失败。

## builder.py

`builder.py` 是 whatsnew-studio 构建器的**逐字副本**，只为 CI 改了六处：

| 改动 | 为什么 |
|-|-|
| `WNS_PY` / `WNS_TEXBIN` 环境变量 | 原文件写死作者本机路径；CI 用当前解释器、TeX 走系统 PATH |
| 去掉 PyPI 镜像探测 | runner 在 GitHub 内网，raw 0.16s，不该绕第三方 |
| API 带 `GITHUB_TOKEN` | `api.github.com` 匿名额度 60 次/时，共享出口 IP 必然 403；带 token 5000 |
| `--mirror 直连` | 同上，只用官网 |
| 路径 `resolve()` | 起子进程带 `cwd=` 时，相对路径按子进程 cwd 解析，`.tex` 会写进错误目录 |
| 删掉 3.7–3.10 分支、full/single 模式 | 那两版已冻结，其余入口用不到 |

**为什么不并进主构建脚本**：主程序既没有 `Doc/build/NEWS`（要 blurb 生成），也没有 changelog 的 `latex_documents` 条目 —— 塞进去等于给核心程序加一条版式分裂的分支，副本 + 环境变量的代价更小。**为什么不复用主工作流中间文件**：两个 job 各自 checkout，artifact 不会传上百 MB 的 `.tex`；同一个 job 里串跑也省不下多少（Sphinx 照样要重跑），还把失败域合并了。

### 直接调用（不包脚本）

```bash
WNS_PY=$(command -v python) \
python ci/changelogs/builder.py --version 3.15 --mode changelog \
       --outdir changelog-out --workdir changelog-work --mirror 直连
```

版式固定：toc-depth 3 / 书签深度 5 / 连续排版 / 页脚只页码 / tight —— 就是成品册的样子。依赖 `sphinx>=9,<10` + `babel` + `blurb`（3.11+ 分支都用 Sphinx 9；要 8.2.3 的 3.9/3.10 已冻结，不进 CI）。

## 失败语义

| 情况 | 行为 |
|-|-|
| 某版本构建失败 | 该 job 红、无 artifact ⇒ 发布时**保留上一版**（说明里标「沿用上次」），告警 |
| 全部失败、release 已存在 | 不建、不动，`::warning::`，job 绿 |
| 全部失败、release 不存在 | `::error::` 报错 —— 否则就是「绿着啥也没有」 |
| 说明/上传中途出错 | 直接退出，不改动已上传的附件 |

发布顺序是**先传后清**：`upload --clobber` 传本轮 + 冻结件，再删「同版本更早日期的文件」和不认识的残留；本轮没编出来的版本，上次那份**留着**。

## 回退 / 停用

| 想做什么 | 做法 |
|-|-|
| 这一轮不跑 | 手跑时把 `changelogs` 勾成 `false` |
| 代码撤掉 | `git revert --no-commit <本功能的几个 commit> && git commit`（主流程一行没动） |
| 连 release 一起删 | `gh release delete changelogs --yes --cleanup-tag`（不碰 `v3.x` 那几条线） |
| 换冻结件 | 把 PDF 放进 `frozen/Python-<版本>-changelog.pdf`，并在发布脚本 `FROZEN` 元组里加版本号 |
