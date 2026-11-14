@echo off
REM Wrapper so the pipeline runs without changing the PowerShell execution policy.
REM   run_all.cmd                  -> real Dify agent + real judge
REM   run_all.cmd -Policy scripted -Mock   -> free smoke test (no API calls)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_all.ps1" %*
