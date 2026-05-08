$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $root
try {
    python -m pip install --upgrade pyinstaller selenium
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao instalar ou atualizar dependencias do build."
    }

    python -m PyInstaller --clean -y --onefile --noconsole --name "Mezzold Connect" --collect-all selenium main.py
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao gerar o executavel do Mezzold Connect."
    }
}
finally {
    Pop-Location
}
