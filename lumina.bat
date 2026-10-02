@echo off
setlocal enabledelayedexpansion

rem Lumina CLI Wrapper for Windows
set SCRIPT_DIR=%~dp0
set BUNDLED_PY=%SCRIPT_DIR%python-dependencies\windows\python.exe

if exist "%BUNDLED_PY%" (
    set PYTHON_BIN=%BUNDLED_PY%
    set PYTHONHOME=%SCRIPT_DIR%python-dependencies\windows
) else (
    where python >nul 2>nul
    if !errorlevel! equ 0 (
        set PYTHON_BIN=python
    ) else (
        where py >nul 2>nul
        if !errorlevel! equ 0 (
            set PYTHON_BIN=py
        ) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
            set PYTHON_BIN=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
        ) else if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
            set PYTHON_BIN=%LOCALAPPDATA%\Programs\Python\Python311\python.exe
        ) else if exist "C:\Python312\python.exe" (
            set PYTHON_BIN=C:\Python312\python.exe
        ) else if exist "C:\Python311\python.exe" (
            set PYTHON_BIN=C:\Python311\python.exe
        ) else (
            echo [Lumina CLI] Error: No Python executable found.
            echo Please ensure python-dependencies\windows\python.exe exists or install Python 3.10+ from python.org.
            exit /b 1
        )
    )
)

set WIN_SP=%SCRIPT_DIR%python-dependencies\windows\Lib\site-packages
if exist "%WIN_SP%" (
    if defined PYTHONPATH (
        set PYTHONPATH=%WIN_SP%;%SCRIPT_DIR%scripts;%SCRIPT_DIR%;%PYTHONPATH%
    ) else (
        set PYTHONPATH=%WIN_SP%;%SCRIPT_DIR%scripts;%SCRIPT_DIR%
    )
)

"%PYTHON_BIN%" "%SCRIPT_DIR%Lumina.py" %*
endlocal
