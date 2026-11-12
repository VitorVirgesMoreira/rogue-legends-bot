@echo off
setlocal
pushd "%~dp0.." || exit /b 1
if not exist ".venv\Scripts\python.exe" (
    echo Python do bot nao encontrado. Configure o ambiente .venv na pasta do projeto.
    popd
    exit /b 1
)
".venv\Scripts\python.exe" -m roguebot %*
set "roguebot_exit_code=%errorlevel%"
popd
exit /b %roguebot_exit_code%
