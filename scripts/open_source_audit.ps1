$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

Write-Host "[1/4] compileall" -ForegroundColor Cyan
py -m compileall main.py run_book.py render_pdf.py src | Out-Host

Write-Host "[2/4] cli help checks" -ForegroundColor Cyan
py main.py --help | Out-Null
py run_book.py --help | Out-Null
py render_pdf.py --help | Out-Null

Write-Host "[3/4] secret scan" -ForegroundColor Cyan
if (-not (Get-Command rg -ErrorAction SilentlyContinue)) {
    throw "rg (ripgrep) not found."
}

$secretPattern = 'sk-[A-Za-z0-9_-]{20,}|(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*["''][^$"''\r\n]{8,}["'']'
$rgArgs = @(
    "-n",
    "-S",
    "--hidden",
    "--glob", "!.git/**",
    "--glob", "!__pycache__/**",
    "--glob", "!.agentdocs/**",
    "--glob", "!data/output/**",
    "--glob", "!data/raw/**",
    "--glob", "!data/vectordb/**",
    "--glob", "!dist/**",
    "--glob", "!text/openclaw101-main/node_modules/**",
    "--glob", "!text/openclaw101-main/.next/**",
    "--glob", "!*.jsonl",
    "--glob", "!完整会话记录_*.jsonl",
    "--glob", "!会话可读版总结_*.md",
    $secretPattern,
    "."
)

$hits = & rg @rgArgs
$rgExit = $LASTEXITCODE
if ($rgExit -eq 0 -and $hits) {
    Write-Host $hits
    throw "Potential secrets detected."
}
if ($rgExit -gt 1) {
    throw "rg execution failed."
}

Write-Host "[4/4] audit passed" -ForegroundColor Green
