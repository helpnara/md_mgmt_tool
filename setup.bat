@echo off
rem Korean text is intentionally NOT used in this file.
rem Windows cmd reads .bat files with the OEM codepage (cp949 on Korean Windows),
rem so UTF-8 Korean here breaks parsing. All messages live in setup.py instead.
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 goto try_python
py -3 setup.py
goto end

:try_python
where python >nul 2>&1
if errorlevel 1 goto no_python
python setup.py
goto end

:no_python
echo.
echo [ERROR] Python was not found on this PC.
echo.
echo   1. Install Python 3.10 or newer:  https://www.python.org/downloads/
echo   2. On the first install screen, CHECK "Add python.exe to PATH".
echo   3. Close this window, then run setup.bat again.
echo.
echo   (Korean guide: see the file named INSTALL-KR.txt)
echo.

:end
pause
