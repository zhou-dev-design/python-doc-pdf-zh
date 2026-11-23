# -*- coding: utf-8 -*-
"""whatsnew Studio 构建核心（也是唯一构建入口）。

每次运行都从 GitHub 官方仓库下载 whatsnew 相关文件（内置加速镜像），
再用官方 Sphinx + LaTeX 路线编译中文 PDF。不改动 whatsnew-volume 下的任何脚本。

可独立命令行运行，也可由 whatsnew_gui.py 通过 QProcess 调用；GUI 只是把界面
选项拼成同一组命令行参数，两者必须产出一致结果。stdout 中以
@@STEP@@ / @@LOG@@ / @@PCT@@ / @@DONE@@ / @@FAIL@@ 输出结构化进度，供 GUI 解析。

给其他环境 AI 助手的交接要点（完整说明见同目录 README.md 第 0、12 节）：
  1. 环境锚点：PY / TEXBIN 以及 work/sphinx82（Sphinx 8.2.3 隔离环境）。
     换机器时先替换这三个路径并锁定版本，否则 PDF 版式/内容会有差异。
  2. 三条不可破坏的约束：不覆盖全局 linkcolor（目录会整条变蓝）；
     不打开 hyperindex=true（会把 .toc 写成 0 字节）；所有 .tex 注入必须幂等。
  3. 版式基线已经与 CPython 官方 Doc/conf.py 对齐：xelatex、a4paper、
     10pt、tocdepth=2。全集用 manual 文档类、加 xeCJK 字体、去掉官方附录，
     是有意差异；不要为了“像官方”擅自改成 howto，除非用户明确要求单版本复刻。
  4. 验收看 README 12.2：@@DONE@@、manual/tocdepth/xeCJK 特征、PDF 的
     %%EOF/startxref、索引页码可点击、目录与书签层级独立。不要用文件大小当
     唯一标准（上游 NEWS.d 与镜像状态每天都在变）。
"""
# ===== 本文件是 whatsnew-studio/builder.py 的**逐字副本**，只改了这几处 =====
#   1) PY / TEXBIN 支持环境变量覆盖（WNS_PY / WNS_TEXBIN）—— CI 里没有
#      D:\软件\Python314 与 F:\texlive\2025\bin\windows；
#   2) TEXBIN 目录不存在时置空串，run() 不再往 PATH 前面塞空段（空段=当前目录）；
#   3) http_get 对 api.github.com 带上 GITHUB_TOKEN（匿名 60 次/小时，CI 必 403）；
#   4) `--mirror` 显式指定时不探测，只用那一个（CI 传「直连」＝只用官网）；
#   5) workdir/outdir 与交给子进程的路径一律绝对化 —— 子进程 cwd=Doc，相对路径
#      会被它按 Doc 解析，.tex 就写到 Doc/ 底下去了（CI 传相对 --outdir 时必踩）；
#   6) 头部这段说明。
# 为什么复制而不 import：CI 只 checkout 本仓库，拿不到同级的 whatsnew-studio。
# 同步方法：上游 builder.py 更新后重新覆盖本文件，再把这 5 处改回来（约 25 行）。
# 版式/命名一律以上游为准，本文件不做任何“改进”——这里只是搬运。
from __future__ import annotations

import argparse
import concurrent.futures
import glob
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
DOCBASE = pathlib.Path(r"C:\Users\zb137\Desktop\编程软件\Python 文档")
PY = os.environ.get("WNS_PY") or r"D:\软件\Python314\python.exe"
TEXBIN = os.environ.get("WNS_TEXBIN") or r"F:\texlive\2025\bin\windows"
# CI（Linux）里 TEXBIN 不存在：置空串，run() 就不往 PATH 前面插空段。
if not os.path.isdir(TEXBIN):
    TEXBIN = ""

# 只处理 3.7+：python-docs-zh-cn 只有 3.7 及以后的分支，再早的版本没有
# 对应中文译文，拿 3.7 的译文去配 3.6 的源文会张冠李戴。
# 版本不写死上限：3.16 / 3.17 … 只要两个仓库出现同名 ref 就能直接构建。
MIN_MINOR = 7
SUGGEST_MAX_MINOR = 20     # GUI 下拉的预置建议值，可手动输入更高版本
VERSIONS = ["3.%d" % i for i in range(MIN_MINOR, SUGGEST_MAX_MINOR + 1)]
# CPython 的 3.7–3.10 维护分支已删除，但保留同名 tag（/tree/3.10 打开的
# 就是这个 tag）；3.11 及以后（含未来的 3.16+）都是分支。
CPY_ARCHIVE_TAG_MAX = 10
FALLBACK_CPY = "3.15"      # 仅用于镜像探测等兜底，不再作为数据源


def version_minor(ver: str) -> int:
    return int(ver.split(".")[1])


def check_version(ver: str):
    if not re.fullmatch(r"3\.\d+", ver or ""):
        raise ValueError("版本号格式应为 3.x（例如 3.10、3.16）：%r" % ver)
    if version_minor(ver) < MIN_MINOR:
        raise ValueError("只支持 3.7 及以后版本（中文译文仓库从 3.7 才有分支）：%s" % ver)


def is_cpy_tag(ver: str) -> bool:
    """3.7–3.10 是归档标签；3.11+ 是分支（未来版本天然落在分支一侧）。"""
    return version_minor(ver) <= CPY_ARCHIVE_TAG_MAX

# 正文目录（Contents）显示到第几级：1=章, 2=节, 3=小节, 4=子小节, 5=段落标题。
# LaTeX 的 tocdepth 比它小 1（chapter 记为 0）。以前硬编码 1 → 只有 2 级。
TOC_DEPTHS = (2, 3, 4, 5)
DEFAULT_TOC_DEPTH = 3
# PDF 阅读器侧边栏书签到第几级（与正文目录互不影响，Sphinx 默认 5）。
BOOKMARK_DEPTHS = (3, 4, 5, 6)
DEFAULT_BOOKMARK_DEPTH = 5
# 官方 Doc/conf.py 的 preamble 写 \setcounter{tocdepth}{2}；默认 3 级正文目录
# 经 patch_conf/patch_toc_depth 减 1 后正好是 2，与官方基线一致（见 README 8.1）。

ZH_REPO = "python/python-docs-zh-cn"
CPY_REPO = "python/cpython"

RAW = "https://raw.githubusercontent.com"
MIRRORS = {
    "ghproxy.net": RAW + "/{repo}/{branch}/{path}",
    "gh-proxy.com": RAW + "/{repo}/{branch}/{path}",
    "jsDelivr": "https://cdn.jsdelivr.net/gh/{repo}@{branch}/{path}",
    "直连": RAW + "/{repo}/{branch}/{path}",
}
PROXY_PREFIX = {
    "ghproxy.net": "https://ghproxy.net/",
    "gh-proxy.com": "https://gh-proxy.com/",
    "jsDelivr": "",
    "直连": "",
}

# 只下载 whatsnew 构建真正需要的 CPython 路径，不下整个源码树
SCAFFOLD_PREFIXES = (
    "Doc/whatsnew/",
    "Doc/deprecations/",
    "Doc/includes/",
    "Doc/tools/",
    "Doc/_static/",
    "Doc/data/",
    "Misc/NEWS.d/",
    # whatsnew/3.15.rst 的 Tachyon 插图在 Lib/ 下（rst 写 ../../Lib/...），
    # 漏掉它会让 graphics 包报 Division by 0 并导致 xdvipdfmx 中断。
    "Lib/profiling/sampling/_assets/",
)
SCAFFOLD_FILES = (
    "Doc/conf.py", "Doc/Makefile", "Doc/README.rst", "Doc/requirements.txt",
    "Doc/make.bat",
    "README.rst", "LICENSE", "Include/Python.h", "Include/patchlevel.h",
    "Python/ceval.c",
)
REPO_MARKERS = ("README.rst", "LICENSE", "Include/Python.h", "Python/ceval.c")


# ---------------------------------------------------------------- 输出协议
def emit(kind: str, msg: str = ""):
    print("@@%s@@ %s" % (kind, msg), flush=True)


def log(msg: str):
    emit("LOG", msg)


def step(name: str, pct: int):
    emit("STEP", name)
    emit("PCT", str(pct))


# ---------------------------------------------------------------- 网络
def mirror_url(mirror: str, repo: str, branch: str, path: str) -> str:
    tpl = MIRRORS[mirror]
    url = tpl.format(repo=repo, branch=branch, path=path.lstrip("/"))
    pre = PROXY_PREFIX[mirror]
    return pre + url if pre else url


