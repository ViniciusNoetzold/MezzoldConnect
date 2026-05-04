$ErrorActionPreference = "Stop"

python -m PyInstaller --clean -y --onefile --noconsole --name "Mezzold Connect" main.py
