param(
    [Parameter(Mandatory=$true)][string]$Version
)
$ErrorActionPreference = "Stop"
$tag = $Version.Trim()
$version = $tag.TrimStart('v')
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root 'dist\DJI_DLogM_BatchGrader'
$exe = Join-Path $dist 'DJI_DLogM_BatchGrader.exe'
if (-not (Test-Path $exe)) { throw "Build output not found: $exe" }
$releaseDir = Join-Path $root 'release'
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
$assetName = "DJI_DLogM_BatchGrader_Windows_x64_$tag.zip"
$assetPath = Join-Path $releaseDir $assetName
Remove-Item $assetPath -Force -ErrorAction SilentlyContinue
Remove-Item "$assetPath.sha256" -Force -ErrorAction SilentlyContinue
Push-Location $root
try {
    Compress-Archive -Path $dist -DestinationPath $assetPath -CompressionLevel Optimal
    $hash = (Get-FileHash $assetPath -Algorithm SHA256).Hash.ToLower()
    "$hash  $assetName" | Set-Content "$assetPath.sha256" -Encoding ascii
    Write-Host "Created: $assetPath"
    Write-Host "SHA256:  $hash"
} finally {
    Pop-Location
}