def http_get(url: str, timeout: int = 60) -> bytes:
    headers = {"User-Agent": "whatsnew-studio/1.0"}
    # ★ 副本新增：api.github.com 匿名额度只有 60 次/小时，而 GitHub 托管 runner
    #   的出口 IP 是共享的 —— 五个 job 一起跑必然 403（2026-11-23 实测：
    #   「GitHub 目录树 API 不可用（HTTPError）」→ 退到 jsDelivr 也被 403）。
    #   有 GITHUB_TOKEN / GH_TOKEN 就带上（5000 次/小时）；没有则维持匿名，
    #   本机行为完全不变。只对 api.github.com 带，别的域名不外泄。
    _tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if _tok and url.startswith("https://api.github.com/"):
        headers["Authorization"] = "Bearer " + _tok
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def probe_mirrors(order: list[str], branch: str = FALLBACK_CPY) -> list[str]:
    """按实测延迟排序可用镜像；不可用的排到最后。"""
    probe = ("Doc/whatsnew/index.rst", CPY_REPO, branch)
    scored = []
    for m in order:
        t0 = time.time()
        try:
            b = http_get(mirror_url(m, probe[1], probe[2], probe[0]), timeout=12)
            ok = len(b) > 100
        except Exception:
            ok = False
        scored.append((m, (time.time() - t0) if ok else 999.0, ok))
    scored.sort(key=lambda x: (not x[2], x[1]))
    for m, t, ok in scored:
        log("  镜像 %-16s %s" % (m, "%.2fs" % t if ok else "不可用"))
    return [m for m, _, _ in scored]


def github_tree(repo: str, branch: str) -> list[str]:
    """一次拿全树，过滤出所需路径。失败时退回 jsDelivr 的 flat 清单。"""
    url = "https://api.github.com/repos/%s/git/trees/%s?recursive=1" % (repo, branch)
    try:
        d = json.loads(http_get(url, timeout=90))
        if isinstance(d, dict) and "tree" in d:
            return [x["path"] for x in d["tree"] if x.get("type") == "blob"]
    except Exception as e:
        log("  [提示] GitHub 目录树 API 不可用（%s），改用 jsDelivr" % type(e).__name__)
    url = "https://data.jsdelivr.com/v1/package/gh/%s@%s/flat" % (repo, branch)
    d = json.loads(http_get(url, timeout=90))
    return [x["name"].lstrip("/") for x in d.get("files", [])]


def zh_po_paths(branch: str, version: str | None = None) -> list[str]:
    """列出该分支 whatsnew 下的 po（优先目录树 API，失败用候选名 + 404 跳过）。

    兜底名单要跟着版本走：不写死到 3.15，否则将来 3.16 的 po 会漏掉。
    """
    try:
        d = json.loads(http_get(
            "https://api.github.com/repos/%s/contents/whatsnew?ref=%s" % (ZH_REPO, branch),
            timeout=40))
        if isinstance(d, list):
            return sorted("whatsnew/" + x["name"] for x in d if x["name"].endswith(".po"))
    except Exception:
        pass
    top = SUGGEST_MAX_MINOR
    if version and re.fullmatch(r"3\.\d+", version):
        top = max(top, version_minor(version))
    names = (["index", "changelog"] + ["2.%d" % i for i in range(8)]
             + ["3.%d" % i for i in range(MIN_MINOR, top + 1)])
    return ["whatsnew/%s.po" % n for n in names]


def download_all(items: list[tuple[str, str, str, pathlib.Path]],
                 mirrors: list[str], workers: int = 10, progress: bool = True):
    """(repo, branch, relpath, dest_root) —— 并发下载，失败逐个切镜像。

    404 视为「该分支不存在此文件」（例如 3.11 分支没有 3.15.po），不算失败。
    """
    total = len(items)
    done = [0]
    failed, missing, cached = [], [], []

    def one(item):
        repo, branch, rel, dest_root = item
        dst = dest_root / rel
        for m in mirrors:
            try:
                data = http_get(mirror_url(m, repo, branch, rel), timeout=90)
                if not data:
                    raise ValueError("空响应")
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(data)
                return rel, "ok"
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue          # 换镜像确认，仍 404 才算不存在
                continue
            except Exception:
                continue
        if dst.is_file() and dst.stat().st_size > 0:
            return rel, "cached"      # 网络失败时用上次下载的副本兜底
        return rel, "missing"

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for rel, status in ex.map(one, items):
            done[0] += 1
            if status == "cached":
                cached.append(rel)
            elif status == "missing":
                # 判定：所有镜像都 404 → 该分支不含此文件；否则是网络失败
                failed.append(rel)
            if progress and (done[0] % 25 == 0 or done[0] == total):
                emit("PCT", str(5 + int(done[0] / total * 20)))
                log("  下载进度 %d/%d" % (done[0], total))
    if cached:
        log("  [提示] %d 个文件用本地旧副本兜底" % len(cached))
    if failed:
        log("  [提示] %d 个文件在该分支不存在或下载失败：%s"
            % (len(failed), [pathlib.Path(x).name for x in failed[:6]]))
    return len(failed)


# ---------------------------------------------------------------- 构建
def run(cmd, cwd=None, timeout=3600, extra_env=None):
    env = os.environ.copy()
    if TEXBIN:
        env["PATH"] = TEXBIN + os.pathsep + env.get("PATH", "")
    if extra_env:
        env.update(extra_env)
    r = subprocess.run([str(x) for x in cmd], cwd=str(cwd) if cwd else None,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, env=env)
    return r


def natural_key(name: str):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", name)]


def resolve_branches(ver: str):
    """两个仓库一律用「与版本号同名的 ref」，未来 3.16/3.17 无需改代码。

    关键一：3.7–3.10 在 CPython 里是 tag 而非 branch，但确实存在，早先一律
    回退 3.11 会让这些版本的 whatsnew 正文、conf.py、扩展和 NEWS.d 全部取错。
    关键二：changelog 的 NEWS 数据必须来自对应 ref。较新分支的 Misc/NEWS.d/
    只保留当前系列的补丁版归档，例如 3.15 分支里 3.11 只剩 3.11.0 的
    alpha/beta 8 节，而 3.11 分支自己有 3.11.0–3.11.18 全部条目。
    """
    check_version(ver)
    return ver, ver


def filter_news(full: str, version: str, out: pathlib.Path):
    """按 "What's New in Python 3.xx.y ...?" 章节标题过滤出该大版本条目。"""
    pat = re.compile(r"^What's New in Python [^\n]+\?\n=+\s*$", re.M)
    heads = list(pat.finditer(full))
    keep = []
    for i, m in enumerate(heads):
        title = m.group(0).splitlines()[0]
        if re.search(r"Python 3\.%s\.\d" % re.escape(version.split(".")[1]), title):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(full)
            keep.append(full[m.start():end])
    if not keep:
        log("  [警告] NEWS 里没有 %s 相关章节（共 %d 节），保留完整变更日志"
            % (version, len(heads)))
        return
    (out.parent / "NEWS.full").write_text(full, encoding="utf-8")
    preamble = full[:heads[0].start()] if heads else ""
    out.write_text(preamble + "".join(keep), encoding="utf-8")
    log("版本过滤：保留 %s 的 %d 个章节（原文 %d 节），%.2f MB → %.2f MB"
        % (version, len(keep), len(heads), len(full) / 1048576,
           out.stat().st_size / 1048576))


def patch_legacy_blurbs(root: pathlib.Path):
    """3.7 等早期标签里有几个 "no changes" 占位条目缺 `.. section:` 元数据。

    新版 blurb 的 finish_entry() 遇到它们会直接抛
    "No 'section' specified. You must provide one!"。补一个默认分类即可，
    不改动条目正文，也不影响 3.10+（那里本来就不缺）。
    """
    nd = root / "Misc" / "NEWS.d"
    fixed = 0
    for p in nd.rglob("*.rst"):
        if "next" in p.parts or not p.is_file():
            continue
        try:
            s = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if ".. section:" in s or (".. nonce:" not in s and ".. bpo:" not in s):
            continue
        p.write_text(".. section: Miscellaneous\n" + s, encoding="utf-8")
        fixed += 1
    if fixed:
        log("兼容早期 blurb 片段：为 %d 个缺 section 的归档条目补默认分类" % fixed)


