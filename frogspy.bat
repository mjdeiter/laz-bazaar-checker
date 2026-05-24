@echo off
:: FrogSpy launcher — double-click to open the GUI
:: Finds Python automatically (py launcher, then PATH)

setlocal

where py >nul 2>&1
if %errorlevel% == 0 (
    start "" py "%~dp0frogspy.py" --gui
    goto :eof
)

where python >nul 2>&1
if %errorlevel% == 0 (
    start "" python "%~dp0frogspy.py" --gui
    goto :eof
)

where python3 >nul 2>&1
if %errorlevel% == 0 (
    start "" python3 "%~dp0frogspy.py" --gui
    goto :eof
)

echo Python not found. Please install Python from https://python.org
pause
