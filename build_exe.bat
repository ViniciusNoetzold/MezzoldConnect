@echo off
echo ==============================================
echo   Compilando Mezzold Connect V2 (Flet)
echo ==============================================
echo.

cd /d "%~dp0"

echo Limpando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "*.spec" del /q "*.spec"

echo.
echo Compilando o executavel com flet...
call ".venv_build\Scripts\python.exe" -m flet.cli pack main.py --name "MezzoldConnect" --add-data "screens;screens"

echo.
if exist "dist\MezzoldConnect.exe" (
    echo ==============================================
    echo   BUILD CONCLUIDO COM SUCESSO!
    echo   Executavel: dist\MezzoldConnect.exe
    echo ==============================================
) else (
    echo ==============================================
    echo   Verifique a pasta dist/
    echo ==============================================
)
pause