def normalize_news_titles(out: pathlib.Path):
    """早期标签的 changelog.po 常常连版本标题的 msgid 都没有（3.7 就是）。

    直接在本地生成的 build/NEWS 里把标题术语统一成「正式版 / 候选发布版」，
    作为 mo 补齐之外的兜底。只动标题行，不动条目正文，也不碰远程译文。
    """
    s = out.read_text(encoding="utf-8", errors="replace")
    a = re.sub(r"(?m)^(What's New in Python 3\.\d+\.\d+(?:[abrc]\d+)?) final\?",
               r"\1 正式版?", s)
    a = re.sub(r"(?m)^(What's New in Python 3\.\d+\.\d+) release candidate (\d+)\?",
               r"\1 候选发布版 \2?", a)
    if a != s:
        n = sum(1 for x, y in zip(s.splitlines(), a.splitlines()) if x != y)
        out.write_text(a, encoding="utf-8")
        log("归档标签：NEWS 版本标题术语补齐 %d 行（正式版 / 候选发布版）" % n)


def prepare_news(root: pathlib.Path, version: str, mode: str,
                 legacy_tag: bool = False):
    """用该 ref 自己的 Misc/NEWS.d 生成 build/NEWS；单版本册再按版本过滤。"""
    patch_legacy_blurbs(root)
    doc = root / "Doc"
    out = doc / "build" / "NEWS"
    out.parent.mkdir(parents=True, exist_ok=True)
    r = run([PY, "-m", "blurb", "merge", "-f", "Doc/build/NEWS"],
            cwd=root, timeout=900)
    if not out.is_file():
        raise RuntimeError("blurb 生成 NEWS 失败：" + (r.stderr or r.stdout)[-1200:])
    full = out.read_text(encoding="utf-8", errors="replace")
    log("build/NEWS 生成：%.2f MB" % (len(full) / 1048576))
    if mode != "full":
        filter_news(full, version, out)
    if legacy_tag:
        normalize_news_titles(out)


def normalize_release_terms(cat):
    """补齐 3.7–3.10 中文 changelog 里未统一的版本标题术语。

    3.11–3.15 的译稿已把 "Python 3.x.y final" 译为「正式版」、
    "release candidate N" 译为「候选发布版 N」；早期分支的 po 里这些
    msgstr 仍为空、直接照抄英文或写成 rcN。这里只在编译 .mo 前于内存里
    补齐这类「未翻译/旧写法」条目，不改动下载的 po，更不碰 Transifex。
    已有其它中文译法的条目一律保留。
    """
    n = 0
    for msg in cat:
        mid = msg.id
        if not isinstance(mid, str) or not mid:
            continue
        cur = msg.string or ""
        if cur and cur != mid and not re.fullmatch(r"Python [\d.]+ ?rc\d+", cur):
            continue                       # 已经是人工中文译文，别覆盖
        m = re.fullmatch(r"(Python \d+\.\d+\.\d+(?:[ab]\d+|rc\d+)?) final", mid)
        if m:
            msg.string = m.group(1) + " 正式版"
            n += 1
            continue
        m = re.fullmatch(r"(Python \d+\.\d+\.\d+) release candidate (\d+)", mid)
        if m:
            msg.string = "%s 候选发布版 %s" % (m.group(1), m.group(2))
            n += 1
    return n


def install_locales(po_root: pathlib.Path, doc: pathlib.Path):
    from babel.messages.pofile import read_po
    from babel.messages.mofile import write_mo
    loc_root = doc / "locales"
    lc = loc_root / "zh_CN" / "LC_MESSAGES"
    # 每次构建用全新 catalog 目录：改名隔离旧目录（原子操作，不做批量删除）
    if loc_root.is_dir():
        try:
            os.replace(str(loc_root), str(doc / ("locales_prev_%d" % int(time.time()))))
        except OSError:
            pass
    lc.mkdir(parents=True, exist_ok=True)
    files = sorted((po_root / "whatsnew").glob("*.po"))
    n = 0
    for src in files:
        dst = lc / "whatsnew" / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        try:
            with open(src, "rb") as f:
                cat = read_po(f, locale="zh_CN", charset="utf-8")
            fixed = normalize_release_terms(cat)
            if fixed:
                log("  %s：补齐 %d 条版本标题术语（正式版 / 候选发布版）"
                    % (src.name, fixed))
            with open(dst.with_suffix(".mo"), "wb") as f:
                write_mo(f, cat)
            n += 1
        except Exception as e:
            log("  [警告] 编译失败 %s: %s" % (src.name, e))
    log("已编译 %d/%d 个中文 po → mo（babel）" % (n, len(files)))
    if n == 0:
        raise RuntimeError("没有任何中文 po 编译成功")


def output_title(version: str, mode: str) -> str:
    """三种模式统一的册名（同时用于 PDF 标题、元数据和输出文件名）。"""
    if mode == "full":
        return "Python %s whatsnew 全集" % version
    if mode == "changelog":
        return "Python %s 完整更新日志" % version
    return "Python %s 更新文档（含变更日志）" % version


def mode_label(mode: str) -> str:
    return {"full": "全集", "single": "单版本",
            "changelog": "完整更新日志"}.get(mode, mode)


def choose_docs(po_root: pathlib.Path, mode: str, version: str,
               rst_names: set[str] | None = None):
    """章节清单 = 中文 po ∩ 该 CPython ref 实际存在的 whatsnew/*.rst。

    以前只看中文 po 列表：回退到 3.11 时刚好能蒙对（3.11 的 whatsnew 目录
    覆盖 2.0–3.11 全部文件）。改用各版本自己的 ref 后，3.7 的 tag 里没有
    3.10.rst、3.10 的 tag 里也没有 3.15.rst，不取交集就会引用不存在的文档。
    """
    names = sorted((p.stem for p in (po_root / "whatsnew").glob("*.po")), key=natural_key)
    if rst_names is not None:
        avail = set(rst_names) | {"index"}
        before = len(names)
        names = [n for n in names if n in avail]
        log("章节按对应 ref 的 whatsnew/*.rst 取交集：中文 po %d → 可编 %d"
            % (before, len(names)))
    has_changelog = "changelog" in names
    if mode == "changelog":
        # 独立成册：只编该大版本的完整更新日志，不含 whatsnew 正文。
        if not has_changelog:
            raise RuntimeError("该 ref 没有 changelog.rst / changelog.po，无法生成更新日志册")
        return ["changelog"], names
    if mode == "single":
        want = version
        if want not in names:
            raise RuntimeError("该 ref 不含 %s.rst / %s.po（可用：%s）"
                               % (want, want, ", ".join(names[-8:])))
        docs = [want] + (["changelog"] if has_changelog else [])
        return docs, names
    docs = [n for n in names if n not in ("changelog", "index")]
    if "index" in names:
        docs.insert(0, "index")
    if has_changelog:
        docs.append("changelog")
    return docs, names


def patch_index_rst(doc: pathlib.Path):
    p = doc / "whatsnew" / "index.rst"
    if not p.is_file():
        return
    s = p.read_text(encoding="utf-8", errors="replace")
    out, i = [], 0
    while i < len(s.splitlines()):
        lines = s.splitlines()
        if re.match(r"^\s*\.\.\s+toctree::\s*$", lines[i]):
            i += 1
            while i < len(lines):
                ln = lines[i]
                if ln.strip() == "" or ln.startswith((" ", "\t")):
                    i += 1
                    continue
                break
            continue
        out.append(lines[i])
        i += 1
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


def write_root_doc(doc: pathlib.Path, docs: list[str], mode: str, version: str):
    title = output_title(version, mode)
    # 只保留标题 + toctree：任何说明性正文都会在目录后单独占一页（甚至
    # 配合 \chapter 的分页产生空白页），对成册没有价值，直接不写。
    lines = [title, "=" * 60, "", ".. toctree::", "   :maxdepth: 1", ""]
    for d in docs:
        label = "更新历史记录" if d == "changelog" else d
        lines.append("   %s <whatsnew/%s>" % (label, d))
    lines.append("")
    (doc / "whatsnew_all.rst").write_text("\n".join(lines), encoding="utf-8")
    log("根文档：%d 个一级章节" % len(docs))


