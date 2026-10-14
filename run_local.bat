@echo off
rem ==============================================================
rem  ReportSPPR: local run of RepSSPR.ipynb in Jupyter (my-FT T-99).
rem  Runs from this folder: data in source\, reports in result\.
rem  AI = OpenCoder: start the local proxy (127.0.0.1:8787) first.
rem  First time: py -m pip install -r requirements.txt
rem ==============================================================
cd /d "%~dp0"
if not exist "RepSSPR.ipynb" (echo RepSSPR.ipynb not found in %CD% & pause & exit /b 1)
if not exist "source" mkdir "source"
py -m jupyter lab RepSSPR.ipynb
if errorlevel 1 (echo Jupyter did not start: py -m pip install -r requirements.txt & pause)
