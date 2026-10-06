@echo off
:: build/windows/build.bat — Lumina Windows Production Build Script
:: Produces: release\Lumina Setup <version>.exe  +  Lumina <version>.exe (portable)

echo 🔷 Lumina Windows Build Script

cd /d "%~dp0..\.."

:: ── Verify Node ──────────────────────────────────────────────────────────────
where node >nul 2>&1
if errorlevel 1 (
  echo ❌ Node.js not found. Install Node.js 18+ from https://nodejs.org
  exit /b 1
)

for /f "tokens=*" %%v in ('node -v') do set NODE_VER=%%v
echo ✓ Node: %NODE_VER%

:: ── Install deps ─────────────────────────────────────────────────────────────
echo.
echo 📦 Installing npm dependencies...
call npm ci --prefer-offline || call npm install

:: ── Windows Python env check ─────────────────────────────────────────────────
if exist "python-dependencies\windows\python.exe" (
  echo ✓ Windows bundled Python found.
) else (
  echo ⚠️  Windows bundled Python not found. The app will use system Python as fallback.
)

:: ── Build ─────────────────────────────────────────────────────────────────────
echo.
echo 🏗️  Building Windows EXE + NSIS installer...
call npm run build:win -- --publish=never

echo.
echo ✅ Windows build complete! Output in: release\
dir /b "release\*.exe" 2>nul
