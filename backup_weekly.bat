@echo off
rem Weekly database backup for the Attendance Portal.
rem Schedule with Task Scheduler, or run manually by double-clicking.
cd /d "%~dp0"
if not exist backups mkdir backups
echo. >> backups\backup.log
echo ===== %DATE% %TIME% ===== >> backups\backup.log
python backup_db.py >> backups\backup.log 2>&1
