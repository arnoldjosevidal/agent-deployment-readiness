$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = Split-Path -Parent $PSScriptRoot
$bundle = Join-Path $repo 'vendor\nemotron-input-counter-v0.3.1'
$target = Join-Path $bundle 'runtime_packages'
$requirements = Join-Path $bundle 'requirements.txt'
if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) { throw 'Counter package requirements are missing.' }
$python = Get-Command py -ErrorAction SilentlyContinue
if ($python) {
    & py -3.12 -m pip install --disable-pip-version-check --target $target -r $requirements
    if ($LASTEXITCODE -ne 0) { throw "Isolated counter dependency installation failed (exit $LASTEXITCODE)." }
} else {
    throw 'Python Launcher for Windows (py) with Python 3.12 is required.'
}
Write-Output 'Counter dependencies installed only under vendor\nemotron-input-counter-v0.3.1\runtime_packages.'
Write-Output 'This prepares the local experimental counter; it does not enable B1 or make provider calls.'
