"""Local service lifecycle only; never touch drivers or persistent startup settings."""
import os
import subprocess
import sys


SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try {
    $action = $env:OSEASY_HELPER_ACTION
    if ($action -notin @('status', 'start', 'stop')) { throw 'Unknown control action.' }
    $service = Get-CimInstance Win32_Service -Filter "Name='MMPC'"
    $names = @('Student.exe', 'MultiClient.exe', 'LissHelper.exe')
    $processes = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in $names })
    if ($action -eq 'status') {
        [ordered]@{
            service = $(if ($service) {
                $service | Select-Object Name, State, StartMode, PathName
            } else { $null })
            candidates = @($processes | Select-Object Name, ProcessId, ExecutablePath)
            note = 'Status only. A running service does not prove teacher connectivity or input protection.'
        } | ConvertTo-Json -Depth 4
        exit 0
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this command in an administrator terminal. No changes made.'
    }
    if (-not $service) { throw 'MMPC is not installed. No changes made.' }
    $match = [regex]::Match($service.PathName, '(?i)^\s*(?:"(?<exe>[^"]+\.exe)"|(?<exe>.+?\.exe))(?:\s|$)')
    if (-not $match.Success) { throw 'Cannot resolve the registered MMPC executable. No changes made.' }
    $exe = [IO.Path]::GetFullPath($match.Groups['exe'].Value)
    if ([IO.Path]::GetFileName($exe) -ine 'MMPC.exe' -or -not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw 'Unexpected MMPC executable. No changes made.'
    }
    if ($action -eq 'start') {
        Start-Service -Name MMPC
        (Get-Service MMPC).WaitForStatus('Running', [TimeSpan]::FromSeconds(15))
        Write-Output 'MMPC is running. Check the original student UI for its teacher connection.'
        exit 0
    }
    $root = [IO.Path]::GetDirectoryName($exe).TrimEnd('\') + '\'
    # Validate process paths before changing anything; never kill by name alone.
    foreach ($process in $processes) {
        if (-not $process.ExecutablePath) { throw 'Cannot inspect a candidate process path. No changes made.' }
    }
    Stop-Service -Name MMPC
    (Get-Service MMPC).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(15))
    # Fetch again after stopping the service; use a process handle and recheck its path.
    $remaining = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in $names })
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
        $_.Name -in $names -and $_.ExecutablePath -and
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


def run(action):
    if sys.platform != "win32":
        raise RuntimeError("control requires Windows")
    if action not in ("status", "start", "stop"):
        raise ValueError("Unknown control action")
    environment = os.environ.copy()
    environment["OSEASY_HELPER_ACTION"] = action
    executable = os.path.join(environment.get("SystemRoot", r"C:\Windows"),
                              "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    try:
        result = subprocess.run([executable, "-NoProfile", "-NonInteractive", "-Command", SCRIPT],
                                env=environment, capture_output=True, encoding="utf-8", errors="replace", timeout=45)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Control command timed out; it may have partly completed. Inspect control status.") from error
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"PowerShell exited with {result.returncode}")
