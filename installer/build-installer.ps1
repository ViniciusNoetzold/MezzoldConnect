$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$distExe = Join-Path $root "dist\Mezzold Connect.exe"
$targetName = Join-Path $PSScriptRoot "Mezzold Connect Setup.exe"
$installerSource = Join-Path $PSScriptRoot "installer_app.py"
$workPath = Join-Path $root "build\Mezzold Connect Setup"
$buildScript = Join-Path $root "build.ps1"

Write-Host "Gerando executavel mais recente do aplicativo..."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $buildScript
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao gerar o executavel principal."
}

if (!(Test-Path $distExe)) {
    throw "Executavel principal nao encontrado apos o build: $distExe"
}

Remove-Item -LiteralPath $targetName -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $workPath -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $PSScriptRoot "Mezzold Connect Setup.spec") -Force -ErrorAction SilentlyContinue

python -m PyInstaller `
    --clean `
    -y `
    --onefile `
    --noconsole `
    --name "Mezzold Connect Setup" `
    --distpath $PSScriptRoot `
    --workpath $workPath `
    --specpath $PSScriptRoot `
    --add-data "$distExe;." `
    $installerSource

if (!(Test-Path $targetName)) {
    throw "Installer was not created."
}

Write-Host "Installer created: $targetName"
