$ErrorActionPreference = 'Stop'
$App = Join-Path $PSScriptRoot 'app.py'
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
  $_.CommandLine -and ($_.CommandLine.Contains('"' + $App + '"') -or $_.CommandLine.EndsWith(' ' + $App))
} | ForEach-Object { & taskkill.exe /PID $_.ProcessId /T /F | Out-Null }
