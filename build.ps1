param(
    [switch]$SkipInstall,
    [switch]$SkipTests,
    [switch]$DebugConsole
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot ".venv_build\Scripts\python.exe"

Push-Location $projectRoot
try {
    if (!(Test-Path -LiteralPath $venvPython)) {
        py -m venv (Join-Path $projectRoot ".venv_build")
        if ($LASTEXITCODE -ne 0) {
            throw "Nao foi possivel criar o ambiente .venv_build."
        }
    }

    if (!$SkipInstall) {
        & $venvPython -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            throw "Falha ao atualizar o pip."
        }
        & $venvPython -m pip install --requirement requirements-build.txt
        if ($LASTEXITCODE -ne 0) {
            throw "Falha ao instalar as dependencias do build."
        }
    }

    & $venvPython -m compileall -q main.py app_log.py app_update.py auth.py background_worker.py campaigns.py compliance.py contact_service.py contacts.py data_export.py database.py flet_compat.py logger.py network.py runtime.py startup.py tray_icon.py warmup.py whatsapp.py screens installer
    if ($LASTEXITCODE -ne 0) {
        throw "A compilacao estatica encontrou erros."
    }

    if (!$SkipTests) {
        & $venvPython -m unittest discover -s tests -p "test_*.py" -v
        if ($LASTEXITCODE -ne 0) {
            throw "Os testes falharam; o executavel nao sera gerado."
        }
    }

    $packArgs = @(
        "-m", "flet.cli", "pack", "main.py",
        "--name", "MezzoldConnect",
        "--product-name", "Mezzold Connect",
        "--file-description", "Mezzold Connect - Gestao de campanhas WhatsApp",
        "--product-version", "2.1.0",
        "--file-version", "2.1.0.0",
        "--company-name", "Mezzold Studios",
        "--copyright", "Copyright (c) Mezzold Studios",
        "--hidden-import", "selenium", "selenium.webdriver", "selenium.webdriver.chrome", "selenium.webdriver.edge", "pystray", "PIL",
        "--yes"
    )
    if ($DebugConsole) {
        $packArgs += @("--debug-console", "all")
    }

    & $venvPython @packArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao gerar o executavel do Mezzold Connect."
    }

    $appExe = Join-Path $projectRoot "dist\MezzoldConnect.exe"
    if (!(Test-Path -LiteralPath $appExe)) {
        throw "O build terminou sem criar dist\MezzoldConnect.exe."
    }

    $artifact = Get-Item -LiteralPath $appExe
    Write-Host "Build concluido: $($artifact.FullName) ($($artifact.Length) bytes)"
}
finally {
    Pop-Location
}
