# Add the repository launcher to this user's PATH, preserving the existing entries.
$ErrorActionPreference = 'Stop'
$taskRepo = Split-Path -Parent $PSScriptRoot
$taskBin = Join-Path $taskRepo 'bin'
if (-not (Test-Path -LiteralPath (Join-Path $taskBin 'roguebot.cmd') -PathType Leaf)) {
    throw 'O iniciador bin\roguebot.cmd nao foi encontrado.'
}
if (-not (Test-Path -LiteralPath (Join-Path $taskRepo '.venv\Scripts\python.exe') -PathType Leaf)) {
    throw 'Configure o ambiente .venv do bot antes de instalar o comando.'
}

$taskKey = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Environment')
try {
    $taskRawPath = [string]$taskKey.GetValue(
        'Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
    $taskKind = [Microsoft.Win32.RegistryValueKind]::ExpandString
    if ($taskKey.GetValueNames() -contains 'Path') {
        $taskKind = $taskKey.GetValueKind('Path')
    }
    $taskAlreadyAdded = @($taskRawPath -split ';' | Where-Object {
        [Environment]::ExpandEnvironmentVariables($_.Trim().Trim('"')).TrimEnd('\') -ieq $taskBin
    }).Count -gt 0
    if (-not $taskAlreadyAdded) {
        $taskUpdatedPath = if ([string]::IsNullOrEmpty($taskRawPath)) {
            $taskBin
        } else {
            $taskRawPath.TrimEnd(';') + ';' + $taskBin
        }
        $taskKey.SetValue('Path', $taskUpdatedPath, $taskKind)
    }
} finally {
    $taskKey.Dispose()
}

# Refresh this shell and notify Explorer so newly opened CMD windows inherit it.
if (-not (@($env:Path -split ';' | Where-Object {
    $_.Trim().Trim('"').TrimEnd('\') -ieq $taskBin
}).Count -gt 0)) {
    $env:Path = $env:Path.TrimEnd(';') + ';' + $taskBin
}
if (-not ('RoguebotEnvironment' -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class RoguebotEnvironment {
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr SendMessageTimeout(
        IntPtr window, uint message, UIntPtr wParam, string lParam,
        uint flags, uint timeout, out UIntPtr result);
}
'@
}
$taskResult = [UIntPtr]::Zero
[void][RoguebotEnvironment]::SendMessageTimeout(
    [IntPtr]0xffff, 0x1a, [UIntPtr]::Zero, 'Environment', 2, 5000, [ref]$taskResult)
Write-Host 'Comando roguebot instalado. Abra um novo CMD e digite: roguebot'
