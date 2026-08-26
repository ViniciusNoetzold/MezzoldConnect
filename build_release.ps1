param(
    [switch]$SkipInstall,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$arguments = @{ SkipAppBuild = $false }
if ($SkipInstall) { $arguments.SkipInstall = $true }
if ($SkipTests) { $arguments.SkipTests = $true }
& (Join-Path $root "installer\build_installer.ps1") @arguments
