@echo off
chcp 65001 > nul
setlocal
echo 가상환경을 만들고 필요한 패키지를 설치합니다...

py -m venv "%~dp0.venv"
if errorlevel 1 (
    echo.
    echo [오류] Python을 찾지 못했습니다. https://www.python.org 에서 3.10 이상을 설치한 뒤
    echo        설치 화면의 "Add python.exe to PATH"를 체크했는지 확인하세요.
    pause
    exit /b 1
)

"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0backend\requirements.txt"

echo.
echo 설치가 끝났습니다. run.bat 을 실행하세요.
pause
endlocal
