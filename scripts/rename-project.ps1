param(
    [ValidatePattern('^[A-Za-z][A-Za-z0-9_-]*$')]
    [string]$TargetName = 'Wenxi',
    [string]$ComposeProject = 'supermew',
    [string]$ToolPythonPath = '',
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$sourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
$parentRoot = Split-Path -Parent $sourceRoot
$targetRoot = [IO.Path]::GetFullPath((Join-Path $parentRoot $TargetName)).TrimEnd('\')
if ($sourceRoot -eq $targetRoot) { throw 'Project already has the requested directory name.' }
if ((Split-Path -Parent $targetRoot) -ne $parentRoot) { throw 'Target must be a sibling directory.' }
if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot '.git'))) { throw 'Expected repository root.' }
if (Test-Path -LiteralPath $targetRoot) { throw "Target already exists: $targetRoot" }
$projectPython = Join-Path $sourceRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) { throw 'Expected the existing Windows .venv.' }
if (-not $ToolPythonPath) {
    $ToolPythonPath = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
}
if (-not (Test-Path -LiteralPath $ToolPythonPath)) {
    throw 'Pass -ToolPythonPath pointing to a tooling Python with pip (for standard launcher regeneration).'
}
& $ToolPythonPath -c 'from pip._vendor.distlib.scripts import ScriptMaker'
if ($LASTEXITCODE -ne 0) { throw 'Tooling Python must provide pip bundled distlib.' }

# Release this shell's working-directory handle. Never terminate editors or user terminals.
Set-Location -LiteralPath $parentRoot
$probe = @'
import ctypes, json, sys
from ctypes import wintypes
k = ctypes.WinDLL('kernel32', use_last_error=True)
k.CreateFileW.restype = wintypes.HANDLE
k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
h = k.CreateFileW(sys.argv[1], 0x10000, 7, None, 3, 0x02000000, None)
error = ctypes.get_last_error() if h == ctypes.c_void_p(-1).value else 0
if not error: k.CloseHandle(h)
print(json.dumps({'rename_handle_available': not error, 'win32_error': error}))
'@
$probeResult = (& $ToolPythonPath -c $probe $sourceRoot) | ConvertFrom-Json
Write-Output "Source: $sourceRoot"
Write-Output "Target: $targetRoot"
Write-Output "Windows rename handle available: $($probeResult.rename_handle_available) (error $($probeResult.win32_error))"
if ($CheckOnly) { return }

$capture = @'
import importlib.metadata, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from backend.env import load_env
load_env()
from backend.infra.database import SessionLocal
from backend.db.models import Run, RagEvaluationJob, IndexJob
from sqlalchemy import func, select
with SessionLocal() as session:
    for model in (Run, RagEvaluationJob, IndexJob):
        active = session.scalar(select(func.count()).select_from(model).where(model.status.in_(['queued','running','pending','starting','waiting_input','cancelling'])))
        if active: raise SystemExit('Active tasks exist; finish or cancel them before renaming')
entries = [{'name': e.name, 'value': e.value, 'group': e.group} for d in importlib.metadata.distributions() for e in d.entry_points if e.group in ('console_scripts','gui_scripts')]
path = Path(sys.argv[1]) / '.artifacts' / 'relocation-entrypoints.json'
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(entries), encoding='utf-8')
'@
& $projectPython -c $capture $sourceRoot
if ($LASTEXITCODE -ne 0) { throw 'Task/venv preflight failed; no services were stopped.' }
$actualProject = & docker inspect supermew-postgres --format '{{ index .Config.Labels "com.docker.compose.project" }}'
if ($LASTEXITCODE -ne 0 -or $actualProject.Trim() -ne $ComposeProject) {
    throw 'Existing Docker project identity differs; inspect it before running with -ComposeProject.'
}

function Start-ProjectServices([string]$Root) {
    Start-Process -FilePath (Join-Path $Root '.venv\Scripts\python.exe') -ArgumentList @('-m','backend.launcher','--host','127.0.0.1','--port','8000') -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Root '.artifacts\backend.out.log') -RedirectStandardError (Join-Path $Root '.artifacts\backend.err.log') | Out-Null
    $node = (Get-Command node.exe).Source
    Start-Process -FilePath $node -ArgumentList @('node_modules/vite/bin/vite.js','--port','3000','--strictPort') -WorkingDirectory (Join-Path $Root 'frontend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Root '.artifacts\frontend.out.log') -RedirectStandardError (Join-Path $Root '.artifacts\frontend.err.log') | Out-Null
}

$currentRoot = $sourceRoot
$stopped = $false
try {
    $stopped = $true
    # Match only this repository's launcher/Vite processes. Preserve Codex/editors/terminals.
    $escapedRoot = [Regex]::Escape($sourceRoot)
    $services = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -in @('python.exe','node.exe') -and $_.CommandLine -match $escapedRoot -and
        ($_.CommandLine -match '-m\s+backend\.launcher(?:\s|$)' -or $_.CommandLine -match 'vite[\\/]bin[\\/]vite\.js')
    }
    foreach ($service in $services) {
        if (Get-Process -Id $service.ProcessId -ErrorAction SilentlyContinue) {
            & taskkill /PID $service.ProcessId /T /F | Out-Null
        }
    }
    & docker compose --project-name $ComposeProject --project-directory $sourceRoot down
    if ($LASTEXITCODE -ne 0) { throw 'Compose shutdown failed.' }
    # Paths were resolved and checked as exact siblings above. No copy/delete fallback.
    Rename-Item -LiteralPath $sourceRoot -NewName $TargetName
    $currentRoot = $targetRoot
    $envPath = Join-Path $targetRoot '.env'
    $envText = [IO.File]::ReadAllText($envPath)
    if ($envText -match '(?m)^COMPOSE_PROJECT_NAME=') {
        $envText = [Regex]::Replace($envText, '(?m)^COMPOSE_PROJECT_NAME=[^\r\n]*', "COMPOSE_PROJECT_NAME=$ComposeProject")
    } else {
        $envText += "`r`nCOMPOSE_PROJECT_NAME=$ComposeProject`r`n"
    }
    # Rewrite only path settings, never credentials or immutable task snapshots.
    $envText = [Regex]::Replace($envText, '(?m)^([A-Z_]*(?:PATH|ROOT|DIR|DIRECTORY)[A-Z_]*=)([^\r\n]*)', {
        param($match)
        $match.Groups[1].Value + $match.Groups[2].Value.Replace($sourceRoot, $targetRoot).Replace($sourceRoot.Replace('\','/'), $targetRoot.Replace('\','/'))
    })
    [IO.File]::WriteAllText($envPath, $envText, [Text.UTF8Encoding]::new($false))
    & $ToolPythonPath (Join-Path $targetRoot 'scripts\relocate_venv.py') $sourceRoot $targetRoot (Join-Path $targetRoot '.artifacts\relocation-entrypoints.json')
    if ($LASTEXITCODE -ne 0) { throw 'Venv launcher regeneration failed.' }
    & docker compose --project-name $ComposeProject --project-directory $targetRoot up -d --wait --wait-timeout 240
    if ($LASTEXITCODE -ne 0) { throw 'Docker startup not healthy; inspect docker compose ps.' }
    Start-ProjectServices $targetRoot
    Write-Output "Renamed successfully: $targetRoot"
    Write-Output 'Reopen the new directory in your editor/Codex and reactivate .venv in existing terminals.'
} catch {
    if ($stopped) {
        & docker compose --project-name $ComposeProject --project-directory $currentRoot up -d
        Start-ProjectServices $currentRoot
    }
    throw
}
