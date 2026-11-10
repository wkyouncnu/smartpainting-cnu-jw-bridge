@echo off
chcp 65001 >NUL
REM JW 수신 검증기 - 더블클릭으로 실행 (Python 3.8 이상 필요, 추가 설치 없음)
REM 서버 IP 가 다르면 아래 --host 값을 바꾸세요. 같은 PC 의 WSL 서버면 127.0.0.1
cd /d "%~dp0"
set ARGS=--host 127.0.0.1 --port 5010 %*
where py >NUL 2>&1
if %errorlevel%==0 (py -3 jw_receiver_gui.py %ARGS%) else (python jw_receiver_gui.py %ARGS%)
if errorlevel 1 pause
