param([switch]$Restart, [switch]$Stop)
$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
$appState = Join-Path $appRoot '.tmp\local-app'
$appPython = Join-Path $appRoot '.venv\Scripts\python.exe'
$appFrontend = Join-Path $appRoot 'frontend'
$appVite = Join-Path $appFrontend 'node_modules\vite\bin\vite.js'
New-Item -ItemType Directory -Force -Path $appState | Out-Null
$appDigest = [System.Security.Cryptography.SHA256]::Create()
$appKey = [BitConverter]::ToString($appDigest.ComputeHash([Text.Encoding]::UTF8.GetBytes($appRoot))).Replace('-', '')
$appMutex = New-Object System.Threading.Mutex($false, "Local\ScorPred-$appKey")
try {
    try { $appLocked = $appMutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $appLocked = $true }
    if (-not $appLocked) { throw 'Another ScorPred launch is in progress. Try again after it finishes.' }

    function Get-AppOwner([int]$Port) {
        $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($listener) { return Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" }
        return $null
    }
    function Get-LocalJson([string]$Path) {
        try { return Invoke-RestMethod -Uri "http://127.0.0.1:5001$Path" -TimeoutSec 3 } catch { return $null }
    }
    function Wait-App([string]$Url, [string]$Log) {
        $deadline = (Get-Date).AddSeconds(55)
        do {
            try {
                $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
                if ($response.StatusCode -eq 200) { return }
            } catch { }
            Start-Sleep -Milliseconds 400
        } while ((Get-Date) -lt $deadline)
        throw "ScorPred did not become ready at $Url. Check $Log"
    }
    $backend = Get-AppOwner 5001
    $runtime = Get-LocalJson '/api/local-runtime'
    if ($backend -and (-not $runtime -or $runtime.root -ne $appRoot -or $runtime.pid -ne $backend.ProcessId)) {
        throw 'Port 5001 is occupied by an unmanaged server. Stop that server explicitly; ScorPred will not terminate it.'
    }
    $frontend = Get-AppOwner 5173
    if ($frontend -and (-not $frontend.CommandLine.Contains($appVite))) {
        throw 'Port 5173 is occupied by an unmanaged server. Stop that server explicitly; ScorPred will not terminate it.'
    }
    if ($Restart -or $Stop) {
        if ($backend) {
            Set-Content -LiteralPath (Join-Path $appState 'backend.stop') -Value 'stop'
            $deadline = (Get-Date).AddSeconds(55)
            while (Get-Process -Id $backend.ProcessId -ErrorAction SilentlyContinue) {
                if ((Get-Date) -gt $deadline) { throw 'Backend is still finishing its work. No second backend was started; check backend.err.log.' }
                Start-Sleep -Milliseconds 400
            }
        }
        if ($frontend) { Stop-Process -Id $frontend.ProcessId }
        if ($Stop) { Write-Host 'ScorPred app stopped. The independent NFL collector was left running.'; return }
        $backend = $null
        $frontend = $null
    }
    if (-not (Test-Path -LiteralPath $appPython)) { throw 'Python environment missing. Run: py -3 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt' }
    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    $appNode = if ($nodeCommand) { $nodeCommand.Source } else { $null }
    if (-not $appNode) {
        $bundled = Get-ChildItem -Path (Join-Path $appRoot '.tmp\review\node-*-win-x64\node.exe') -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
        if ($bundled) { $appNode = $bundled.FullName }
    }
    if (-not $appNode) { throw 'Node.js missing. Install Node.js 22.12+ and run this command again.' }
    if (-not (Test-Path -LiteralPath $appVite)) { throw 'Frontend dependencies missing. Run npm ci in frontend, then start again.' }
    & $appPython -c 'import flask, flask_sqlalchemy, flask_limiter, apscheduler, requests, numpy, pandas, sklearn'
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependencies missing. Run .\.venv\Scripts\python.exe -m pip install -r requirements.txt' }
    if (-not $backend) {
        $backendLog = Join-Path $appState 'backend.err.log'
        Start-Process -FilePath $appPython -ArgumentList @('-u', ('"' + (Join-Path $appRoot 'scripts\run_local.py') + '"')) -WorkingDirectory $appRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $appState 'backend.out.log') -RedirectStandardError $backendLog | Out-Null
        Wait-App 'http://127.0.0.1:5001/live' $backendLog
    }
    $runtime = Get-LocalJson '/api/local-runtime'
    if (-not $runtime -or $runtime.root -ne $appRoot) { throw 'Backend identity check failed. See .tmp\local-app\backend.err.log.' }
    $expected = & $appPython -c 'from scripts.run_local import source_fingerprint; print(source_fingerprint())'
    if ($runtime.source_fingerprint -ne $expected) { throw 'Backend source files changed. Run .\Start-ScorPred.ps1 -Restart to reload them safely.' }
    Wait-App 'http://127.0.0.1:5001/health' (Join-Path $appState 'backend.err.log')
    if (-not $frontend) {
        Start-Process -FilePath $appNode -ArgumentList @(('"' + $appVite + '"'), '--host', '127.0.0.1', '--port', '5173', '--strictPort') -WorkingDirectory $appFrontend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $appState 'frontend.out.log') -RedirectStandardError (Join-Path $appState 'frontend.err.log') | Out-Null
    }
    Wait-App 'http://127.0.0.1:5173/' (Join-Path $appState 'frontend.err.log')
    $proxied = Invoke-RestMethod 'http://127.0.0.1:5173/api/local-runtime' -TimeoutSec 5
    if ($proxied.pid -ne $runtime.pid) { throw 'Frontend is not connected to this backend.' }
    Write-Host 'ScorPred is ready: http://127.0.0.1:5173'
    Write-Host 'Loopback only. Research models disabled. Logs: .tmp\local-app\'
} finally {
    if ($appLocked) { $appMutex.ReleaseMutex() }
    $appMutex.Dispose()
}
