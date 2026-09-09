"""Local process suspension and service lifecycle management."""
import ctypes
import json
import ntpath
import os
import subprocess
import sys

import psutil


SUSPEND_NAMES = {"student.exe", "mmcstudent.exe", "multiclient.exe"}


SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try {
    $action = $env:OSEASY_HELPER_ACTION
    if ($action -notin @('status', 'start', 'stop')) { throw 'Unknown control action.' }
    $service = Get-CimInstance Win32_Service -Filter "Name='MMPC'"
    $serviceExe = $null
    $root = $null
    if ($service) {
        $match = [regex]::Match($service.PathName, '(?i)^\s*(?:"(?<exe>[^"]+\.exe)"|(?<exe>.+?\.exe))(?:\s|$)')
        if ($match.Success) {
            $serviceExe = [IO.Path]::GetFullPath($match.Groups['exe'].Value)
            $root = [IO.Path]::GetDirectoryName($serviceExe).TrimEnd('\') + '\'
        }
    }
    $allProcesses = @(Get-CimInstance Win32_Process)
    # Protected service processes can hide ExecutablePath from a normal terminal.
    # Follow the service PID tree as a second, read-only discovery signal.
    $serviceTree = [Collections.Generic.HashSet[uint32]]::new()
    if ($service -and $service.ProcessId -gt 0) { $null = $serviceTree.Add([uint32]$service.ProcessId) }
    do {
        $changed = $false
        foreach ($process in $allProcesses) {
            if ($serviceTree.Contains([uint32]$process.ParentProcessId) -and
                    $serviceTree.Add([uint32]$process.ProcessId)) { $changed = $true }
        }
    } while ($changed)
    $processes = @($allProcesses | Where-Object {
        $underRoot = $false
        if ($root -and $_.ExecutablePath) {
            try {
                $underRoot = [IO.Path]::GetFullPath($_.ExecutablePath).StartsWith(
                    $root, [StringComparison]::OrdinalIgnoreCase)
            } catch { $underRoot = $false }
        }
        $underRoot -or $serviceTree.Contains([uint32]$_.ProcessId)
    })
    if ($action -eq 'status') {
        [ordered]@{
            service = $(if ($service) {
                $service | Select-Object Name, ProcessId, State, StartMode, PathName
            } else { $null })
            installRoot = $root
            processes = @($processes | Select-Object Name, ProcessId, ParentProcessId, SessionId, ExecutablePath)
            note = 'Read-only discovery by install path and MMPC process tree. A running service does not prove teacher connectivity or input protection.'
        } | ConvertTo-Json -Depth 4
        exit 0
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this command in an administrator terminal. No changes made.'
    }
    if (-not $service) { throw 'MMPC is not installed. No changes made.' }
    if (-not $serviceExe) { throw 'Cannot resolve the registered MMPC executable. No changes made.' }
    if ([IO.Path]::GetFileName($serviceExe) -ine 'MMPC.exe' -or
            -not (Test-Path -LiteralPath $serviceExe -PathType Leaf)) {
        throw 'Unexpected MMPC executable. No changes made.'
    }
    if ($action -eq 'start') {
        Start-Service -Name MMPC
        (Get-Service MMPC).WaitForStatus('Running', [TimeSpan]::FromSeconds(15))
        Write-Output 'MMPC is running. Check the original student UI for its teacher connection.'
        exit 0
    }
    Stop-Service -Name MMPC
    (Get-Service MMPC).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(15))
    # Fetch again after stopping the service; use a process handle and recheck its path.
    $stopNames = @(
        'Student.exe', 'MmcStudent.exe', 'MultiClient.exe', 'LissHelper.exe', 'LISSNetInfoSniffer.exe',
        'DeviceControl_x64.exe', 'DeviceControl_x86.exe'
    )
    $remaining = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in $stopNames })
    foreach ($process in $remaining) {
        if (-not $process.ExecutablePath) { throw 'Cannot inspect a remaining candidate process path.' }
        $path = [IO.Path]::GetFullPath($process.ExecutablePath)
        if (-not $path.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { continue }
        $target = Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
        if ($target) {
            $null = $target.Handle
            if ($target.Path -ieq $path) { $target.Kill(); $null = $target.WaitForExit(5000) }
            $target.Dispose()
        }
    }
    $left = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -in $stopNames -and $_.ExecutablePath -and
        $_.ExecutablePath.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)
    })
    if ($left.Count -gt 0 -or (Get-Service MMPC).Status -ne 'Stopped') {
        throw 'Student processes or MMPC are still running (possibly restarted by another component).'
    }
    Write-Output 'MMPC and the scoped student processes are stopped. The original student connection is interrupted.'
    Write-Output 'Drivers and startup settings are unchanged; existing input locks are not verified as cleared.'
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    [Console]::Error.WriteLine('If a change partly completed, inspect control status; use control start to restore MMPC.')
    exit 1
}
'''


def _powershell(action):
    environment = os.environ.copy()
    environment["OSEASY_HELPER_ACTION"] = action
    executable = os.path.join(environment.get("SystemRoot", r"C:\Windows"),
                              "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    try:
        return subprocess.run([executable, "-NoProfile", "-NonInteractive", "-Command", SCRIPT],
                              env=environment, capture_output=True, encoding="utf-8",
                              errors="replace", timeout=45)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Control command timed out; it may have partly completed. Inspect control status.") from error


def _document(result):
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"PowerShell exited with {result.returncode}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Cannot parse control status output") from error


def _under_root(path, root):
    if not path or not root:
        return False
    normalized_root = ntpath.normcase(ntpath.abspath(root)).rstrip("\\/") + "\\"
    normalized_path = ntpath.normcase(ntpath.abspath(path))
    return normalized_path.startswith(normalized_root)


def _decorate_status(document):
    processes = document.get("processes") or []
    if isinstance(processes, dict):
        processes = [processes]
        document["processes"] = processes
    for item in processes:
        try:
            status = psutil.Process(int(item["ProcessId"])).status()
        except (KeyError, ValueError, psutil.Error):
            status = "unavailable"
        item["status"] = status
        item["suspended"] = status == psutil.STATUS_STOPPED
    return document


def _change_suspension(action, install_root, process_iter=None):
    """Follow OsEasy-ToolBox's psutil suspend/resume approach, with path checks."""
    if process_iter is None:
        process_iter = psutil.process_iter
    found = []
    failures = []
    for process in process_iter(["pid", "name", "exe", "status"]):
        name = (process.info.get("name") or "").casefold()
        if name not in SUSPEND_NAMES:
            continue
        try:
            # Re-read identity immediately before changing state to reduce PID-race risk.
            actual_name = process.name()
            executable = process.exe()
            if actual_name.casefold() not in SUSPEND_NAMES or not _under_root(executable, install_root):
                continue
            before = process.status()
            suspended = before == psutil.STATUS_STOPPED
            if action == "suspend" and not suspended:
                process.suspend()
                result = "suspended"
            elif action == "resume" and suspended:
                process.resume()
                result = "resumed"
            else:
                result = "already suspended" if suspended else "already running"
            found.append(f"{actual_name} (PID {process.pid}): {result}")
        except (psutil.Error, OSError) as error:
            failures.append(f"{process.info.get('name')} (PID {process.info.get('pid')}): {error}")
    if not found:
        detail = f" ({'; '.join(failures)})" if failures else ""
        raise RuntimeError("No running Student.exe, MmcStudent.exe or MultiClient.exe was found in the MMPC install directory" + detail)
    if failures:
        raise RuntimeError("Some processes changed state, but others failed: " + "; ".join(failures))
    return found


def run(action):
    if sys.platform != "win32":
        raise RuntimeError("control requires Windows")
    if action not in ("status", "suspend", "resume", "start", "stop"):
        raise ValueError("Unknown control action")
    if action == "status":
        print(json.dumps(_decorate_status(_document(_powershell("status"))),
                         ensure_ascii=False, indent=4))
        return
    if action in ("suspend", "resume"):
        if not ctypes.windll.shell32.IsUserAnAdmin():
            raise RuntimeError("Run this command in an administrator terminal. No changes made.")
        status = _document(_powershell("status"))
        install_root = status.get("installRoot")
        if not install_root:
            raise RuntimeError("Cannot resolve the MMPC install directory. No changes made.")
        for line in _change_suspension(action, install_root):
            print(line)
        print("MMPC service state is unchanged. Teacher connectivity after suspension is not guaranteed.")
        return
    result = _powershell(action)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"PowerShell exited with {result.returncode}")
