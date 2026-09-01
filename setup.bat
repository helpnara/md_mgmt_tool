@echo off
chcp 65001 > nul
setlocal
cd /d "%~dp0"

echo ============================================
echo   과제 이력 관리 도구 - 설치
echo ============================================
echo.

rem --- 1. 파이썬 확인 -------------------------------------------------
where py >nul 2>&1
if %errorlevel%==0 (
    set "PYCMD=py -3"
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "PYCMD=python"
    ) else (
        echo [오류] Python을 찾지 못했습니다.
        echo        https://www.python.org/downloads/ 에서 3.10 이상을 설치하고,
        echo        설치 화면의 "Add python.exe to PATH"를 반드시 체크하세요.
        pause
        exit /b 1
    )
)

echo 가상환경을 만듭니다...
%PYCMD% -m venv .venv
if errorlevel 1 (
    echo [오류] 가상환경을 만들지 못했습니다.
    pause
    exit /b 1
)

set "VPY=%~dp0.venv\Scripts\python.exe"

rem --- 2. 패키지 설치 (인터넷이 막혀 있으면 동봉된 vendor 폴더 사용) ----
if exist "%~dp0vendor" (
    echo 동봉된 패키지로 설치합니다 ^(인터넷 불필요^)...
    "%VPY%" -m pip install --no-index --find-links "%~dp0vendor" -r "%~dp0backend\requirements.txt"
    if not errorlevel 1 goto :done
    echo.
    echo 동봉 패키지 설치가 실패해 인터넷 설치를 시도합니다...
)

echo 인터넷에서 패키지를 내려받아 설치합니다...
"%VPY%" -m pip install --upgrade pip
"%VPY%" -m pip install -r "%~dp0backend\requirements.txt"
if errorlevel 1 (
    echo.
    echo [오류] 패키지 설치에 실패했습니다.
    echo        사내망에서 외부 접속이 막혀 있다면, 인터넷이 되는 PC에서
    echo        vendor 폴더가 포함된 배포본을 받아 사용하세요.
    pause
    exit /b 1
)

:done
echo.
echo ============================================
echo   설치가 끝났습니다. run.bat 을 실행하세요.
echo ============================================
pause
endlocal
