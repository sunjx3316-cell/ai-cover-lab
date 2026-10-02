param(
  [ValidateSet('Minimal','Ying','All')][string]$Feature = 'Minimal',
  [string]$InstallRoot = 'D:\AI-Cover-Lab'
)
$ErrorActionPreference = 'Stop'
$Lab = [IO.Path]::GetFullPath($InstallRoot)
$Source = [IO.Path]::GetFullPath($PSScriptRoot)
if (-not (Test-Path -LiteralPath ([IO.Path]::GetPathRoot($Lab)))) { throw "Drive does not exist: $Lab. Specify -InstallRoot." }
New-Item -ItemType Directory -Path $Lab -Force | Out-Null
if ($Source -ne $Lab) {
  foreach ($File in Get-ChildItem -LiteralPath $Source -File) {
    if ($File.Extension -in @('.py','.ps1','.cmd','.md','.txt') -or $File.Name -in @('LICENSE','.gitignore')) {
      Copy-Item -LiteralPath $File.FullName -Destination $Lab -Force
    }
  }
}
foreach ($Name in @('runtime','runtime\uv','cache\uv','cache\pip','cache\huggingface','cache\torch','temp','external','envs','models','logs','outputs','exports')) {
  New-Item -ItemType Directory -Path "$Lab\$Name" -Force | Out-Null
}
$env:UV_CACHE_DIR = "$Lab\cache\uv"
$env:UV_PYTHON_INSTALL_DIR = "$Lab\runtime\python"
$env:UV_PYTHON_BIN_DIR = "$Lab\runtime\python-bin"
$env:PIP_CACHE_DIR = "$Lab\cache\pip"
$env:HF_HOME = "$Lab\cache\huggingface"
$env:TORCH_HOME = "$Lab\cache\torch"
$env:TEMP = "$Lab\temp"
$env:TMP = "$Lab\temp"
$env:PYTHONUTF8 = '1'
$env:UV_HTTP_TIMEOUT = '300'
$env:HF_HUB_DOWNLOAD_TIMEOUT = '120'
$Uv = "$Lab\runtime\uv\uv.exe"
if (-not (Test-Path -LiteralPath $Uv)) {
  $Archive = "$Lab\temp\uv-install.zip"
  Invoke-WebRequest -Uri 'https://github.com/astral-sh/uv/releases/download/0.12.22/uv-x86_64-pc-windows-msvc.zip' -OutFile $Archive
  Expand-Archive -LiteralPath $Archive -DestinationPath "$Lab\runtime\uv" -Force
}
$Python = "$Lab\envs\ying\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
  & $Uv python install 3.10.22
  if ($LASTEXITCODE -ne 0) { throw 'Python installation failed' }
  & $Uv venv --python 3.10.22 "$Lab\envs\ying"
  if ($LASTEXITCODE -ne 0) { throw 'Environment installation failed' }
}
& $Uv pip install --python $Python torch==2.4.0 torchaudio==2.4.0 torchvision==0.19.0 --index-url https://download.pytorch.org/whl/cu124
if ($LASTEXITCODE -ne 0) { throw 'CUDA PyTorch installation failed' }
& $Uv pip install --python $Python -r "$Lab\requirements-engine.txt"
if ($LASTEXITCODE -ne 0) { throw 'Engine dependencies installation failed' }
foreach ($Backend in @(
  @{ Name='YingMusic-SVC'; Url='https://github.com/GiantAILab/YingMusic-SVC.git'; Ref='4974a80c6044c4557059548409379f6365129f88' },
  @{ Name='Applio'; Url='https://github.com/IAHispano/Applio.git'; Ref='55fe0b976a6990bb75261c32ccecf6bfca3198f1' }
)) {
  $Repo = "$Lab\external\$($Backend.Name)"
  if (-not (Test-Path -LiteralPath "$Repo\.git")) {
    & git init $Repo
    if ($LASTEXITCODE -ne 0) { throw 'Git is required: https://git-scm.com/download/win' }
    & git -C $Repo remote add origin $Backend.Url
    & git -C $Repo fetch --depth 1 origin $Backend.Ref
    if ($LASTEXITCODE -ne 0) { throw 'Backend download failed' }
    & git -C $Repo checkout --detach FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Backend checkout failed' }
  }
  $Head = & git -C $Repo rev-parse HEAD
  if ($Head -ne $Backend.Ref) { throw "Backend revision mismatch in $Repo; preserve local changes and inspect manually." }
}
Push-Location $Lab
try {
  if ($Feature -in @('Minimal','All')) {
    & $Python "$Lab\prepare_models.py" --feature separator
    if ($LASTEXITCODE -ne 0) { throw 'Separation model preparation failed' }
    & $Python "$Lab\prepare_rvc.py"
    if ($LASTEXITCODE -ne 0) { throw 'Training model preparation failed' }
  }
  if ($Feature -in @('Ying','All')) {
    & $Python "$Lab\prepare_models.py" --feature ying
    if ($LASTEXITCODE -ne 0) { throw 'Optional reference-conversion model preparation failed' }
  }
  & $Python "$Lab\rvc_worker.py" check
  if ($LASTEXITCODE -ne 0) { throw 'CUDA engine check failed' }
} finally { Pop-Location }
Write-Host "Setup complete: $Lab. Run Start-Cover.cmd."
