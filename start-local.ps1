# Start API and worker together; stop worker when the API exits.
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
$workerProcess = $null
try {
    python -m app.seed
    if ($LASTEXITCODE -ne 0) { throw 'Demo initialization failed.' }
    $taskPython = (Get-Command python).Source
    $workerProcess = Start-Process -FilePath $taskPython -ArgumentList '-m','app.worker' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput '.local/worker.out.log' -RedirectStandardError '.local/worker.err.log' -PassThru
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
} finally {
    if ($workerProcess -and -not $workerProcess.HasExited) { Stop-Process -Id $workerProcess.Id }
    Pop-Location
}
