$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) {
    throw 'Create .venv and install requirements.txt first. See README.ko.md.'
}
& $pythonPath -m uvicorn marine_agent.app:app --host 127.0.0.1 --port 8001
