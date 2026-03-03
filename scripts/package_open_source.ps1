$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$distRoot = Join-Path $projectRoot "dist"
$outDir = Join-Path $distRoot "open-source-package"

if (Test-Path $outDir) {
    Remove-Item -Recurse -Force $outDir
}
New-Item -ItemType Directory -Path $outDir | Out-Null

function Copy-Path {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath
    )

    $src = Join-Path $projectRoot $RelativePath
    $dst = Join-Path $outDir $RelativePath

    if (-not (Test-Path $src)) {
        return
    }

    $dstParent = Split-Path -Parent $dst
    if ($dstParent -and -not (Test-Path $dstParent)) {
        New-Item -ItemType Directory -Path $dstParent -Force | Out-Null
    }

    Copy-Item -Path $src -Destination $dst -Recurse -Force
}

# 复制开源所需文件
$includePaths = @(
    ".env.example",
    ".gitignore",
    "AGENTS.md",
    "LICENSE",
    "README.md",
    "requirements.txt",
    "main.py",
    "run_book.py",
    "render_pdf.py",
    "generate_openclaw.py",
    "config",
    "src",
    "scripts",
    "data\output\.gitkeep",
    "data\raw\.gitkeep",
    "data\vectordb\.gitkeep"
)

foreach ($path in $includePaths) {
    Copy-Path -RelativePath $path
}

# 清理缓存产物，避免污染开源包
Get-ChildItem -Path $outDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force
Get-ChildItem -Path $outDir -Recurse -File -Include "*.pyc","*.pyo" -ErrorAction SilentlyContinue |
    Remove-Item -Force

Write-Host "Open-source package created: $outDir" -ForegroundColor Green
Write-Host "Recommended next step: powershell -ExecutionPolicy Bypass -File scripts/open_source_audit.ps1" -ForegroundColor Yellow
