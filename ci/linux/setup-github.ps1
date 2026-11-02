#Requires -Version 7.0
<#
.SYNOPSIS
    在没有 GitHub 连接器、且 github.com 主站打不开的情况下，把仓库建好并推上去。

.DESCRIPTION
    为什么需要这个脚本（2026-11-02 实测环境）：
        https://github.com             TCP 443 全不通（140.82.112.3 / .113.3 / .114.3 /
                                        20.200.245.247 / 4.237.22.38 全部超时）
        https://api.github.com         200，0.6s          ← 通
        https://codeload.github.com    301，1.0s          ← 通
        ssh.github.com:443             握手成功（Permission denied (publickey)）← 通

    于是：
      · WorkBuddy 的 GitHub 连接器永远授权失败 —— 它要访问
        github.com/login/oauth/access_token，这个域名 TCP 都不通，跟账号设置无关；
      · `git push` 走 https://github.com 也会失败；
      · 但 **api.github.com** 可用（建仓库、上传公钥），**ssh.github.com:443** 可用（推送）。

    本脚本就走这条备用通道：
      1. 用 PAT 调 api.github.com 确认身份、建仓库（幂等）；
      2. 可选：把本机 SSH 公钥通过 API 注册到账号（省得打开打不开的网页）；
      3. 写 ~/.ssh/config，让 `github.com` 实际连到 `ssh.github.com:443`；
      4. 配 remote 并 push main。

    ★ Token 只从环境变量读、只在内存里用，**不落盘、不写进 .git/config**。

.PARAMETER Repo
    仓库名，默认取 $env:GH_REPO，否则 python-docs-zh-pdf。

.PARAMETER Private
    建私有仓库（默认公开：私有仓库 Actions 只有 2000 分钟/月，3 版本×每天会超）。

.PARAMETER UploadKey
    把 -KeyPath 指的公钥通过 API 注册到 GitHub 账号（已存在则跳过）。

.PARAMETER DryRun
    只打印计划，不调 API、不改文件、不推送。没有 token 也能跑，用来先看一遍。

.EXAMPLE
    $env:GH_TOKEN = "github_pat_xxx"
    .\ci\linux\setup-github.ps1 -DryRun

.EXAMPLE
    $env:GH_TOKEN = "github_pat_xxx"
    .\ci\linux\setup-github.ps1 -UploadKey
#>
[CmdletBinding()]
param(
    [string]$Repo = $(if ($env:GH_REPO) { $env:GH_REPO } else { 'python-doc-pdf-zh' }),
    [string]$Owner = '',
    [switch]$Private,
    [switch]$UploadKey,
    [string]$KeyPath = (Join-Path $HOME '.ssh/id_ed25519.pub'),
    [string]$Branch = 'main',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ---------------------------------------------------------------- 小工具
function Say([string]$msg, [string]$level = 'info') {
    $tag = switch ($level) { 'ok' { 'OK  ' } 'warn' { 'WARN' } 'err' { 'FAIL' } default { '--  ' } }
    Write-Host "[$tag] $msg"
}

function Api {
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][string]$Path,
        $Body,
        [switch]$Allow404
    )
    $headers = @{
        Authorization          = "Bearer $script:Token"
        Accept                 = 'application/vnd.github+json'
        'X-GitHub-Api-Version' = '2022-11-28'
        'User-Agent'           = 'pdfbuild-setup'
    }
    $splat = @{
        Method      = $Method
        Uri         = "https://api.github.com$Path"
        Headers     = $headers
        TimeoutSec  = 30
        ErrorAction = 'Stop'
    }
    if ($null -ne $Body) {
        $splat.Body        = ($Body | ConvertTo-Json -Depth 6)
        $splat.ContentType = 'application/json; charset=utf-8'
    }
    try {
        return Invoke-RestMethod @splat
    } catch {
        $code = 0
        if ($_.Exception.PSObject.Properties['Response'] -and $_.Exception.Response) {
            $code = [int]$_.Exception.Response.StatusCode
        }
        if ($Allow404 -and $code -eq 404) { return $null }
        throw "API $Method $Path 失败（HTTP $code）：$($_.Exception.Message)"
    }
}

