@echo off
chcp 65001 >nul 2>&1
setlocal

REM Install the commit gate that requires WORK_STATUS.md to change whenever a
REM .py file changes.
REM
REM Why an installer is needed: .git\hooks is not tracked, so a fresh clone has
REM no hook. Copying it by hand is easy to forget, and a hook nobody installed
REM is the same as no hook at all.
REM
REM Why this file is pure ASCII: a .bat holding UTF-8 Korean gets mis-split by
REM a cp949 console (a trailing byte can land on " or &, and the line falls
REM apart). Same reasoning as run_tests.bat.

set "ROOT=%~dp0"
set "SRC=%ROOT%.githooks\pre-commit"
set "DST=%ROOT%.git\hooks\pre-commit"

if not exist "%SRC%" (
  echo [install-hook] missing %SRC%
  exit /b 1
)

if not exist "%ROOT%.git" (
  echo [install-hook] %ROOT%.git not found - not a git repository
  exit /b 1
)

if not exist "%ROOT%.git\hooks" mkdir "%ROOT%.git\hooks"

copy /y "%SRC%" "%DST%" >nul
if errorlevel 1 (
  echo [install-hook] failed to copy
  exit /b 1
)

echo [install-hook] installed %DST%
echo [install-hook] commits touching a .py file now require WORK_STATUS.md.
echo [install-hook] bypass on purpose with: git commit --no-verify
exit /b 0
