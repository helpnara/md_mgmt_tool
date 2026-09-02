@echo off
rem ASCII only - see the comment in setup.bat for the reason.
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto use_venv

where py >nul 2>&1
if errorlevel 1 goto try_python
py -3 run.py %*
goto end

:try_python
where python >nul 2>&1
if errorlevel 1 goto no_python
python run.py %*
goto end

:use_venv
".venv\Scripts\python.exe" run.py %*
goto end

:no_python
echo.
echo [ERROR] Python was not found. Run setup.bat first.
echo.
pause

:end
