# -*- coding: utf-8 -*-
"""更新日志册构建器（取自 whatsnew-studio，本仓库只用于 CI）。

从 GitHub 官方仓库下载 whatsnew 相关文件（cpython 的 Misc/NEWS.d +
python-docs-zh-cn 的 changelog.po），用官方 Sphinx + LaTeX 路线编出
「Python 3.x 完整更新日志」PDF。stdout 用 @@STEP@@ / @@LOG@@ / @@PCT@@ /
@@DONE@@ / @@FAIL@@ 输出结构化进度。

CI 的调用方式（一个版本一个 job）：

    python ci/changelogs/builder.py --version 3.11 --mode changelog \\
        --outdir changelog-out --workdir changelog-work --mirror 直连
"""
# ===== 与 whatsnew-studio/builder.py 的差异（同步时重新覆盖后改回来）=====
#   1) PY 默认用 sys.executable、TEXBIN 取 WNS_TEXBIN（不存在则置空走 PATH）；
#   2) http_get 对 api.github.com 带 GITHUB_TOKEN（匿名 60 次/小时，CI 必 403）；
#   3) 显式 --mirror 时不探测（CI 传「直连」＝只用官网 raw）；
#   4) workdir/outdir 与交给子进程的路径一律绝对化 —— 子进程 cwd=Doc，
#      相对路径会被它按 Doc 解析，.tex 就写进 Doc/ 底下（CI 传相对路径必踩）；
#   5) 删掉本仓库用不到的入口：GUI 常量、3.7–3.10 归档标签、full/single 两种
#      模式、--no-index / --keep-work / --latex-only / 排版开关（版式固定为出厂基线）。
from __future__ import annotations

import argparse
import concurrent.futures
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

HERE = pathlib.Path(__file__).resolve().parent
PY = os.environ.get("WNS_PY") or sys.executable
TEXBIN = os.environ.get("WNS_TEXBIN", "")
# 没有显式指定、或指定的目录不存在时置空：run() 不往 PATH 塞空段（空段=当前目录）。
if not os.path.isdir(TEXBIN):
    TEXBIN = ""

# python-docs-zh-cn 从 3.7 才有分支，但 3.7–3.10 在 cpython 里是归档 tag、
# 且已从本仓库的册列表里移出，这里只出 3.11 及以后（3.16+ 直接写版本号即可）。
MIN_MINOR = 11

# 正文目录层级：1=章 2=节 3=小节…；LaTeX 的 tocdepth 比它小 1（chapter 记为 0），
# 3 级正好落成官方基线的 tocdepth=2。
TOC_DEPTH = 3
# PDF 阅读器侧边栏书签层级，与正文目录互不影响。
BOOKMARK_DEPTH = 5

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


def check_version(ver: str):
    if not re.fullmatch(r"3\.\d+", ver or ""):
        raise ValueError("版本号格式应为 3.x（例如 3.11、3.16）：%r" % ver)
    if int(ver.split(".")[1]) < MIN_MINOR:
        raise ValueError("只出 3.%d 及以后（3.7–3.10 已归档，册列表里也没有）"
                         % MIN_MINOR)


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


def probe_mirrors(order: list[str]) -> list[str]:
    """按实测延迟排序可用镜像；不可用的排到最后。"""
    probe = ("Doc/whatsnew/index.rst", CPY_REPO, "3.15")
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
    """列出该分支 whatsnew 下的 po（优先目录 API，失败用候选名 + 404 跳过）。

    兜底名单跟着版本走：不写死到 3.15，将来 3.16 的 po 才不会被漏掉。
    """
    try:
        d = json.loads(http_get(
            "https://api.github.com/repos/%s/contents/whatsnew?ref=%s" % (ZH_REPO, branch),
            timeout=40))
        if isinstance(d, list):
            return sorted("whatsnew/" + x["name"] for x in d if x["name"].endswith(".po"))
    except Exception:
        pass
    top = 20
    if version and re.fullmatch(r"3\.\d+", version):
        top = max(top, int(version.split(".")[1]))
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

    必须取对应 ref：较新分支的 Misc/NEWS.d/ 只留当前系列，例如 3.15 分支里
    3.11 只剩 3.11.0 的 alpha/beta 8 节，而 3.11 分支有 3.11.0–3.11.18 全部条目。
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


