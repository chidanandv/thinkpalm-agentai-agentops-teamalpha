@echo off
cd /d "%~dp0"
set PYTHONPATH=src
set AUTH_ENABLED=true
set AUTH_USERNAME=admin
set AUTH_PASSWORD=fleetops
echo Starting Team Alpha Fleet Health on http://127.0.0.1:8001/
echo Login: admin / fleetops
echo Keep this window open. Press Ctrl+C to stop.
.venv\Scripts\python.exe -m fleet_health
pause
