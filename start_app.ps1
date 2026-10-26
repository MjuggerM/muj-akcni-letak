$ErrorActionPreference = 'Stop'

$backendDir = Join-Path $PSScriptRoot 'backend'
$frontendDir = Join-Path $PSScriptRoot 'frontend'
$backendPort = 8000
$tempDir = [System.IO.Path]::GetTempPath()
$backendOut = Join-Path $tempDir 'muj-akcni-letak-backend-out.log'
$backendErr = Join-Path $tempDir 'muj-akcni-letak-backend-error.log'
$frontendOut = Join-Path $tempDir 'muj-akcni-letak-frontend-out.log'
$frontendErr = Join-Path $tempDir 'muj-akcni-letak-frontend-error.log'

function Test-TcpPort {
    param([int]$Port)

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connect = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if (-not $connect.AsyncWaitHandle.WaitOne(500)) { return $false }
        $client.EndConnect($connect)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Test-BackendHealth {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$backendPort/api/health" -TimeoutSec 2
        return $health.status -eq 'ok'
    }
    catch {
        return $false
    }
}

function Wait-ForBackend {
    param([int]$Seconds)

    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        if (Test-BackendHealth) { return $true }
        Start-Sleep -Seconds 1
    } while ([DateTime]::UtcNow -lt $deadline)
    return $false
}

function Wait-ForPort {
    param([int]$Port, [int]$Seconds)

    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        if (Test-TcpPort -Port $Port) { return $true }
        Start-Sleep -Seconds 1
    } while ([DateTime]::UtcNow -lt $deadline)
    return $false
}

try {
    if (-not (Test-Path $backendDir)) { throw "Backend folder not found: $backendDir" }
    if (-not (Test-Path $frontendDir)) { throw "Frontend folder not found: $frontendDir" }

    $frontendPort = $null
    foreach ($port in 3000..3010) {
        if (-not (Test-TcpPort -Port $port)) {
            $frontendPort = $port
            break
        }
    }
    if ($null -eq $frontendPort) { throw 'No free frontend port in range 3000-3010.' }

    if (-not (Test-BackendHealth)) {
        if (Test-TcpPort -Port $backendPort) {
            throw "Port $backendPort is in use, but /api/health does not respond. Stop the process using that port and retry."
        }

        $python = Join-Path $backendDir '.venv\Scripts\python.exe'
        if (-not (Test-Path $python)) {
            $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
            if ($null -eq $pythonCommand) { throw 'Python was not found. Install Python or create backend\.venv first.' }
            $python = $pythonCommand.Source
        }

        Start-Process -FilePath $python `
            -ArgumentList '-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload' `
            -WorkingDirectory $backendDir `
            -RedirectStandardOutput $backendOut `
            -RedirectStandardError $backendErr `
            -WindowStyle Hidden | Out-Null

        if (-not (Wait-ForBackend -Seconds 60)) {
            Write-Host "Backend did not become ready. Logs: $backendOut and $backendErr" -ForegroundColor Red
            if (Test-Path $backendErr) { Get-Content -Tail 40 $backendErr }
            if (Test-Path $backendOut) { Get-Content -Tail 40 $backendOut }
            exit 1
        }
    }

    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($null -eq $npm) { throw 'npm.cmd was not found. Install Node.js and npm first.' }

    Start-Process -FilePath $env:ComSpec `
        -ArgumentList "/d /c npm run dev -- --host 127.0.0.1 --port $frontendPort --strictPort" `
        -WorkingDirectory $frontendDir `
        -RedirectStandardOutput $frontendOut `
        -RedirectStandardError $frontendErr `
        -WindowStyle Hidden | Out-Null

    if (-not (Wait-ForPort -Port $frontendPort -Seconds 60)) {
        Write-Host "Frontend did not become ready. Logs: $frontendOut and $frontendErr" -ForegroundColor Red
        if (Test-Path $frontendErr) { Get-Content -Tail 40 $frontendErr }
        if (Test-Path $frontendOut) { Get-Content -Tail 40 $frontendOut }
        exit 1
    }

    $url = "http://localhost:$frontendPort"
    Write-Host "Backend is ready on http://127.0.0.1:$backendPort"
    Write-Host "Frontend is ready on $url"
    Start-Process $url
}
catch {
    Write-Host "Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
