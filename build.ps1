$ErrorActionPreference = "Stop"

# Uses the project spec file so hidden imports (pystray, Pillow) are included.
python -m PyInstaller --clean -y "Mezzold Connect.spec"
