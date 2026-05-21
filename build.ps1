$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $root
try {
    python -m pip install --upgrade pyinstaller selenium pystray pillow
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao instalar ou atualizar dependencias do build."
    }

    # Uses the project spec file so hidden imports (pystray, Pillow) are included.
    python -m PyInstaller --clean -y "Mezzold Connect.spec"
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao gerar o executavel do Mezzold Connect."
    }
}
finally {
    Pop-Location
}
