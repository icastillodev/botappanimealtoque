# Actualiza desde Git, pip y reinicia el bot EN ESTA MÁQUINA (p. ej. carpeta clonada en un VPS
# o la copia “oficial” del repo). No es el flujo de desarrollo en localhost.
#
# Desarrollo local: en otra carpeta o la misma, con venv activo →  python main.py
# (Cursor/terminal). Si corrés dos bots, usá otro token o solo uno online para evitar
# que Discord desconecte sesiones duplicadas.
#
# Recomendado con Git for Windows: delega en update.sh (mismo comportamiento que Linux).
# Uso:  .\update.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

$gitBash = @(
    "${env:ProgramFiles}\Git\bin\bash.exe",
    "${env:ProgramFiles(x86)}\Git\bin\bash.exe",
    "$env:LocalAppData\Programs\Git\bin\bash.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if ($gitBash) {
    Write-Host "==> Usando Git Bash: $gitBash"
    Set-Location $Root
    & $gitBash -lc "./update.sh"
    exit $LASTEXITCODE
}

# --- Fallback sin bash: pull, pip, reinicio básico ---
Write-Host "==> (Sin Git Bash) modo PowerShell básico"

function Get-VenvPython {
    $candidates = @(
        (Join-Path $Root ".venv\Scripts\python.exe"),
        (Join-Path $Root "venv\Scripts\python.exe")
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    return (Get-Command python -ErrorAction Stop).Source
}

$Py = Get-VenvPython
$RunDir = Join-Path $Root ".run"
$PidFile = Join-Path $RunDir "bot.pid"
$LogFile = Join-Path $RunDir "bot.log"
$ErrFile = Join-Path $RunDir "bot.err.log"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

Write-Host "==> Repo: $Root"
Write-Host "==> Python: $Py"

Set-Location $Root
Write-Host "==> git pull --ff-only"
git pull --ff-only

$Req = Join-Path $Root "requirements.txt"
if (Test-Path $Req) {
    Write-Host "==> pip install -r requirements.txt"
    & $Py -m pip install -r $Req -q
}

if (Test-Path $PidFile) {
    $raw = (Get-Content $PidFile -Raw).Trim()
    if ($raw -match '^\d+$') {
        $id = [int]$raw
        $p = Get-Process -Id $id -ErrorAction SilentlyContinue
        if ($p) {
            Write-Host "==> Deteniendo PID $id..."
            Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

$mainPy = Join-Path $Root "main.py"
Write-Host "==> Iniciando bot (stdout: $LogFile, stderr: $ErrFile)"
$proc = Start-Process -FilePath $Py -ArgumentList "`"$mainPy`"" `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError $ErrFile `
    -PassThru
$proc.Id | Set-Content -Path $PidFile -Encoding ascii
Write-Host "==> Listo. PID $($proc.Id)"
