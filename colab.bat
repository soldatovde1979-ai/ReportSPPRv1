@echo off
rem ==============================================================
rem  ReportSPPR: open the current notebook version in Colab.
rem  Finds the newest RepSSPR_v*.ipynb in this folder and opens it
rem  from the main branch on GitHub (main = production, README).
rem ==============================================================
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$f = Get-ChildItem -Filter 'RepSSPR_v*.ipynb' | Where-Object { $_.BaseName -match '^RepSSPR_v[0-9]+\.[0-9]+$' } | Sort-Object { [version]($_.BaseName -replace '^RepSSPR_v','') } -Descending | Select-Object -First 1; if (-not $f) { Write-Host 'RepSSPR_v*.ipynb not found in this folder' -ForegroundColor Red; exit 1 }; $u = 'https://colab.research.google.com/github/soldatovde1979-ai/ReportSPPRv1/blob/main/' + $f.Name; Write-Host ('Colab: ' + $u); Start-Process $u"
if errorlevel 1 pause
