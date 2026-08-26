param(
    [switch]$SkipAppBuild,
    [switch]$SkipInstall,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv_build\Scripts\python.exe"
$appExe = Join-Path $projectRoot "dist\MezzoldConnect.exe"
$installerName = "Mezzold.Connect.Setup.v2.1.0"

Push-Location $projectRoot
try {
    if (!$SkipAppBuild) {
        $buildArgs = @{}
        if ($SkipInstall) { $buildArgs.SkipInstall = $true }
        if ($SkipTests) { $buildArgs.SkipTests = $true }
        & (Join-Path $projectRoot "build.ps1") @buildArgs
    }

    if (!(Test-Path -LiteralPath $appExe)) {
        throw "Executavel principal ausente: $appExe"
    }
    if (!(Test-Path -LiteralPath $venvPython)) {
        throw "Ambiente de build ausente: $venvPython"
    }

    $workPath = Join-Path $PSScriptRoot "build"
    $versionFile = Join-Path $PSScriptRoot "version_info.txt"
    $addBinary = "$appExe;."

    & $venvPython -m PyInstaller `
        --clean `
        --noconfirm `
        --onefile `
        --windowed `
        --name $installerName `
        --distpath (Join-Path $projectRoot "dist") `
        --workpath $workPath `
        --specpath $workPath `
        --version-file $versionFile `
        --add-binary $addBinary `
        (Join-Path $PSScriptRoot "installer_app.py")
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao gerar o instalador."
    }

    $setupExe = Join-Path $projectRoot "dist\$installerName.exe"
    if (!(Test-Path -LiteralPath $setupExe)) {
        throw "O build nao criou $setupExe."
    }
    $artifact = Get-Item -LiteralPath $setupExe
    Write-Host "Instalador concluido: $($artifact.FullName) ($($artifact.Length) bytes)"
}
finally {
    Pop-Location
}
