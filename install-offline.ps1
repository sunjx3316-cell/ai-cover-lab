param([string]$Destination = (Join-Path $PSScriptRoot 'AI-Cover-Lab-v0.1.0-beta'))
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$Manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'offline-manifest.json') -Raw | ConvertFrom-Json
function Assert-Hash($Path, $Bytes, $Sha) {
  $Stream = [IO.File]::OpenRead($Path)
  $Hash = [Security.Cryptography.SHA256]::Create()
  try {
    $Actual = ([BitConverter]::ToString($Hash.ComputeHash($Stream))).Replace('-', '').ToLowerInvariant()
    if ($Stream.Length -ne $Bytes -or $Actual -ne $Sha) { throw "Checksum failed: $Path" }
  } finally { $Hash.Dispose(); $Stream.Dispose() }
}
$Destination = [IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $Destination) { throw 'Destination already exists. Choose a new empty path with -Destination.' }
if ($Manifest.archive -ne 'AI-Cover-Lab-Windows-offline.zip') { throw 'Invalid archive name.' }
$Zip = Join-Path $PSScriptRoot $Manifest.archive
foreach ($Part in $Manifest.parts) {
  if ($Part.name -notmatch '^AI-Cover-Lab-Windows-offline\.zip\.part\d{2,3}$') { throw 'Invalid part name.' }
  Write-Host "Checking $($Part.name)"
  Assert-Hash (Join-Path $PSScriptRoot $Part.name) $Part.bytes $Part.sha256
}
if (-not (Test-Path -LiteralPath $Zip)) {
  $Stream = [IO.File]::Open($Zip, [IO.FileMode]::CreateNew)
  try {
    foreach ($Part in $Manifest.parts) {
      $Input = [IO.File]::OpenRead((Join-Path $PSScriptRoot $Part.name))
      try { $Input.CopyTo($Stream) } finally { $Input.Dispose() }
    }
  } finally { $Stream.Dispose() }
}
Write-Host 'Checking complete archive...'
Assert-Hash $Zip $Manifest.bytes $Manifest.sha256
$Archive = [IO.Compression.ZipFile]::OpenRead($Zip)
try {
  $Prefix = $Destination.TrimEnd('\') + '\'
  $Seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
  foreach ($Entry in $Archive.Entries) {
    $Target = [IO.Path]::GetFullPath((Join-Path $Destination $Entry.FullName))
    if (-not $Target.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase) -or -not $Seen.Add($Target)) { throw 'Unsafe archive path.' }
    if (-not $Entry.FullName.StartsWith('AI-Cover-Lab/')) { throw 'Invalid archive root.' }
  }
  New-Item -ItemType Directory -Path $Destination | Out-Null
  Write-Host 'Extracting offline runtime. This can take several minutes...'
  foreach ($Entry in $Archive.Entries) {
    $Target = [IO.Path]::GetFullPath((Join-Path $Destination $Entry.FullName))
    if ($Entry.FullName.EndsWith('/')) { New-Item -ItemType Directory -Force -Path $Target | Out-Null; continue }
    New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($Target)) | Out-Null
    [IO.Compression.ZipFileExtensions]::ExtractToFile($Entry, $Target, $false)
  }
} finally { $Archive.Dispose() }
Write-Host "Ready: $Destination\AI-Cover-Lab\Start-Cover.cmd"
