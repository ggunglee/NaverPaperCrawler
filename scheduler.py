import subprocess
import sys
from pathlib import Path


DAILY_TASK_NAME = "NaverPaperCrawler_DailyPaperPrompt"
ONLINE_TASK_NAME = "NaverPaperCrawler_OnlineEvery3Hours"
MORNING_REPORT_TASK_NAME = "NaverPaperCrawler_MorningReportTelegram"


def app_command():
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        return str(exe), str(exe.parent), ""
    script = Path(__file__).resolve().parent / "main.py"
    exe = Path(sys.executable).resolve()
    return str(exe), str(script.parent), f'"{script}" '


def install_scheduled_tasks():
    exe, workdir, script_prefix = app_command()
    daily_args = f'{script_prefix}--crawl-today-with-prompt'
    online_args = f'{script_prefix}--crawl-online --no-gui'
    if getattr(sys, "frozen", False):
        morning_args = "--run-morning-report"
    else:
        morning_script = Path(__file__).resolve().parent / "morning_report_task.py"
        morning_args = f'"{morning_script}" --date today --send-telegram --force --no-llm'
    script = f"""
$ErrorActionPreference = 'Stop'
$exe = @'
{exe}
'@
$workdir = @'
{workdir}
'@

function Register-NaverTask($name, $arguments, $repeat) {{
    $action = New-ScheduledTaskAction -Execute $exe -Argument $arguments -WorkingDirectory $workdir
    if ($repeat) {{
        $trigger = New-ScheduledTaskTrigger -Daily -At '05:50' -RepetitionInterval (New-TimeSpan -Hours 3) -RepetitionDuration (New-TimeSpan -Days 1)
    }} else {{
        $trigger = New-ScheduledTaskTrigger -Daily -At '05:50'
    }}
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
}}

Unregister-ScheduledTask -TaskName '{DAILY_TASK_NAME}' -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName '{ONLINE_TASK_NAME}' -Confirm:$false -ErrorAction SilentlyContinue

$morningAction = New-ScheduledTaskAction -Execute $exe -Argument @'
{morning_args}
'@ -WorkingDirectory $workdir
$morningTrigger = New-ScheduledTaskTrigger -Daily -At '06:00'
$morningSettings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
$morningPrincipal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName '{MORNING_REPORT_TASK_NAME}' -Action $morningAction -Trigger $morningTrigger -Settings $morningSettings -Principal $morningPrincipal -Force | Out-Null
"""
    run_powershell(script)


def uninstall_scheduled_tasks():
    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
Unregister-ScheduledTask -TaskName '{DAILY_TASK_NAME}' -Confirm:$false
Unregister-ScheduledTask -TaskName '{ONLINE_TASK_NAME}' -Confirm:$false
Unregister-ScheduledTask -TaskName '{MORNING_REPORT_TASK_NAME}' -Confirm:$false
"""
    run_powershell(script)


def run_powershell(script: str):
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "작업 스케줄러 명령이 실패했습니다.").strip())
    return completed.stdout
