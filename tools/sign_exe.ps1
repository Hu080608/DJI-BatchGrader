param(
    [Parameter(Mandatory=$true)][string]$Exe,
    [Parameter(Mandatory=$true)][string]$PfxPath,
    [Parameter(Mandatory=$true)][string]$PfxPassword
)
$ErrorActionPreference = "Stop"
$signtool = Get-Command signtool.exe -ErrorAction Stop
& $signtool.Source sign /fd SHA256 /td SHA256 /tr http://timestamp.digicert.com /f $PfxPath /p $PfxPassword $Exe
if ($LASTEXITCODE -ne 0) { throw "signtool failed with exit code $LASTEXITCODE" }
Write-Host "Signed: $Exe"