def prepare_news(root: pathlib.Path, version: str):
    """用该 ref 自己的 Misc/NEWS.d 生成 build/NEWS，再按大版本过滤。"""
    doc = root / "Doc"
    out = doc / "build" / "NEWS"
    out.parent.mkdir(parents=True, exist_ok=True)
    r = run([PY, "-m", "blurb", "merge", "-f", "Doc/build/NEWS"],
            cwd=root, timeout=900)
    if not out.is_file():
        raise RuntimeError("blurb 生成 NEWS 失败：" + (r.stderr or r.stdout)[-1200:])
    full = out.read_text(encoding="utf-8", errors="replace")
    log("build/NEWS 生成：%.2f MB" % (len(full) / 1048576))
    filter_news(full, version, out)


def normalize_release_terms(cat):
    """补齐中文 changelog 里仍未统一的版本标题术语（未翻译/照抄英文的条目）。

    3.11+ 的译稿大多已把 "Python 3.x.y final" 译为「正式版」、rcN 译为
    「候选发布版 N」；个别补丁版的 msgstr 仍空着。这里只在编译 .mo 前于内存里
    补，不改下载的 po，已有其它中文译法的一律保留。
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


def output_title(version: str) -> str:
    """册名，同时用作 PDF 标题、元数据和输出文件名。"""
    return "Python %s 完整更新日志" % version


def choose_docs(po_root: pathlib.Path, rst_names: set[str] | None = None):
    """章节清单 = 中文 po ∩ 该 CPython ref 实际存在的 whatsnew/*.rst。

    必须取交集：3.11 分支里没有 3.15.rst，不筛就会引用不存在的文档。
    本册只编 changelog 一页（不含 whatsnew 正文）。
    """
    names = sorted((p.stem for p in (po_root / "whatsnew").glob("*.po")), key=natural_key)
    if rst_names is not None:
        avail = set(rst_names) | {"index"}
        before = len(names)
        names = [n for n in names if n in avail]
        log("章节按对应 ref 的 whatsnew/*.rst 取交集：中文 po %d → 可编 %d"
            % (before, len(names)))
    if "changelog" not in names:
        raise RuntimeError("该 ref 没有 changelog.rst / changelog.po，无法生成更新日志册")
    return names


def write_root_doc(doc: pathlib.Path, version: str):
    """根文档只放标题 + 一条 toctree：多余正文会在目录后单独占页（甚至空白页）。"""
    lines = [output_title(version), "=" * 60, "", ".. toctree::", "   :maxdepth: 1", "",
             "   更新历史记录 <whatsnew/changelog>", ""]
    (doc / "whatsnew_all.rst").write_text("\n".join(lines), encoding="utf-8")


def patch_conf(doc: pathlib.Path, version: str, cpy_ref: str | None = None):
    p = doc / "conf.py"
    s = p.read_text(encoding="utf-8", errors="replace")
    marker = "# ==== whatsnew-studio override ===="
    if marker in s:
        s = s[:s.index(marker)]
    title = output_title(version)
    # 除 changelog 外的 whatsnew/*.rst 全部排除：本册只编更新日志一页。
    unused = ["whatsnew/%s.rst" % x.stem
              for x in sorted((doc / "whatsnew").glob("*.rst")) if x.stem != "changelog"]
    override = """
# ==== whatsnew-studio override ====
# 这些扩展依赖 Doc/ 之外的源码模块（asdl、Parser/…），且与 whatsnew 无关；
# 按对应 ref 只取文档目录时去掉，避免 Sphinx 导入失败。
_DROP_EXT = {'asdl_highlight', 'peg_highlight', 'escape4chm',
             'glossary_search', 'suspicious', 'sphinxext.opengraph'}
extensions = [e for e in extensions if e not in _DROP_EXT]
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
# 文档类用 manual（官方单版本册用 howto）：多版本合集需要章级结构。
latex_documents = [
    ('whatsnew_all', 'whatsnew_all.tex', %r,
     'Python Software Foundation', 'manual'),
]
try:
    latex_elements
except NameError:
    latex_elements = {}
latex_elements['papersize'] = 'a4paper'
# 中文字体是本项目相对官方的必要差异；tocdepth 只是首个写入点，
# patch_toc_depth() 会在 .tex 层统一所有设置。
latex_elements['preamble'] = latex_elements.get('preamble', '') + r'''
\\usepackage{xeCJK}
\\setCJKmainfont{FandolSong-Regular.otf}[BoldFont=FandolHei-Bold.otf]
\\setCJKsansfont{FandolHei-Regular.otf}
\\setCJKmonofont{FandolFang-Regular.otf}
\\setcounter{tocdepth}{%d}
'''
""" % (version, unused, title, TOC_DEPTH - 1)
    p.write_text(s.rstrip() + "\n" + override, encoding="utf-8")
    log("conf.py 副本已覆盖（来源 cpython@%s，排除 %d 个未使用 whatsnew 文档）"
        % (cpy_ref or "?", len(unused)))


def sphinx_latex(doc: pathlib.Path, outlatex: pathlib.Path):
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
            cwd=doc, timeout=3600)
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


def patch_toc_depth(tex: pathlib.Path):
    r"""统一正文目录（Contents）与 PDF 书签的层级。

    Sphinx 的 conf.py、sphinxmanual.cls 和我们的 override 各写一次
    `\setcounter{tocdepth}`，最后生效的那个会把目录压成两级；在 .tex 层统一
    最可靠。正文 TOC_DEPTH=3 级 → 减 1 正好是官方基线的 tocdepth=2。
    bookmarksdepth 与 tocdepth 独立：目录只到 2 级，侧边栏书签仍保留 5 级。
    """
    toc_depth = TOC_DEPTH
    bookmark_depth = BOOKMARK_DEPTH
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
  \sloppy\setlength{\emergencystretch}{2em}%
}
\makeatother
""" + end + "\n"
    head += "\n" + inject
    tex.write_text(head + sep + body, encoding="utf-8")
    log("目录层级：正文 %d 级（tocdepth=%d，统一 %d 处设置）；PDF 书签 %d 级"
        % (toc_depth, toc_depth - 1, n, bookmark_depth))


# ---- changelog 独立册：小版本提升为一级章节 -------------------------------
PROMOTE_MARK = "% ==== whatsnew-studio changelog promoted ===="
HDR_BEGIN = "% ==== whatsnew-studio changelog headers begin ===="
HDR_END = "% ==== whatsnew-studio changelog headers end ===="
CLEAR_IDX_MARK = "% ==== whatsnew-studio index pagebreak ===="


def promote_changelog_structure(tex: pathlib.Path):
    r"""让每个补丁版本成为一级章节，索引与其同级。

    Sphinx 把 changelog.rst 编成 `\chapter{更新日志}`，里面的每个
    "What's New in Python 3.11.x ...?" 只是 `\section`。这里在 .tex 层：
      1) 去掉总章（目录/书签里不再有「更新历史记录」这一层）；
      2) section→chapter、subsection→section … 逐级上提；
      3) 页脚跟随新的章，并给小版本连续排版（对齐官方 whatsnew.pdf）。
    只改 LaTeX 命令、不换 docname，所以中文 po 的译文全部保留。
    幂等：注入标记可防止 --skip-download 续跑时重复提升。
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
\makeatletter
% 小版本连续排版：章不强制换页，标题紧凑，
% 版式对齐官方 whatsnew.pdf（章 14.4pt / 节 12pt / 正文 10pt，标题深蓝）。
\renewcommand\chapter{%
  \par\global\@topnum\z@
  \@afterindentfalse
  \secdef\@chapter\@schapter}
\titleformat{\section}{\large\py@HeaderFamily}%
            {\py@TitleColor\thesection}{0.5em}{\py@TitleColor}
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
\fancypagestyle{normal}{%
  \fancyhf{}%
  \fancyfoot[C]{\py@HeaderFamily\thepage}%
  \renewcommand{\headrulewidth}{0pt}%
  \renewcommand{\footrulewidth}{0pt}%
}
\makeatother
    """

    head += "\n" + HDR_BEGIN + flow.rstrip() + "\n" + HDR_END + "\n"

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

    # 3) 章不再自动分页，索引前补一次分页，避免索引紧贴正文
    if CLEAR_IDX_MARK not in body:
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
    """跑完整流程：下载 → blurb 合 NEWS → 编译 mo → Sphinx → 补丁 → xelatex。

    work/build_changelog_<ver>/ 是唯一中间目录，--skip-download 复用它。
    """
    ver = cfg["version"]
    # 必须绝对化：Sphinx / latexmk 都以 cwd=<别的目录> 起子进程，相对路径会被
    # 子进程按它的 cwd 解析（.tex 就写进 Doc/ 底下了），本机传绝对路径不暴露。
    work = pathlib.Path(cfg["workdir"]).resolve()
    outdir = pathlib.Path(cfg["outdir"]).resolve()
    root = work / ("build_changelog_%s" % ver.replace(".", "_"))
    doc = root / "Doc"
    po_root = root / "zh_po"
    outlatex = root / "out" / "latex"
    root.mkdir(parents=True, exist_ok=True)

    zh_branch, cpy_branch = resolve_branches(ver)
    log("版本 %s ｜ 中文译文 python-docs-zh-cn@%s ｜ 源文 cpython@%s"
        % (ver, zh_branch, cpy_branch))

    step("选择下载源", 2)
    if cfg["mirror"] != "auto":
        mirrors = [cfg["mirror"]]
        log("镜像：%s（已显式指定，不探测）" % cfg["mirror"])
    else:
        mirrors = probe_mirrors(list(MIRRORS))
    if not mirrors:
        raise RuntimeError("没有可用的下载镜像")

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
        # 下载器把「该分支没有这个文件」和「网络失败」都算进 fails，不能一律失败；
        # 但骨架文件缺了必然编不出来，早点报「下载不完整」，别拖到 Sphinx 才报
        # FileNotFoundError: conf.py（那种报错看不出是没下全）。
        lost = [p.name for p in (doc / "conf.py", doc / "tools" / "extensions")
                if not p.exists()]
        if lost or not any((doc / "tools" / "extensions").glob("*.py")):
            raise RuntimeError(
                "下载不完整：缺 %s（失败 %d 个文件）。换个 --mirror 重跑即可，"
                "已下好的文件会复用。" % (lost or ["tools/extensions/*.py"], fails))
        emit("PCT", "26")

    step("生成变更日志数据", 27)
    prepare_news(root, ver)
    emit("PCT", "32")

    step("编译中文译文", 33)
    install_locales(po_root, doc)
    emit("PCT", "38")

    step("准备 Sphinx 工程", 39)
    # 官方 conf.py 会 os.listdir('howto') 生成分册列表；本册不下载 howto 内容，
    # 建空目录让它返回 []（latex_documents 随后被覆盖，不影响产物）。
    (doc / "howto").mkdir(exist_ok=True)
    choose_docs(po_root, {p.stem for p in (doc / "whatsnew").glob("*.rst")})
    write_root_doc(doc, ver)
    patch_conf(doc, ver, cpy_branch)
    emit("PCT", "43")

    step("Sphinx 生成 LaTeX", 44)
    tex = sphinx_latex(doc, outlatex)
    emit("PCT", "68")
    ensure_graphics(root, tex, cpy_branch, mirrors)
    patch_index_style(outlatex, tex)
    patch_toc_depth(tex)
    promote_changelog_structure(tex)
    emit("PCT", "70")

    step("XeLaTeX 编译 PDF", 71)
    pdf = latexmk(outlatex, tex)
    emit("PCT", "96")

    outdir.mkdir(parents=True, exist_ok=True)
    final = outdir / (output_title(ver) + ".pdf")
    shutil.copy2(pdf, final)
    emit("PCT", "100")
    emit("DONE", str(final))
    log("输出：%s（%.2f MB）" % (final, final.stat().st_size / 1048576))
    return final


def main():
    """命令行入口。--mode 只为兼容既有调用方保留，本文件固定出更新日志册。"""
    ap = argparse.ArgumentParser(description="Python 完整更新日志构建器")
    ap.add_argument("--version", default="3.15", help="版本号 3.x（3.11 及以后）")
    ap.add_argument("--mode", default="changelog", choices=("changelog",),
                    help="只支持 changelog")
    ap.add_argument("--mirror", default="auto", choices=["auto"] + list(MIRRORS),
                    help="下载源：auto=逐个探测后取最快；直连=只用官网 raw")
    ap.add_argument("--outdir", default=str(HERE / "output"))
    ap.add_argument("--workdir", default=str(HERE / "work"))
    ap.add_argument("--skip-download", action="store_true",
                    help="复用上次下载的文件，跳过下载（改译文/调版式后续跑用）")
    a = ap.parse_args()
    try:
        build({"version": a.version, "mirror": a.mirror, "outdir": a.outdir,
               "workdir": a.workdir, "skip_download": a.skip_download})
    except Exception as e:  # noqa: BLE001
        emit("FAIL", "%s: %s" % (type(e).__name__, e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