function Test-Tcp([string]$HostName, [int]$Port) {
    try {
        $c = [System.Net.Sockets.TcpClient]::new()
        $ok = $c.ConnectAsync($HostName, $Port).Wait(5000)
        $c.Dispose()
        return $ok
    } catch { return $false }
}

# ---------------------------------------------------------------- 0. 前置
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path (Join-Path $root '.git'))) {
    throw "这里不是 git 仓库根目录（$root）：先在项目根目录下运行本脚本"
}
Say "项目根：$root"

if ($DryRun) {
    Say '=== DryRun：只打印计划，不动任何东西 ===' 'warn'
    Say "仓库名      ：$Repo（$(if ($Private) { '私有' } else { '公开' })）"
    Say "SSH 公钥    ：$KeyPath（$(if (Test-Path $KeyPath) { '已存在' } else { '还没有，需要先生成' })）"
    Say "将执行      ：GET /user → 建仓库 → $(if ($UploadKey) { '上传公钥 → ' } else { '' })写 ~/.ssh/config → git remote + push $Branch"
    Say "连通性自查  ："
    Say ("  api.github.com:443  = " + (Test-Tcp 'api.github.com' 443))
    Say ("  ssh.github.com:443  = " + (Test-Tcp 'ssh.github.com' 443))
    Say ("  github.com:443      = " + (Test-Tcp 'github.com' 443) + "（关掉也无所谓，本脚本不走它）")
    exit 0
}

$script:Token = ($env:GH_TOKEN, $env:GITHUB_TOKEN | Where-Object { $_ } | Select-Object -First 1)
if (-not $script:Token) {
    throw @'
没有找到 token。两种给法（任选一种，都只在当前会话有效）：

  PowerShell ：
      $env:GH_TOKEN = "github_pat_xxxxxxxx"
      .\ci\linux\setup-github.ps1 -UploadKey

  cmd ：
      set GH_TOKEN=github_pat_xxxxxxxx

★ PAT 怎么建：需要在**能打开 github.com 的网络**（比如手机热点）上，
  Settings → Developer settings → Fine-grained tokens → Generate new token：
     Repository access : 选 All repositories（或先建空仓库再只选它）
     Permissions       : Contents = Read and write
                         Workflows = Read and write   ← 少了这个推不进 .github/workflows/
  Classic token 也可以，勾 repo + workflow 两个 scope。
'@
}

if (-not (Test-Tcp 'api.github.com' 443)) {
    throw 'api.github.com 也连不上：先把网络弄通（这脚本只依赖 api.github.com 与 ssh.github.com:443）'
}

# ---------------------------------------------------------------- 1. 身份
$me = Api -Method GET -Path '/user'
$login = $me.login
if (-not $Owner) { $Owner = $login }
Say "身份：$login（计划推到 $Owner/$Repo）" 'ok'

if ($me.PSObject.Properties['plan'] -and $me.plan -and $me.plan.name) {
    Say "账号套餐：$($me.plan.name)"
}
if ($Private) { Say '私有仓库：Actions 只有 2000 分钟/月，3 版本×每天约 2700 分钟，会超' 'warn' }

# ---------------------------------------------------------------- 2. 仓库
$repoPath = "/repos/$Owner/$Repo"
$exists = Api -Method GET -Path $repoPath -Allow404
if ($exists) {
    Say "仓库已存在：$($exists.full_name)（private = $($exists.private)）" 'ok'
} else {
    Say "建仓库 $Owner/$Repo（$(if ($Private) { '私有' } else { '公开' })）"
    $body = @{ name = $Repo; private = [bool]$Private; auto_init = $false }
    $created = Api -Method POST -Path '/user/repos' -Body $body
    Say "已创建：$($created.html_url)" 'ok'
    $exists = $created
}
$sshUrl = if ($exists.PSObject.Properties['ssh_url'] -and $exists.ssh_url) {
    $exists.ssh_url
} else {
    "git@github.com:$Owner/$Repo.git"
}

