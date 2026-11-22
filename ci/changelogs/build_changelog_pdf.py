#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI：构建 3.11–3.15 的「完整更新日志」PDF（每天随工作流跑一次）。

产物与本地 whatsnew-studio 的 `--mode changelog` 完全一致：
    Python 3.11 完整更新日志.pdf

本脚本**不重新实现**构建逻辑，只是把 whatsnew-studio 的 `builder.py`
（逐字副本见同目录 builder.py）按 CI 的方式调用一遍：

    3.11 → build/mode=changelog → 只编该 ref 的 changelog.po + 该版本的 NEWS 条目
    3.12 → …
    3.15 → …

要点：
  * 只影响「更新日志册」，不碰主文档 PDF 的构建（那是 pdf_builder_linux.py）；
  * 单版本失败不连累其它版本：全部跑完再统一返回退出码；
  * 发布用的文件名必须是 ASCII（GitHub 附件名会把中文换成点号），
    所以这里把中文原名另存一份 ASCII 副本，两份都不改内容。

用法：
    python ci/changelogs/build_changelog_pdf.py \
        --versions 3.11,3.12,3.13,3.14,3.15 \
        --outdir changelog-out --date 20261122
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import pathlib
import shutil
import subprocess
import sys
import time
import traceback

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent

# 与本地 whatsnew-studio 的 GUI 默认值一致（README 4.2 / 12.2）。
# 这些值决定版式：改任何一个，产物就跟 output/3.9-3.15 里那几本对不上了。
DEFAULTS = dict(
    mode="changelog",
    include_index=True,       # 术语索引页（官方单版本册也有）
    toc_depth=3,              # 正文目录 3 级
    bookmark_depth=5,         # PDF 书签 5 级
    changelog_flow="continuous",   # 小版本连续排（不强制换页）
    changelog_footer="page",       # 页脚只留页码
    changelog_spacing="tight",     # 按官方 PDF 压紧标题/目录/正文
)


def log(msg: str):
    print(msg, flush=True)


def gha(group: str, msg: str):
    """GitHub Actions 注解；本地跑时只是多打一行前缀，无害。"""
    print("::%s::%s" % (group, msg), flush=True)


def load_builder():
    """导入同目录的 builder.py，并把解释器/TeX 路径改成 CI 里的实际值。

    builder.py 里的 PY / TEXBIN 是作者本机的绝对路径（D:\\软件\\Python314、
    F:\\texlive\\2025）。这里用环境变量覆盖，不改副本里的默认值 —— 这样
    本机跑同一份代码仍然是原来的行为。
    """
    os.environ.setdefault("WNS_PY", sys.executable)
    sys.path.insert(0, str(HERE))
    import builder  # noqa: E402  （必须在设置环境变量之后导入）

    builder.PY = os.environ["WNS_PY"]
    # TEXBIN：显式给了才覆盖，否则**保留 builder 自己的判断**——
    # 本机是 F:\texlive\2025（存在就用），CI 里不存在自动变空串（用系统 PATH）。
    # 不要无条件置空：本机 PATH 上可能还有别的 TeX（比如 TinyTeX），
    # 缺宏包时会得到 "File `cmap.sty' not found" 这种莫名其妙的失败。
    texbin = os.environ.get("WNS_TEXBIN")
    if texbin is not None:
        builder.TEXBIN = texbin if texbin and os.path.isdir(texbin) else ""
    log("解释器：%s" % builder.PY)
    log("TeX bin：%s" % (builder.TEXBIN or "（用系统 PATH，CI 就是 /usr/bin）"))
    return builder


