@echo off
rem ==============================================================
rem  ReportSPPR: local run of RepSSPR.ipynb in Jupyter (my-FT T-99).
rem  1) git pull: always the latest version from main (production).
rem  2) Fresh working copy run\RepSSPR.ipynb (not in git): Jupyter saves
rem     outputs there, so RepSSPR.ipynb stays clean and git pull works.
rem  3) Jupyter Lab: data in source\, reports in result\,
rem     parameters and keys in .env (sample: .env.example).
rem  AI = OpenCoder: start the local proxy (127.0.0.1:8787) first.
rem  First time: py -m pip install -r requirements.txt
rem ==============================================================
cd /d "%~dp0"
if not exist "RepSSPR.ipynb" (echo RepSSPR.ipynb not found in %CD% & pause & exit /b 1)
where git >nul 2>nul && (
  git pull --ff-only origin main || (echo. & echo WARNING: git pull failed - local changes or no network. Running the version on disk. & echo Check: git status & pause)
) || echo WARNING: git not found - running the version on disk.
if not exist "source" mkdir "source"
if not exist "run" mkdir "run"
copy /Y "RepSSPR.ipynb" "run\RepSSPR.ipynb" >nul
if not exist ".env" echo No .env yet: defaults are used. Sample with all parameters: .env.example
set "REPORTSPPR_ROOT=%~dp0"
py -m jupyter lab "run\RepSSPR.ipynb"
if errorlevel 1 (echo Jupyter did not start: py -m pip install -r requirements.txt & pause)