# ---------------------------------------------------------------- 3. 公钥（可选）
if ($UploadKey) {
    if (-not (Test-Path $KeyPath)) {
        Say "找不到公钥 $KeyPath，先生成：ssh-keygen -t ed25519 -C pdfbuild -f $($KeyPath -replace '\.pub$','')" 'err'
        exit 1
    }
    $pub = (Get-Content $KeyPath -Raw).Trim()
    $keys = Api -Method GET -Path '/user/keys'
    $dup = $keys | Where-Object { $_.key -and $_.key.Split(' ')[1] -eq $pub.Split(' ')[1] }
    if ($dup) {
        Say "公钥已在该账号（title = $($dup.title)，id = $($dup.id)），跳过" 'ok'
    } else {
        $k = Api -Method POST -Path '/user/keys' -Body @{ title = "pdfbuild-$env:COMPUTERNAME"; key = $pub }
        Say "公钥已上传（id = $($k.id)）" 'ok'
    }
}

# ---------------------------------------------------------------- 4. SSH 走 443
$sshDir = Join-Path $HOME '.ssh'
New-Item -ItemType Directory -Force -Path $sshDir | Out-Null
$cfgPath = Join-Path $sshDir 'config'
$marker = '# >>> pdfbuild: github.com 走 ssh.github.com:443（主站 443 被封时用）'
$cfg = if (Test-Path $cfgPath) { Get-Content $cfgPath -Raw } else { '' }
if ($cfg -notmatch [regex]::Escape($marker)) {
    $block = @"

$marker
Host github.com
    HostName ssh.github.com
    Port 443
    User git
# <<< pdfbuild
"@
    Add-Content -Path $cfgPath -Value $block -Encoding utf8
    Say "已写入 $cfgPath（github.com → ssh.github.com:443）" 'ok'
} else {
    Say "$cfgPath 已有该配置，跳过" 'ok'
}

if (-not (Test-Tcp 'ssh.github.com' 443)) {
    Say 'ssh.github.com:443 连不上：推送会失败，先解决网络' 'err'
    exit 1
}

$probe = & ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -T git@github.com 2>&1
$probeText = ($probe | Out-String)
if ($probeText -match 'successfully authenticated') {
    Say 'SSH 认证通过' 'ok'
} elseif ($probeText -match 'Permission denied') {
    Say 'SSH 能连到 GitHub，但本机这把 key 没被账号接受（把公钥加进账号，或加 -UploadKey 重跑）' 'err'
    exit 1
} else {
    Say "SSH 探测结果不明：$($probeText.Trim())" 'warn'
}

# ---------------------------------------------------------------- 5. remote + push
Push-Location $root
try {
    $hasOrigin = (& git remote) -contains 'origin'
    if ($hasOrigin) {
        & git remote set-url origin $sshUrl
        Say "origin 已更新为 $sshUrl"
    } else {
        & git remote add origin $sshUrl
        Say "origin 已添加：$sshUrl"
    }
    if ($LASTEXITCODE -ne 0) { throw 'git remote 配置失败' }

    Say "推送 $Branch ……"
    & git push -u origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "推送失败（退出码 $LASTEXITCODE）" }
    Say "推送完成：https://github.com/$Owner/$Repo/tree/$Branch" 'ok'
} finally {
    Pop-Location
}

Say '' 'ok'
Say '下一步：' 'ok'
Say "  1) 打开 https://github.com/$Owner/$Repo/actions （打不开就等网络好）"
Say "  2) 选「构建 Python 中文文档 PDF（Linux）」→ Run workflow → versions 先填 3.15"
Say "  3) 跑完后 Branches 里会出现 v<完整版本>，点进去就是 39 册 PDF + 验收报告"