def patch_conf(doc: pathlib.Path, docs: list[str], version: str, mode: str,
               toc_depth: int = DEFAULT_TOC_DEPTH, cpy_ref: str | None = None):
    p = doc / "conf.py"
    s = p.read_text(encoding="utf-8", errors="replace")
    marker = "# ==== whatsnew-studio override ===="
    if marker in s:
        s = s[:s.index(marker)]
    title = output_title(version, mode)
    all_wn = sorted(x.stem for x in (doc / "whatsnew").glob("*.rst"))
    unused = ["whatsnew/%s.rst" % n for n in all_wn if n not in docs]
    override = """
# ==== whatsnew-studio override ====
# Sphinx 9 把 status_iterator 从 sphinx.util 移到了 sphinx.util.display，
# 而 3.7–3.10 标签里的单体 pyspecific.py 仍从旧位置导入。补一个别名即可
# 让旧扩展完整加载（它同时提供 miscnews 指令与 issue/gh 角色，不能简单删掉）。
import sphinx.util as _wns_sphinx_util
if not hasattr(_wns_sphinx_util, 'status_iterator'):
    try:
        from sphinx.util.display import status_iterator as _wns_status_iterator
        _wns_sphinx_util.status_iterator = _wns_status_iterator
    except ImportError:
        pass
# 3.7/3.8 的 pyspecific 还用 Sphinx 2 时代的 PyModulelevel / PyClassmember
# （Sphinx 8 和 9 都只剩 PyFunction / PyMethod），补别名避免 ImportError。
import sphinx.domains.python as _wns_pydomain
if not hasattr(_wns_pydomain, 'PyModulelevel'):
    _wns_pydomain.PyModulelevel = _wns_pydomain.PyFunction
if not hasattr(_wns_pydomain, 'PyClassmember'):
    _wns_pydomain.PyClassmember = _wns_pydomain.PyMethod
# 这些扩展依赖 Doc/ 之外的源码模块（asdl、Parser/…），且与 whatsnew 无关；
# 按对应 ref 取源码时去掉，避免 Sphinx 导入失败。
_DROP_EXT = {'asdl_highlight', 'peg_highlight', 'escape4chm',
             'glossary_search', 'suspicious', 'sphinxext.opengraph'}
extensions = [e for e in extensions if e not in _DROP_EXT]
# 脚手架版本号的页脚按所选版本改正。
release = %r
language = 'zh_CN'
locale_dirs = ['locales']
gettext_compact = False
root_doc = 'whatsnew_all'
master_doc = 'whatsnew_all'   # 3.11 及更早分支用旧名，一并覆盖
exclude_patterns = [
    'about.rst', 'bugs.rst', 'contents.rst', 'copyright.rst',
    'glossary.rst', 'license.rst', 'improve-page.rst',
    'improve-page-nojs.rst', 'sphinx.rst',
    'library/*', 'c-api/*', 'reference/*', 'tutorial/*', 'using/*',
    'faq/*', 'howto/*', 'extending/*', 'installing/*', 'builtins/*',
    'distributing/*', 'deprecations/*', 'includes/*.rst', 'venv/*',
    'README.rst',
] + %r
latex_engine = 'xelatex'
latex_appendices = []
# 不引用 _doc_authors 等分支私有变量：3.11 及更早的 conf.py 没有定义它。
# 文档类刻意用 manual 而非官方单版本册的 howto：全集跨多个 Python 版本，
# 需要章级结构容纳「每个版本一篇」。官方附录（glossary/about/license/
# copyright）也不加入，避免在合集里重复出现；这两项是有意差异，见 README 12.1。
latex_documents = [
    ('whatsnew_all', 'whatsnew_all.tex', %r,
     'Python Software Foundation', 'manual'),
]
try:
    latex_elements
except NameError:
    latex_elements = {}
# 旧分支默认 letterpaper，统一为 A4 与既有各册一致（官方也是 a4paper）。
latex_elements['papersize'] = 'a4paper'
# 中文字体是本项目相对官方的必要差异；tocdepth 仍按官方基线设为 2。
# 注意：这里只是首个写入点，patch_toc_depth() 会在 .tex 层统一所有 tocdepth，
# 所以 --latex-only 续跑也一定能拿到新值。
latex_elements['preamble'] = latex_elements.get('preamble', '') + r'''
\\usepackage{xeCJK}
\\setCJKmainfont{FandolSong-Regular.otf}[BoldFont=FandolHei-Bold.otf]
\\setCJKsansfont{FandolHei-Regular.otf}
\\setCJKmonofont{FandolFang-Regular.otf}
\\setcounter{tocdepth}{%d}
'''
""" % (version, unused, title, toc_depth - 1)
    p.write_text(s.rstrip() + "\n" + override, encoding="utf-8")
    log("conf.py 副本已覆盖（来源 cpython@%s，排除 %d 个未使用 whatsnew 文档）"
        % (cpy_ref or "?", len(unused)))