def pdf_pages(pdf: pathlib.Path) -> str:
    """页数用 poppler 的 pdfinfo 读；没装就退回 pypdf，都没有则返回 —。"""
    exe = shutil.which("pdfinfo")
    if exe:
        try:
            out = subprocess.run([exe, str(pdf)], capture_output=True, text=True,
                                 timeout=120).stdout
            for line in out.splitlines():
                if line.lower().startswith("pages:"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass
    try:
        from pypdf import PdfReader
        return str(len(PdfReader(str(pdf)).pages))
    except Exception:
        return "—"


def verify_pdf(pdf: pathlib.Path) -> int:
    """结构完整性：必须以 startxref/%%EOF 收尾（截断的 PDF 也能有个大小）。"""
    size = pdf.stat().st_size
    if size < 100_000:
        raise RuntimeError("PDF 太小（%.1f KB），基本是失败产物" % (size / 1024))
    with open(pdf, "rb") as f:
        f.seek(max(0, size - 8192))
        tail = f.read()
    if b"%%EOF" not in tail or b"startxref" not in tail:
        raise RuntimeError("PDF 不完整（缺 startxref/%%EOF），转换被中断")
    return size


def build_one(builder, ver: str, outdir: pathlib.Path, workdir: pathlib.Path,
              mirror: str, date: str, clean_work: bool,
              skip_download: bool = False, latex_only: bool = False) -> dict:
    """编一个版本，返回一条结果记录（失败时抛异常，由调用方收集）。"""
    t0 = time.time()
    raw_out = outdir / "_raw"
    raw_out.mkdir(parents=True, exist_ok=True)

    cfg = dict(DEFAULTS)
    cfg.update(version=ver, outdir=str(raw_out), workdir=str(workdir),
               mirror=mirror, keep_work=True,
               skip_download=skip_download, latex_only=latex_only)

    log("\n" + "=" * 72)
    log("构建 Python %s 完整更新日志（模式 %s）" % (ver, cfg["mode"]))
    log("=" * 72)
    pdf = pathlib.Path(builder.build(cfg))

    size = verify_pdf(pdf)
    pages = pdf_pages(pdf)

    # 中文原名（与 output/3.9-3.15 一致）+ ASCII 副本（发布用）
    cn = outdir / ("Python %s 完整更新日志.pdf" % ver)
    shutil.copy2(pdf, cn)
    ascii_name = "Python-%s-changelog-%s.pdf" % (ver, date)
    shutil.copy2(pdf, outdir / ascii_name)

    # 中间产物在 CI 里没有价值（下一轮会全量重下），别把 5 个版本 ~800MB
    # 堆在 runner 上把磁盘吃满。本地想留就传 --keep-work。
    if clean_work:
        shutil.rmtree(workdir / ("build_changelog_%s" % ver.replace(".", "_")),
                      ignore_errors=True)

    dt = time.time() - t0
    log("✔ %s：%s 页 / %.2f MB / 用时 %.1f 分 → %s"
        % (ver, pages, size / 1048576, dt / 60, ascii_name))
    return dict(version=ver, cn=cn.name, asset=ascii_name, pages=pages,
                bytes=size, seconds=round(dt, 1), ok=True, error="")


def main() -> int:
    ap = argparse.ArgumentParser(description="构建 3.11–3.15 完整更新日志 PDF")
    ap.add_argument("--versions", default="3.11,3.12,3.13,3.14,3.15",
                    help="逗号分隔，默认 3.11–3.15（3.9/3.10 已冻结，不再重建）")
    ap.add_argument("--outdir", default=str(REPO / "changelog-out"))
    ap.add_argument("--workdir", default=str(REPO / "changelog-work"))
    ap.add_argument("--date", default=_dt.datetime.now(
        _dt.timezone(_dt.timedelta(hours=8))).strftime("%Y%m%d"),
        help="写进发布文件名的日期（默认北京时间今天）")
    ap.add_argument("--mirror", default=os.environ.get("WNS_MIRROR", "auto"),
                    choices=["auto", "ghproxy.net", "gh-proxy.com", "jsDelivr", "直连"])
    ap.add_argument("--keep-work", action="store_true",
                    help="保留中间目录（本地调试用；CI 不传，省磁盘）")
    ap.add_argument("--skip-download", action="store_true",
                    help="本地续跑：复用上次下载的文件（CI 绝不能用 —— 那样内容不会更新）")
    ap.add_argument("--latex-only", action="store_true",
                    help="本地续跑：复用已生成的 .tex，只重编 LaTeX（调版式用）")
    ap.add_argument("--report", default="",
                    help="把结果写成 Markdown（发布说明用），默认写到 outdir/changelog-report.md")
    a = ap.parse_args()

    versions = [v.strip() for v in a.versions.split(",") if v.strip()]
    outdir = pathlib.Path(a.outdir)
    workdir = pathlib.Path(a.workdir)
    outdir.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)

    builder = load_builder()
    log("本轮版本：%s ｜ 日期：%s ｜ 输出：%s" % (", ".join(versions), a.date, outdir))

    results, failed = [], []
    # 续跑时不能删中间目录（删了就没得复用了）
    clean = not a.keep_work and not (a.skip_download or a.latex_only)
    for ver in versions:
        try:
            results.append(build_one(builder, ver, outdir, workdir, a.mirror,
                                     a.date, clean_work=clean,
                                     skip_download=a.skip_download,
                                     latex_only=a.latex_only))
        except Exception as exc:  # 单版本失败不终止整轮
            failed.append(ver)
            log("✘ %s 构建失败：%s" % (ver, exc))
            traceback.print_exc()
            results.append(dict(version=ver, cn="", asset="", pages="—", bytes=0,
                                seconds=0, ok=False, error=str(exc).splitlines()[0]))

    # ---- 报告（发布说明直接引用，避免手写数字和实际产物对不上）----
    ok = [r for r in results if r["ok"]]
    lines = ["**Python 完整更新日志（3.9–3.15）**", "",
             "构建日期：%s ｜ 成功 %d / %d 个版本" % (a.date, len(ok), len(results)),
             "", "| 版本 | 页数 | 大小 | 文件 |", "|-|-|-|-|"]
    for r in results:
        if r["ok"]:
            lines.append("| %s | %s | %.1f MB | `%s` |"
                         % (r["version"], r["pages"], r["bytes"] / 1048576, r["asset"]))
        else:
            lines.append("| %s | — | — | 构建失败：%s |"
                         % (r["version"], r["error"].replace("|", "/")))
    report = pathlib.Path(a.report) if a.report else outdir / "changelog-report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    log("\n本轮结果：")
    for r in results:
        log("  %-5s %s" % (r["version"],
                           ("✔ %s 页 %s" % (r["pages"], r["asset"])) if r["ok"]
                           else "✘ " + r["error"]))
    log("报告：%s" % report)

    if failed:
        gha("error", "更新日志构建失败：%s（成功的版本照常发布）" % ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
