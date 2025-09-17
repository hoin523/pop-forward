@echo off
cd /d .\pop-foward

REM pop_gmail.py start
start "" /B pythonw pop_gmail.py
REM 잠시 대기 후 pop_gmail.py PID 찾기
timeout /t 2 > nul
for /f "tokens=2 delims==; " %%a in ('wmic process where "CommandLine like '%%pop_gmail.py%%'" get ProcessId /format:value ^| find "="') do (
    echo %%a > pop_gmail.pid
)

REM deploy_reminder.py start
start "" /B pythonw deploy_reminder.py
timeout /t 2 > nul
for /f "tokens=2 delims==; " %%a in ('wmic process where "CommandLine like '%%deploy_reminder.py%%'" get ProcessId /format:value ^| find "="') do (
    echo %%a > deploy_reminder.pid
)

REM keyword_bot.py start
start "" /B pythonw keyword\keyword_bot.py
timeout /t 2 > nul
for /f "tokens=2 delims==; " %%a in ('wmic process where "CommandLine like '%%keyword_bot.py%%'" get ProcessId /format:value ^| find "="') do (
    echo %%a > keyword_bot.pid
)

echo Python started to service.
