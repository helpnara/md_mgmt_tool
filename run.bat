@echo off
rem ASCII only - see the comment in setup.bat for the reason.
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto use_venv

where py >nul 2>&1
if errorlevel 1 goto try_python
py -3 run.py %*
goto after_run

:try_python
where python >nul 2>&1
if errorlevel 1 goto no_python
python run.py %*
goto after_run

:use_venv
".venv\Scripts\python.exe" run.py %*
goto after_run

:no_python
echo.
echo [ERROR] Python was not found. Run setup.bat first.
echo.
pause
goto end

:after_run
rem Keep the window open when the program stopped with an error,
rem otherwise the message disappears before anyone can read it (TODO 163).
if errorlevel 1 (
  echo.
  echo [ERROR] The program stopped. Read the message above.
  pause
)

:end
