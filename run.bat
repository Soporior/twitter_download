@echo off
cd /d D:\twitter_download

echo Starting PostgreSQL service...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$svc = Get-Service | Where-Object { $_.Name -like 'postgresql*' -or $_.DisplayName -like 'PostgreSQL*' } | Select-Object -First 1; if ($null -eq $svc) { Write-Host 'PostgreSQL service not found. Please start database manually.'; exit 0 }; if ($svc.Status -ne 'Running') { Start-Service -Name $svc.Name; $svc.WaitForStatus('Running','00:00:20') }; Write-Host ('PostgreSQL service running: ' + $svc.Name)"

python D:\twitter_download\main.py
pause
