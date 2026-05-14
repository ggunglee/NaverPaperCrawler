import subprocess
import sys
from pathlib import Path


DAILY_TASK_NAME = "NaverPaperCrawler_DailyPaperPrompt"
ONLINE_TASK_NAME = "NaverPaperCrawler_OnlineEvery3Hours"


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
    $trigger = New-ScheduledTaskTrigger -Daily -At '05:50'
    if ($repeat) {{
        $trigger.Repetition.Interval = 'PT3H'
        $trigger.Repetition.Duration = 'P1D'
    }}
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel LeastPrivilege
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
}}

Register-NaverTask '{DAILY_TASK_NAME}' '{daily_args}' $false
Register-NaverTask '{ONLINE_TASK_NAME}' '{online_args}' $true
"""
    run_powershell(script)


def uninstall_scheduled_tasks():
    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
Unregister-ScheduledTask -TaskName '{DAILY_TASK_NAME}' -Confirm:$false
Unregister-ScheduledTask -TaskName '{ONLINE_TASK_NAME}' -Confirm:$false
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
