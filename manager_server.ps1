[CmdletBinding()]
param(
    [ValidateSet('start', 'stop', 'restart', 'install', 'cleanlogs', 'status', 'help')]
    [string]$Command = 'help'
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $Root '.env'
$LogsDir = Join-Path $Root 'logs'
$InstanceDir = Join-Path $Root 'instance'
$PidFile = Join-Path $LogsDir 'server.pid'
$AppLog = if ([string]::IsNullOrWhiteSpace($env:APP_LOG_FILE)) {
    Join-Path $LogsDir 'app.log'
} else {
    $env:APP_LOG_FILE
}
$ServerStdoutLog = Join-Path $LogsDir 'server.out.log'
$ServerStderrLog = Join-Path $LogsDir 'server.err.log'

function Read-EnvFile {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) {
            return
        }

        $idx = $line.IndexOf('=')
        if ($idx -lt 1) {
            return
        }

        $key = $line.Substring(0, $idx).Trim()
        $value = $line.Substring($idx + 1).Trim()
        if ($value.Length -ge 2 -and $value.StartsWith('"') -and $value.EndsWith('"')) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        Set-Item -Path "Env:$key" -Value $value
    }
}

function Resolve-PythonPath {
    $candidates = @(
        $env:PYTHON,
        (Join-Path $Root '.venv\Scripts\python.exe'),
        'C:\Python313\python.exe',
        (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
    ) | Where-Object { $_ }

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    throw "Nu gasesc un interpreter Python valid."
}

function Resolve-PythonWPath {
    $candidate = $env:PYTHONW
    if ($candidate -and (Test-Path -LiteralPath $candidate)) {
        return (Resolve-Path -LiteralPath $candidate).Path
    }

    $python = Resolve-PythonPath
    $pythonW = [System.IO.Path]::Combine(
        [System.IO.Path]::GetDirectoryName($python),
        'pythonw.exe'
    )
    if ($pythonW -and (Test-Path -LiteralPath $pythonW)) {
        return (Resolve-Path -LiteralPath $pythonW).Path
    }

    return $python
}

function Ensure-Dirs {
    New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
    New-Item -ItemType Directory -Force -Path $InstanceDir | Out-Null
}

function Get-ListeningPid {
    param([int]$Port)

    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($null -ne $connection) {
        return [int]$connection.OwningProcess
    }

    return $null
}

function Save-PidFile {
    param([int]$ProcessId)

    Set-Content -LiteralPath $PidFile -Value $ProcessId -Encoding ASCII
}

function Load-PidFile {
    if (-not (Test-Path -LiteralPath $PidFile)) {
        return $null
    }

    $raw = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    $parsed = 0
    if ([int]::TryParse($raw, [ref]$parsed)) {
        return $parsed
    }

    return $null
}

function Test-ProcessAlive {
    param([int]$ProcessId)

    try {
        Get-Process -Id $ProcessId -ErrorAction Stop | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Remove-Logs {
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Get-ChildItem -LiteralPath $LogsDir -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like '*.log*' } |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

function Show-Help {
    @(
        'Utilizare:',
        '  manager_server.ps1 start',
        '  manager_server.ps1 stop',
        '  manager_server.ps1 restart',
        '  manager_server.ps1 install',
        '  manager_server.ps1 cleanlogs',
        '  manager_server.ps1 status'
    ) | ForEach-Object { Write-Host $_ }
}

Read-EnvFile -Path $EnvFile
Ensure-Dirs

$Port = if ([string]::IsNullOrWhiteSpace($env:PORT)) { 5055 } else { [int]$env:PORT }
$Python = Resolve-PythonPath
$HostName = if ([string]::IsNullOrWhiteSpace($env:HOST)) { '127.0.0.1' } else { $env:HOST }

switch ($Command) {
    'help' {
        Show-Help
        exit 1
    }

    'install' {
        & $Python -m pip install -r (Join-Path $Root 'requirements.txt')
        exit $LASTEXITCODE
    }

    'start' {
        $runningPid = Load-PidFile
        if ($runningPid -and (Test-ProcessAlive -ProcessId $runningPid)) {
            Save-PidFile -ProcessId $runningPid
            Write-Host "Serverul ruleaza deja cu PID $runningPid pe portul $Port."
            exit 0
        }

        $launcher = Join-Path $Root 'scripts\server_launcher.py'
        if (-not (Test-Path -LiteralPath $launcher)) {
            Write-Host "Nu gasesc launcher-ul serverului: $launcher"
            exit 1
        }

        $launchOutput = & $Python $launcher `
            --root $Root `
            --pid-file $PidFile `
            --stdout $ServerStdoutLog `
            --stderr $ServerStderrLog `
            --app-log $AppLog

        if ($LASTEXITCODE -ne 0) {
            Write-Host "Pornirea serverului a esuat. Verifica $ServerStderrLog si $AppLog."
            exit $LASTEXITCODE
        }

        $processIdText = ($launchOutput | Select-Object -Last 1).ToString().Trim()
        $processId = 0
        if (-not [int]::TryParse($processIdText, [ref]$processId)) {
            $processId = Load-PidFile
        }

        if (-not $processId) {
            Write-Host "Serverul a fost lansat, dar PID-ul nu a putut fi confirmat."
            exit 1
        }

        Save-PidFile -ProcessId $processId
        Write-Host "Server pornit cu PID $processId pe http://$HostName`:$Port"
        exit 0
    }

    'stop' {
        $processId = Get-ListeningPid -Port $Port
        if (-not $processId) {
            $processId = Load-PidFile
        }

        if (-not $processId -or -not (Test-ProcessAlive -ProcessId $processId)) {
            Write-Host "Nu exista un server pornit."
            exit 0
        }

        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        Write-Host "Server oprit."
        exit 0
    }

    'restart' {
        & $PSCommandPath stop
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
        & $PSCommandPath start
        exit $LASTEXITCODE
    }

    'cleanlogs' {
        Remove-Logs
        Write-Host "Logurile au fost sterse."
        exit 0
    }

    'status' {
        $processId = Load-PidFile
        if ($processId -and (Test-ProcessAlive -ProcessId $processId)) {
            Save-PidFile -ProcessId $processId
            Write-Host "Serverul ruleaza cu PID $processId pe portul $Port."
        } else {
            $processId = Get-ListeningPid -Port $Port
            if ($processId) {
                Save-PidFile -ProcessId $processId
                Write-Host "Serverul ruleaza cu PID $processId pe portul $Port."
            } else {
                Write-Host "Serverul nu ruleaza."
            }
        }
        exit 0
    }
}