def legacy_sphinx_env(workdir: pathlib.Path):
    """归档标签（3.7–3.10）优先用隔离安装的 Sphinx 8.2.3。

    work/sphinx82 由 `pip install --target` 生成，不污染系统 Sphinx 9；
    不存在时返回 None，退回系统 Sphinx（conf.py 里的兼容垫片同样能跑）。
    """
    d = pathlib.Path(workdir) / "sphinx82"
    if (d / "sphinx" / "__init__.py").is_file():
        return {"PYTHONPATH": str(d) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    return None


def sphinx_latex(doc: pathlib.Path, outlatex: pathlib.Path,
                 extra_env: dict | None = None):
    # 交给子进程的路径一律绝对化（子进程 cwd=doc，相对路径会按 doc 解析）
    doc = pathlib.Path(doc).resolve()
    outlatex = pathlib.Path(outlatex).resolve()
    if outlatex.is_dir() and any(outlatex.glob("*.fdb_latexmk")):
        try:
            outlatex.rename(outlatex.parent / ("latex_prev_%d" % int(time.time())))
        except OSError:
            pass
    outlatex.mkdir(parents=True, exist_ok=True)
    r = run([PY, "-m", "sphinx", "-b", "latex", "-D", "language=zh_CN",
             "-D", "latex_engine=xelatex", "-q", ".", str(outlatex)],
            cwd=doc, timeout=3600, extra_env=extra_env)
    tex = outlatex / "whatsnew_all.tex"
    if not tex.is_file():
        raise RuntimeError("Sphinx 未产出 .tex（返回码 %s，期望位置 %s）：\n%s\n%s"
                           % (r.returncode, tex,
                              (r.stdout or "")[-2500:], (r.stderr or "")[-2500:]))
    log("Sphinx 完成：%.2f MB（%s）" % (tex.stat().st_size / 1048576, tex))
    return tex


def ensure_graphics(root: pathlib.Path, tex: pathlib.Path, branch: str,
                    mirrors: list[str]):
    """补下载 .tex 引用的图片，并改写为编译目录内的纯 ASCII 短名。

    Sphinx 在 Windows 上把 `../../Lib/.../logo.png` 写成
    `{{..\\Lib\\...\\logo}.png}`：反斜杠会被 LaTeX 当转义字符吃掉，
    xdvipdfmx 报 `Could not find file: .._assets-logo.png`；而且路径基准是
    Doc/，latexmk 却在 out/latex/ 下运行。两者叠加会产出截断 PDF。
    解法：下载图片 → 复制到 out/latex/wns_img_N.ext → 改写 tex 参数。
    幂等：已改写过的引用不再处理。
    """
    s = tex.read_text(encoding="utf-8", errors="replace")
    outlatex = tex.parent
    lines = s.splitlines(keepends=True)
    mapping: dict[str, tuple[str, str]] = {}
    refs: dict[str, str] = {}        # rel -> 原始 path
    new_lines = []
    for line in lines:
        k = line.find("\\sphinxincludegraphics")
        if k < 0:
            new_lines.append(line)
            continue
        start = line.find("{", k)
        if start < 0:
            new_lines.append(line)
            continue
        depth, end = 0, -1
        for pos in range(start, len(line)):
            if line[pos] == "{":
                depth += 1
            elif line[pos] == "}":
                depth -= 1
                if depth == 0:
                    end = pos
                    break
        if end < 0:
            new_lines.append(line)
            continue
        arg = line[start + 1:end]
        path = arg.replace("{", "").replace("}", "").replace("\\", "/").strip()
        if re.fullmatch(r"wns_img_\d+\.[A-Za-z0-9]+", path):
            new_lines.append(line)      # 已改写，幂等
            continue
        rel = os.path.normpath(os.path.join("Doc", path)).replace("\\", "/")
        refs[rel] = path
        ext = pathlib.Path(rel).suffix or ".png"
        if rel not in mapping:
            mapping[rel] = ("wns_img_%d" % len(mapping), ext)
        base, _ = mapping[rel]
        # 保持 Sphinx 的 {{basename}.ext} 结构，只换 basename
        newline = line[:start + 1] + "{" + base + "}" + ext + line[end:]
        new_lines.append(newline)

    if not refs:
        log("图片依赖齐全（本册无图片引用）")
        return
    missing = sorted(r for r in refs if not (root / r).is_file())
    if missing:
        log("补下载 %d 个缺失图片依赖：%s" % (len(missing), missing[:3]))
        download_all([(CPY_REPO, branch, r, root) for r in missing],
                     mirrors, workers=5, progress=False)
    for rel, (base, ext) in mapping.items():
        src = root / rel
        if not src.is_file():
            raise RuntimeError("图片无法下载，XeLaTeX 会失败：%s" % rel)
        shutil.copy2(src, outlatex / (base + ext))
    tex.write_text("".join(new_lines), encoding="utf-8")
    log("图片已就位并改写 tex 路径：%d 个引用 → %s"
        % (len(refs), ", ".join(b + e for b, e in mapping.values())))


def patch_index_style(outlatex: pathlib.Path, tex: pathlib.Path):
    """修复索引页三个排版问题。

    1) Sphinx 自带 python.ist 不含 delim_*/delim_t，makeindex 输出纯数字页码；
       而 .tex 又设了 hyperindex=false（为绕开 xindy 兼容问题），所以页码
       不是蓝色超链接。这里让 makeindex 把页码整体包进 \\hyperpage{...}，
       与 Sphinx 的 xindy 输出一致，hyperref 会为每个页码生成链接。
    2) 双栏 theindex 两端对齐 + 超长英文项 → LaTeX 强行拉伸字距、越过中线。
       在 theindex 开始时启用 \\raggedright / \\sloppy / emergencystretch。
    3) sphinxlatexstyletext.sty 把索引项定义为 \\texttt{#1}，中文只能落到
       CJK 等宽字体，缺字即显示黑问号；改为不切字体的正常罗马体。
    """
    # --- 1) .ist：页码超链接 + 关闭按字节分组 + 防止折行切断汉字 ---
    ist = outlatex / "python.ist"
    if ist.is_file():
        s = ist.read_text(encoding="utf-8", errors="replace")
        # makeindex 按字节给中文条目做「字母分组」，会写出
        # `\bigletter \xe7`（「环」的 UTF-8 首字节），渲染成黑色菱形/问号，
        # 还会让 .ind 变成非法 UTF-8。关掉分组标题即可根治。
        s = re.sub(r"(?m)^headings_flag\s+\d+", "headings_flag 0", s)
        # line_max 100 按字节折行，可能在多字节汉字中间断开。
        s = re.sub(r"(?m)^line_max\s+\d+", "line_max 1000", s)
        if "delim_t" not in s:
            s += ('\ndelim_0 ", \\\\hyperpage{"\n'
                  'delim_1 ", \\\\hyperpage{"\n'
                  'delim_2 ", \\\\hyperpage{"\n'
                  'delim_t "}"\n')
        ist.write_text(s, encoding="utf-8")
        log("python.ist：页码 \\hyperpage 链接 / 关闭字节分组 / line_max 1000")

    # --- 2/3) .tex：索引排版与字体 ---
    t = tex.read_text(encoding="utf-8", errors="replace")
    marker = "% ==== whatsnew-studio index fixes ===="
    end = "% ==== whatsnew-studio index fixes end ===="
    # 幂等：优先按起止标记精确移除，避免连带删掉相邻的 toc 注入块；
    # 兼容早期版本（无结束标记）生成的 .tex。
    if end in t:
        t = re.sub(re.escape(marker) + r".*?" + re.escape(end) + r"\s*",
                   "", t, count=1, flags=re.S)
    elif marker in t:
        t = re.sub(re.escape(marker) + r".*?(?=\\begin\{document\})", "", t,
                   count=1, flags=re.S)
    if marker not in t:
        inject = marker + r"""
\usepackage{etoolbox}
\AtBeginEnvironment{theindex}{\raggedright\sloppy\setlength{\emergencystretch}{3em}}
\def\sphinxstyleindexentry#1{#1}
\def\sphinxstyleindexpagemain#1{#1}
\renewcommand{\sphinxsymbolsname}{符号}
\renewcommand{\sphinxnumbersname}{数字}
% 链接色不再覆盖：统一用 Sphinx 默认的 InnerLinkColor =
% rgb(0.208,0.374,0.486)（#355f7c 深蓝灰），目录、正文交叉引用和
% 索引页码同色，与官方 PDF 一致。
% 交接：不要改成 \color{blue} 或覆盖 \hypersetup{linkcolor=...}；
% 目录条目本身是超链接，全局改色会把整条标题染蓝（见 README 8.4 / 12.3）。
""" + end + "\n"
        if r"\begin{document}" not in t:
            raise RuntimeError("找不到 \\begin{document}，无法注入索引修复")
        t = t.replace(r"\begin{document}",
                      inject + "\n\\begin{document}", 1)
        log("已注入索引排版修复（左对齐/宽松断行/去等宽字体/中文组标题）")

    tex.write_text(t, encoding="utf-8")

    # 样式与 .tex 都变了，删掉旧 .ind 强制 makeindex 重新生成
    ind = outlatex / (tex.stem + ".ind")
    if ind.is_file():
        ind.unlink()
        log("已清除旧 .ind，makeindex 将重新生成")


def patch_toc_depth(tex: pathlib.Path, toc_depth: int = DEFAULT_TOC_DEPTH,
                    bookmark_depth: int = DEFAULT_BOOKMARK_DEPTH,
                    toc_baselineskip: str | None = None):
    r"""让正文目录（Contents）与 PDF 书签的层级可配置。

    Sphinx 官方 conf.py、sphinxmanual.cls 以及我们的 override 会各写一次
    `\setcounter{tocdepth}`；最后生效的那个（以前固定为 1）把目录压成
    「章 / 节」两级。这里在 .tex 层面统一改成目标值，比改 conf.py 更可靠，
    也能让 --latex-only 续跑直接用上新设置。官方单版本册的基线是 tocdepth=2，
    本程序默认正文 3 级 → 减 1 后正好同为 2（见 README 12.1）。

    bookmarksdepth 由 \PassOptionsToPackage 在 \usepackage{hyperref} 前给出，
    与 tocdepth 独立：即使正文目录只到 2 级，侧边栏书签仍可保留 5 级。
    """
    toc_depth = max(2, min(5, int(toc_depth)))
    bookmark_depth = max(3, min(6, int(bookmark_depth)))
    s = tex.read_text(encoding="utf-8", errors="replace")
    head, sep, body = s.partition(r"\begin{document}")
    if not sep:
        raise RuntimeError("找不到 \\begin{document}，无法设置目录层级")

    # 1) 导言区所有 tocdepth 设置统一（避免被后面某处覆盖回去）
    n = len(re.findall(r"\\setcounter\{tocdepth\}\{\d+\}", head))
    head = re.sub(r"\\setcounter\{tocdepth\}\{\d+\}",
                  r"\\setcounter{tocdepth}{%d}" % (toc_depth - 1), head)
    # 2) PDF 书签层级
    head = re.sub(r"bookmarksdepth=\d+",
                  "bookmarksdepth=%d" % bookmark_depth, head)

    # 3) 幂等清理上一次注入块（精确起止标记，不碰相邻 index 修复块）
    begin = "% ==== whatsnew-studio toc begin ===="
    end = "% ==== whatsnew-studio toc end ===="
    head = re.sub(re.escape(begin) + r".*?" + re.escape(end) + r"\s*",
                  "", head, count=1, flags=re.S)

    # 4) 目录条目排版：各级缩进/编号宽度重新给足，长中文标题允许折行。
    #    \@dottedtocline 含 @，必须包在 \makeatletter 里；\sloppy 作用于
    #    \sphinxtableofcontents 的 \begingroup 内，只影响目录页。
    inject = begin + r"""
\makeatletter
\renewcommand{\sphinxtableofcontentshook}{%
  \renewcommand*\l@section{\@dottedtocline{1}{1.5em}{2.9em}}%
  \renewcommand*\l@subsection{\@dottedtocline{2}{4.4em}{4.3em}}%
  \renewcommand*\l@subsubsection{\@dottedtocline{3}{8.7em}{5.3em}}%
  \renewcommand*\l@paragraph{\@dottedtocline{4}{13.2em}{5.6em}}%
  \sloppy\setlength{\emergencystretch}{2em}%"""
    if toc_baselineskip:
        inject += "\n  \\setlength{\\baselineskip}{%s}%%" % toc_baselineskip
    inject += r"""
}
\makeatother
""" + end + "\n"
    head += "\n" + inject
    tex.write_text(head + sep + body, encoding="utf-8")
    log("目录层级：正文 %d 级（tocdepth=%d，统一 %d 处设置）；PDF 书签 %d 级"
        % (toc_depth, toc_depth - 1, n, bookmark_depth))


def patch_tex_chapters(tex: pathlib.Path, docs: list[str], include_index: bool,
                       promote: bool = False):
    r"""正文保留官方中文标题、PDF 一级书签用 po 名；按需保留 \printindex。

    promote=True 用于 changelog 独立册：总章马上会被移除、小版本提升为章，
    此时不能再把第一个 chapter 的书签写成「更新历史记录」。
    """
    s = tex.read_text(encoding="utf-8", errors="replace")
    if promote:
        result = s
        n = 0
        log("changelog 册：总章将移除，各补丁版本提升为一级书签")
    else:
        ms = list(re.finditer(r"\\chapter\{([^{}]*)\}", s))
        if len(ms) < len(docs):
            log("  [警告] \\chapter 数 %d < 章节数 %d" % (len(ms), len(docs)))
        out, last, n = [], 0, 0
        for m in ms[:len(docs)]:
            name = "更新历史记录" if docs[n] == "changelog" else docs[n]
            out.append(s[last:m.start()])
            out.append("\\chapter{\\texorpdfstring{%s}{%s}}" % (m.group(1), name))
            last = m.end()
            n += 1
        out.append(s[last:])
        result = "".join(out)
    if not include_index:
        result = result.replace(r"\printindex",
                                "% \\printindex (disabled by whatsnew-studio)")
    tex.write_text(result, encoding="utf-8")
    if not promote:
        log("已设置 %d 个一级书签；术语索引页：%s"
            % (n, "保留" if include_index else "禁用"))


# ---- changelog 独立册：小版本提升为一级章节 -------------------------------
PROMOTE_MARK = "% ==== whatsnew-studio changelog promoted ===="
HDR_BEGIN = "% ==== whatsnew-studio changelog headers begin ===="
HDR_END = "% ==== whatsnew-studio changelog headers end ===="
CLEAR_IDX_MARK = "% ==== whatsnew-studio index pagebreak ===="


def promote_changelog_structure(tex: pathlib.Path, compact: bool = True,
                                footer: str = "page", tight: bool = True):
    r"""让「仅完整更新日志」册的每个补丁版本成为一级目录，索引与其同级。

    Sphinx 把 changelog.rst 编成 `\chapter{更新日志}`，里面的每个
    "What's New in Python 3.10.x ...?" 只是 `\section`。这里在 .tex 层：
      1) 去掉总章（目录/书签里不再有「更新历史记录」这一层）；
      2) section→chapter、subsection→section … 逐级上提，正文编号、
         目录层级和 PDF 书签随之整体变化；
      3) 页眉页脚跟随新的章：默认 \rightmark 会被分类小节覆盖，改为
         让左右页脚都显示当前补丁版本。
    compact=True 时再给 \chapter 去掉强制分页，让小版本连续排；
    compact=False 保留每版另起一页。两种模式都消除 openright 造成的空白页。
    只改 LaTeX 命令、不换 docname，因此中文 po 的译文全部保留。
    幂等：注入的标记可防止 --latex-only / --skip-download 续跑重复提升。
    """
    s = tex.read_text(encoding="utf-8", errors="replace")
    head, sep, body = s.partition(r"\begin{document}")
    if not sep:
        raise RuntimeError("找不到 \\begin{document}，无法提升 changelog 层级")

    # 1) 导言区：页眉页脚 + 分页策略（每次按当前开关重注入）
    head = re.sub(re.escape(HDR_BEGIN) + r".*?" + re.escape(HDR_END) + r"\s*",
                  "", head, count=1, flags=re.S)
    flow = r"""
% 补丁版本提升为章后，页脚左右都显示当前补丁版本；默认的 \rightmark
% 会被分类小节覆盖，这里让它保持章名。页眉仍是官方的书名 + 发行版本。
\providecommand{\sectionmark}[1]{}
\renewcommand{\sectionmark}[1]{}
\renewcommand{\chaptermark}[1]{\markboth{\thechapter\enspace #1}{\thechapter\enspace #1}}
% 章默认 \clearpage，openright 下还会 \cleardoublepage：目录之后和每章
% 之前都会因此留下空白页。统一降级成普通分页。
\let\cleardoublepage\clearpage
"""
    if compact:
        flow += r"""
\makeatletter
% 小版本连续排版：章不强制换页，标题紧凑，
% 版式对齐官方 whatsnew.pdf（章 14.4pt / 节 12pt / 正文 10pt，标题深蓝）。
\renewcommand\chapter{%
  \par\global\@topnum\z@
  \@afterindentfalse
  \secdef\@chapter\@schapter}
\titleformat{\section}{\large\py@HeaderFamily}%
            {\py@TitleColor\thesection}{0.5em}{\py@TitleColor}
"""
        # 正文间距固定按官方 whatsnew.pdf 的实测值，不随开关变化：
        # 段落间距 6pt、章标题前 18pt、节标题前 14pt / 后 8pt。
        flow += r"""
\AtBeginDocument{\setlength{\parskip}{6pt plus 1pt minus 1pt}}
\titlespacing*{\section}{0pt}{1.4em}{0.8em}
\titlespacing*{\subsection}{0pt}{1.2em}{0.6em}
\renewcommand\@makechapterhead[1]{%
  \vspace{1.8em plus .4em minus .2em}%
  {\parindent\z@\raggedright\normalfont\interlinepenalty\@M
   \py@HeaderFamily\bfseries\Large\py@TitleColor \thechapter\enspace #1\par\nobreak}%
}
\renewcommand\@makeschapterhead[1]{%
  \vspace{1.8em plus .4em minus .2em}%
  {\parindent\z@\raggedright\normalfont\interlinepenalty\@M
   \py@HeaderFamily\bfseries\Large\py@TitleColor #1\par\nobreak}%
}
"""
        if tight:
            # 只处理封面与目录的空白：封面不再用 titlepage（不自动分页、
            # 不用 \vfill 撑满），目录紧接在封面下方开始，消除封面下方空白。
            flow += r"""
\renewcommand{\sphinxmaketitle}{%
  \noindent\rule{\textwidth}{1pt}\par
  \begingroup
    \def\endgraf{ }\def\and{\& }%
    \pdfstringdefDisableCommands{\def\\{, }}%
    \hypersetup{pdfauthor={\@author}, pdftitle={\@title}}%
  \endgroup
  \begin{flushright}%
    \py@HeaderFamily
    {\Huge \@title \par}%
    {\itshape\LARGE \py@release\releaseinfo \par}%
    \vspace{1.2em}%
    {\LARGE \@author \par}%
    \vspace{0.5em}%
    {\large \@date \par}%
    \py@authoraddress \par
  \end{flushright}%
  \vspace{1em}%
}
% 目录结束后不再强制分页：正文直接接在目录末页的剩余空间里，
% 目录行距保持默认，不压缩。页码不再切 roman，从封面页起连续编号。
\renewcommand{\sphinxtableofcontents}{%
  \begingroup
    \parskip \z@skip
    \sphinxtableofcontentshook
    \tableofcontents
  \endgroup
  % 目录结束、正文开始之间的分隔线（0.4pt，通栏）
  \par\noindent\rule{\textwidth}{0.4pt}\par
  \vspace{0.8em}%
}
% 页脚不画线（plain / normal 都是 0），目录与正文之间的分隔线
% 在 \sphinxtableofcontents 结束时单独画一条。
\fancypagestyle{plain}{%
  \fancyhf{}%
  \fancyfoot[C]{\py@HeaderFamily\thepage}%
  \renewcommand{\headrulewidth}{0pt}%
  \renewcommand{\footrulewidth}{0pt}%
}
"""
        # 页脚：默认只保留页码，无横线；footer="chapter" 时右侧再加一级目录名
        # （一页跨章按本页最后一个章算）。书名始终不加。
        flow += r"""
\fancypagestyle{normal}{%
  \fancyhf{}%
  \fancyfoot[C]{\py@HeaderFamily\thepage}%
"""
        if footer == "chapter":
            flow += r"""  \fancyfoot[R]{\py@HeaderFamily\small\nouppercase{\leftmark}}%
"""
        flow += r"""  \renewcommand{\headrulewidth}{0pt}%
  \renewcommand{\footrulewidth}{0pt}%
}
\makeatother
"""
    head += "\n" + HDR_BEGIN + flow + HDR_END + "\n"

    # 2) 正文层级提升（幂等）
    if PROMOTE_MARK not in body:
        body, removed = re.subn(r"(?m)^\\chapter\{[^\n]*\}\s*\n", "", body, count=1)
        mapping = {"section": "chapter", "subsection": "section",
                   "subsubsection": "subsection", "paragraph": "subsubsection"}

        def lift(m):
            return "\\" + mapping[m.group(1)] + m.group(2) + "{"

        body, lifted = re.subn(
            r"\\(section|subsection|subsubsection|paragraph)(\*?)\{", lift, body)
        body = PROMOTE_MARK + "\n" + body
        log("changelog 层级提升：移除总章 %d 个，上提 %d 个标题"
            "（补丁版本 → 一级章，分类 → 小节）" % (removed, lifted))

    # 2b) blurb 的分类标题是英文硬编码（不进 po），统一译成中文；
    #     Windows / macOS / IDLE / C API 这类专有名词保留原文。
    CATEGORY_ZH = {
        "Security": "安全性",
        "Core and Builtins": "核心与内置函数",
        "Library": "库",
        "Extension Modules": "扩展模块",
        "Documentation": "文档",
        "Tests": "测试",
        "Build": "构建",
        "Tools/Demos": "工具/示例",
        "New Features": "新特性",
        "Other Language Changes": "其他语言特性修改",
        "Improved Modules": "改进的模块",
        "New Modules": "新增模块",
        "Deprecated": "已弃用",
        "Removed": "已移除",
        "Performance": "性能优化",
        "Networking": "网络",
        "Internationalization": "国际化",
    }

    def zh_head(m):
        return "\\%s{%s}" % (m.group(1), CATEGORY_ZH.get(m.group(2), m.group(2)))

    body = re.sub(r"\\(chapter|section)\{([^}]*)\}", zh_head, body)
    body = re.sub(r"\\(chapter|section)\{Porting to Python ([0-9.]+)\}",
                  r"\\\1{移植到 Python \2}", body)

    # 3) compact 下章不再自动分页，索引前补一次分页，避免索引紧贴正文
    if compact and CLEAR_IDX_MARK not in body:
        body = re.sub(
            r"(?m)^\\printindex\b",
            CLEAR_IDX_MARK + "\n\\\\clearpage\n\\\\printindex",
            body, count=1)
    tex.write_text(head + sep + body, encoding="utf-8")


def latexmk(outlatex: pathlib.Path, tex: pathlib.Path, force_clean: bool = False):
    # -f 跑完整循环；-g 忽略 .fdb_latexmk 的 "up-to-date" 判定；续跑时用
    # -gg 先清理再全量重编，否则上次的坏 .xdv 不会重建（缺图造成的
    # graphics Division by 0 会一直留在里面，xdvipdfmx 反复失败）。
    flag = "-gg" if force_clean else "-g"
    r = run(["latexmk", "-xelatex", "-interaction=nonstopmode", "-f", flag,
             "-file-line-error",
             "-e", "$makeindex = q/makeindex -s python.ist %O -o %D %S/;",
             tex.name], cwd=outlatex, timeout=7200,
            extra_env={"LC_ALL": "C", "LANG": "C"})
    pdf = outlatex / (tex.stem + ".pdf")
    if not pdf.is_file() or pdf.stat().st_size < 100_000:
        raise RuntimeError("latexmk 未产出有效 PDF：\n" +
                           (r.stdout or "")[-3000:] + "\n" + (r.stderr or "")[-1200:])
    # xdvipdfmx 中断时会留下无 trailer 的截断 PDF；只看文件大小会误判成功。
    tail = b""
    with open(pdf, "rb") as f:
        f.seek(max(0, pdf.stat().st_size - 8192))
        tail = f.read()
    if b"%%EOF" not in tail or b"startxref" not in tail:
        raise RuntimeError(
            "PDF 不完整（缺 %%EOF/startxref），xdvipdfmx 转换中断。\n"
            "常见原因：缺图片导致 graphics Division by 0。请查看 %s\n%s"
            % (outlatex / (tex.stem + ".log"),
               (r.stdout or "")[-1500:]))
    log("latexmk 完成：%.2f MB（PDF 结构完整）" % (pdf.stat().st_size / 1048576))
    return pdf


# ---------------------------------------------------------------- 主流程
def build(cfg):
    """串起九个构建阶段；GUI 与命令行共用本函数，保证产物一致。

    复现要点：work/build_<mode>_<ver>/ 是唯一中间目录；--skip-download 复用
    已下载文件，--latex-only 复用 .tex。改版式时优先删 .tex 再 --latex-only，
    不要直接手改 work 下的 conf.py/.tex（下次构建会覆盖）。
    """
    ver, mode = cfg["version"], cfg["mode"]
    # ★ 必须绝对化：Sphinx / latexmk 都以 cwd=<别的目录> 起子进程，而传过去的
    #   outlatex 若是相对路径，会被子进程按它的 cwd 解析 —— 于是 .tex 写进了
    #   Doc/changelog-work/... 而我们回仓库根找 work/... ，表现成「Sphinx 未产出 .tex」。
    #   本机测试习惯传绝对路径，所以这个坑只在 CI（传 relative --outdir/--workdir）暴露。
    work = pathlib.Path(cfg["workdir"]).resolve()
    outdir = pathlib.Path(cfg["outdir"]).resolve()
    root = work / ("build_%s_%s" % (mode, ver.replace(".", "_")))
    doc = root / "Doc"
    po_root = root / "zh_po"
    outlatex = root / "out" / "latex"
    root.mkdir(parents=True, exist_ok=True)

    zh_branch, cpy_branch = resolve_branches(ver)
    ref_kind = "归档标签 tag" if is_cpy_tag(ver) else "分支 branch"
    log("版本 %s ｜ 模式 %s ｜ 中文译文 python-docs-zh-cn@%s ｜ "
        "CPython 源文/脚手架 cpython@%s（%s）"
        % (ver, mode_label(mode), zh_branch, cpy_branch, ref_kind))
    log("索引页：%s" % ("包含" if cfg["include_index"] else "不包含"))

    step("检测加速镜像", 2)
    # ★ 副本新增：显式指定镜像时**不再探测**，就只用那一个。
    #   CI 里传 `--mirror 直连`，语义就是「只用官网 raw.githubusercontent」，
    #   不必先花 15 秒去试 ghproxy/jsDelivr（runner 上那两个还常常不可用）。
    if cfg["mirror"] != "auto":
        mirrors = [cfg["mirror"]]
        log("镜像：%s（已显式指定，不探测）" % cfg["mirror"])
    else:
        mirrors = probe_mirrors(list(MIRRORS), cpy_branch)
    if not mirrors:
        raise RuntimeError("没有可用的下载镜像")

    if cfg.get("latex_only"):
        # 调试/续跑：复用已生成的 .tex，只补图片依赖并重编 LaTeX
        tex = outlatex / "whatsnew_all.tex"
        if not tex.is_file():
            raise RuntimeError("找不到已生成的 .tex：" + str(tex))
        step("补齐图片依赖", 60)
        ensure_graphics(root, tex, cpy_branch, mirrors)
        if cfg["include_index"]:
            patch_index_style(outlatex, tex)
        patch_toc_depth(tex, cfg.get("toc_depth", DEFAULT_TOC_DEPTH),
                        cfg.get("bookmark_depth", DEFAULT_BOOKMARK_DEPTH),
                        None)
        if mode == "changelog":
            promote_changelog_structure(
                tex, compact=cfg.get("changelog_flow", "continuous") == "continuous",
                footer=cfg.get("changelog_footer", "page"),
                tight=cfg.get("changelog_spacing", "tight") == "tight")
        step("XeLaTeX 编译 PDF", 71)
        pdf = latexmk(outlatex, tex, force_clean=True)
        outdir.mkdir(parents=True, exist_ok=True)
        name = output_title(ver, mode) + ".pdf"
        final = outdir / name
        shutil.copy2(pdf, final)
        emit("PCT", "100")
        emit("DONE", str(final))
        log("输出：%s（%.2f MB）" % (final, final.stat().st_size / 1048576))
        return final

    if cfg.get("skip_download"):
        log("复用上次下载的文件（--skip-download），跳过下载阶段")
        if not any((po_root / "whatsnew").glob("*.po")):
            raise RuntimeError("没有可复用的中文 po，请先完整构建一次")
        emit("PCT", "26")
    else:
        step("列出官网文件清单", 4)
        tree = github_tree(CPY_REPO, cpy_branch)
        tree_set = set(tree)
        scaffold = [p for p in tree
                    if p.startswith(SCAFFOLD_PREFIXES)
                    or (p in SCAFFOLD_FILES and p in tree_set)]
        zh_list = zh_po_paths(zh_branch, ver)
        log("CPython 需下载 %d 个文件；中文 whatsnew po %d 个"
            % (len(scaffold), len(zh_list)))
        items = ([(CPY_REPO, cpy_branch, p, root) for p in scaffold]
                 + [(ZH_REPO, zh_branch, p, po_root) for p in zh_list])

        step("从官网下载 whatsnew 相关文件", 5)
        fails = download_all(items, mirrors, workers=10)
        if not any((po_root / "whatsnew").glob("*.po")):
            raise RuntimeError("中文 po 下载失败，无法继续")
        log("下载完成（失败 %d 个）" % fails)
        # 下载器把「该分支没有这个文件」和「网络失败」都算进 fails，所以不能一律失败；
        # 但骨架文件缺了就一定编不出来，早点给出人话，别让它拖到 Sphinx 才报
        # FileNotFoundError: conf.py（那种报错看不出是下载没下全）。
        skeleton = [doc / "conf.py", doc / "tools" / "extensions"]
        lost = [p.name for p in skeleton if not p.exists()]
        if lost or not any((doc / "tools" / "extensions").glob("*.py")):
            raise RuntimeError(
                "下载不完整：缺 %s（失败 %d 个文件）。换个 --mirror 重跑即可，"
                "已下好的文件会复用。" % (lost or ["tools/extensions/*.py"], fails))
        emit("PCT", "26")

    step("生成变更日志数据", 27)
    prepare_news(root, ver, mode, is_cpy_tag(ver))
    emit("PCT", "32")

    step("编译中文译文", 33)
    install_locales(po_root, doc)
    emit("PCT", "38")

    step("准备 Sphinx 工程", 39)
    # 官方 conf.py 有 `os.listdir('howto')`（用于生成 howto 分册列表）。
    # 本册不下载 howto 内容，建空目录让它返回 []；随后 latex_documents 会被
    # 覆盖为单条目，这一步的结果不会进入最终构建。
    (doc / "howto").mkdir(exist_ok=True)
    rst_names = {p.stem for p in (doc / "whatsnew").glob("*.rst")}
    docs, all_names = choose_docs(po_root, mode, ver, rst_names)
    log("章节：%s" % ", ".join(docs))
    patch_index_rst(doc)
    write_root_doc(doc, docs, mode, ver)
    patch_conf(doc, docs, ver, mode,
               cfg.get("toc_depth", DEFAULT_TOC_DEPTH), cpy_branch)
    emit("PCT", "43")

    step("Sphinx 生成 LaTeX", 44)
    sphinx_env = legacy_sphinx_env(cfg["workdir"]) if is_cpy_tag(ver) else None
    log("Sphinx：%s" % ("隔离的 8.2.3（归档标签）" if sphinx_env else "系统版本 9.x"))
    if is_cpy_tag(ver) and sphinx_env is None:
        log("  [提示] 用系统 Sphinx + conf.py 兼容垫片也能编；如需 8.2.3："
            "python -m pip install --target work/sphinx82 sphinx==8.2.3")
    tex = sphinx_latex(doc, outlatex, sphinx_env)
    emit("PCT", "68")
    ensure_graphics(root, tex, cpy_branch, mirrors)
    if cfg["include_index"]:
        patch_index_style(outlatex, tex)
    patch_toc_depth(tex, cfg.get("toc_depth", DEFAULT_TOC_DEPTH),
                    cfg.get("bookmark_depth", DEFAULT_BOOKMARK_DEPTH),
                    None)
    patch_tex_chapters(tex, docs, cfg["include_index"],
                       promote=(mode == "changelog"))
    if mode == "changelog":
        promote_changelog_structure(
            tex, compact=cfg.get("changelog_flow", "continuous") == "continuous",
            footer=cfg.get("changelog_footer", "page"),
            tight=cfg.get("changelog_spacing", "tight") == "tight")
    emit("PCT", "70")

    step("XeLaTeX 编译 PDF", 71)
    pdf = latexmk(outlatex, tex)
    emit("PCT", "96")

    outdir.mkdir(parents=True, exist_ok=True)
    name = output_title(ver, mode) + ".pdf"
    final = outdir / name
    shutil.copy2(pdf, final)
    if not cfg.get("keep_work"):
        log("中间产物保留在 %s" % root)
    emit("PCT", "100")
    emit("DONE", str(final))
    log("输出：%s（%.2f MB）" % (final, final.stat().st_size / 1048576))
    return final


def main():
    """命令行入口。这里的默认值就是复现基线（README 4.2 / 12.2）。

    whatsnew_gui.py 必须传齐同名参数，不能只在界面上“看起来一样”；
    任何新增参数都要同步补进 GUI 的 args 列表和 README 参数表。
    """
    ap = argparse.ArgumentParser(description="whatsnew Studio 构建核心")
    ap.add_argument("--version", default="3.15",
                    help="版本号 3.x（>= 3.7；未来 3.16 / 3.17 等直接写版本号即可）")
    ap.add_argument("--mode", default="full",
                    choices=("full", "single", "changelog"),
                    help="full=全集 / single=单版本册 / changelog=仅完整更新日志")
    ap.add_argument("--no-index", action="store_true")
    ap.add_argument("--toc-depth", type=int, default=DEFAULT_TOC_DEPTH,
                    choices=TOC_DEPTHS,
                    help="正文目录层级：2=章/节 3=+小节 4=+子小节 5=+段落标题（默认 3）")
    ap.add_argument("--bookmark-depth", type=int, default=DEFAULT_BOOKMARK_DEPTH,
                    choices=BOOKMARK_DEPTHS,
                    help="PDF 侧边栏书签层级（默认 5，与正文目录独立）")
    ap.add_argument("--mirror", default="auto", choices=["auto"] + list(MIRRORS))
    ap.add_argument("--outdir", default=str(HERE / "output"))
    ap.add_argument("--workdir", default=str(HERE / "work"))
    ap.add_argument("--keep-work", action="store_true")
    ap.add_argument("--latex-only", action="store_true",
                    help="复用已生成的 .tex，只补图片依赖并重编 LaTeX（调试用）")
    ap.add_argument("--skip-download", action="store_true",
                    help="复用上次下载的文件，跳过下载（改了译文/参数后续跑用）")
    ap.add_argument("--changelog-flow", default="continuous",
                    choices=("continuous", "page"),
                    help="更新日志册排版：continuous=小版本连续排（默认），"
                         "page=每个小版本另起一页")
    ap.add_argument("--changelog-footer", default="page",
                    choices=("page", "chapter"),
                    help="更新日志册页脚：page=只页码（默认），"
                         "chapter=页码 + 当前一级目录名")
    ap.add_argument("--changelog-spacing", default="tight",
                    choices=("tight", "normal"),
                    help="更新日志册间距：tight=按官方 PDF 压紧标题/目录/正文（默认），"
                         "normal=保留原有空白")
    a = ap.parse_args()
    cfg = {"version": a.version, "mode": a.mode,
           "include_index": not a.no_index, "mirror": a.mirror,
           "outdir": a.outdir, "workdir": a.workdir, "keep_work": a.keep_work,
           "latex_only": a.latex_only, "skip_download": a.skip_download,
           "changelog_flow": a.changelog_flow,
           "changelog_footer": a.changelog_footer,
           "changelog_spacing": a.changelog_spacing,
           "toc_depth": a.toc_depth, "bookmark_depth": a.bookmark_depth}
    try:
        build(cfg)
    except Exception as e:  # noqa: BLE001
        emit("FAIL", "%s: %s" % (type(e).__name__, e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
