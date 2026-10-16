@echo off
cd /d "%~dp0"
git add -A
git commit -m "auto commit before pull"
git pull
pause
