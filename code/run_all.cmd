@echo off
REM Wrapper so the pipeline runs without changing the PowerShell execution policy.
REM   run_all.cmd                     -> real Dify agent + real judge
REM   run_all.cmd -RunId B-refactor   -> name the batch (see output\runs\B-refactor\)
REM   run_all.cmd -Limit 2            -> only the first two tasks
REM There is no -Mock anymore (issue #7): mock scores must not share a file with real ones.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_all.ps1" %*
