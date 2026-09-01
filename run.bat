@echo off
chcp 65001 > nul
setlocal

rem 가상환경이 있으면 그 파이썬을, 없으면 시스템 파이썬을 쓴다.
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY=%~dp0.venv\Scripts\python.exe"
) else (
    set "PY=py"
)

"%PY%" "%~dp0run.py" %*
if errorlevel 1 pause
endlocal
