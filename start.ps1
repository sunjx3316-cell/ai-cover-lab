$ErrorActionPreference = 'Stop'
$Lab = $PSScriptRoot
$Portable = Join-Path $Lab 'runtime\python\python.exe'
$Python = if (Test-Path -LiteralPath $Portable) { $Portable } else { Join-Path $Lab 'envs\ying\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $Python)) { throw 'Python runtime missing. Use the offline release or run Setup.cmd.' }
New-Item -ItemType Directory -Force -Path (Join-Path $Lab 'logs') | Out-Null
$Hash = [System.Security.Cryptography.SHA256]::Create()
try { $Token = ([BitConverter]::ToString($Hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($Lab.ToLowerInvariant())))).Replace('-', '').ToLowerInvariant() } finally { $Hash.Dispose() }
$env:PYTHONUTF8 = '1'
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONPATH = $Lab
if ($Python -eq $Portable) { $env:PYTHONHOME = Split-Path $Portable } else { Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue }
$Selected = $null
foreach ($Port in 7867..7886) {
  $Url = "http://127.0.0.1:$Port"
  try {
    $Health = Invoke-RestMethod "$Url/lab-health" -TimeoutSec 1
    if ($Health.application -eq 'AI Cover Lab' -and $Health.root_token -eq $Token) { Start-Process "$Url/"; exit 0 }
  } catch { }
  $Listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
  try { $Listener.Start(); $Selected = $Port } catch { } finally { $Listener.Stop() }
  if ($Selected) { break }
}
if (-not $Selected) { throw 'No free port between 7867 and 7886.' }
$env:AI_COVER_PORT = [string]$Selected
$Process = Start-Process -FilePath $Python -ArgumentList @('-u', "`"$Lab\app.py`"") -WorkingDirectory $Lab -WindowStyle Hidden -PassThru -RedirectStandardOutput "$Lab\logs\web.out.log" -RedirectStandardError "$Lab\logs\web.err.log"
for ($i = 0; $i -lt 90; $i++) {
  Start-Sleep -Seconds 1
  if ($Process.HasExited) { throw "Startup failed. See $Lab\logs\web.err.log" }
  try {
    $Health = Invoke-RestMethod "$Url/lab-health" -TimeoutSec 1
    if ($Health.application -eq 'AI Cover Lab' -and $Health.root_token -eq $Token) { Start-Process "$Url/"; exit 0 }
  } catch { }
}
throw "Startup timed out. See $Lab\logs\web.err.log"
